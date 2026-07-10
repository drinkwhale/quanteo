"""OrderSyncFeed — 브로커 주문 상태를 로컬 orders 테이블과 동기화하는 테스트.

버그 배경: OrderExecutor.submit()은 주문을 'submitted'로 한 번 기록한 뒤
다시는 상태를 확인하지 않는다 (record_fill()을 호출하는 곳이 아무 데도 없음).
Toss는 WebSocket 체결 통지가 없어 REST 폴링으로 직접 확인해야 하는데, 이
동기화 루프가 없어서 실제로는 체결/취소/거부된 주문이 로컬 DB에는 영원히
'submitted'로 남아 있었다 (005930 28건 적체 사례).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

import core.execution.order_sync as order_sync_module
from core.events.bus import EventBus
from core.events.types import EventType
from core.execution.order_sync import OrderSyncFeed
from core.risk.models import OrderSide
from core.store.db import StateStore


@dataclass
class _FakeExecution:
    filled_quantity: int
    avg_fill_price: Decimal | None
    fees: Decimal | None = None


@dataclass
class _FakeTossOrder:
    order_id: str
    status: str
    quantity: int
    execution: _FakeExecution


class _FakeRestClient:
    def __init__(self, responses: dict[str, _FakeTossOrder | Exception]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    async def get_order(self, order_id: str) -> _FakeTossOrder:
        self.calls.append(order_id)
        result = self._responses[order_id]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
async def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "test.db"))
    await s.open()
    yield s
    await s.close()


async def _insert_order(
    store: StateStore,
    client_order_id: str,
    broker_order_id: str,
    symbol: str = "005930",
    status: str = "submitted",
    qty: int = 1,
) -> None:
    now = datetime.now(UTC).isoformat()
    await store.conn.execute(
        """
        INSERT INTO orders
            (client_order_id, symbol, market, env, side, order_type, qty, price,
             status, broker_order_id, created_at, updated_at)
        VALUES (?, ?, 'domestic', 'prod', ?, 'limit', ?, 75000, ?, ?, ?, ?)
        """,
        (client_order_id, symbol, OrderSide.BUY.value, qty, status, broker_order_id, now, now),
    )
    await store.conn.commit()


async def _status_of(store: StateStore, client_order_id: str) -> str:
    async with store.conn.execute(
        "SELECT status FROM orders WHERE client_order_id = ?", (client_order_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row["status"]


@pytest.mark.asyncio
async def test_sync_once_marks_filled_order_as_filled(store) -> None:
    await _insert_order(store, "c1", "toss-1")
    rest = _FakeRestClient(
        {"toss-1": _FakeTossOrder("toss-1", "FILLED", 1, _FakeExecution(1, Decimal("75000")))}
    )
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod")

    await feed.sync_once()

    assert await _status_of(store, "c1") == "filled"


@pytest.mark.asyncio
async def test_sync_once_marks_canceled_order_as_cancelled(store) -> None:
    await _insert_order(store, "c2", "toss-2")
    rest = _FakeRestClient(
        {"toss-2": _FakeTossOrder("toss-2", "CANCELED", 1, _FakeExecution(0, None))}
    )
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod")

    await feed.sync_once()

    assert await _status_of(store, "c2") == "cancelled"


@pytest.mark.asyncio
async def test_sync_once_marks_rejected_order_as_rejected(store) -> None:
    await _insert_order(store, "c3", "toss-3")
    rest = _FakeRestClient(
        {"toss-3": _FakeTossOrder("toss-3", "REJECTED", 1, _FakeExecution(0, None))}
    )
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod")

    await feed.sync_once()

    assert await _status_of(store, "c3") == "rejected"


@pytest.mark.asyncio
async def test_sync_once_leaves_still_open_order_untouched(store) -> None:
    """브로커가 여전히 PENDING/PARTIAL_FILLED면 로컬 상태를 건드리지 않는다."""
    await _insert_order(store, "c4", "toss-4")
    rest = _FakeRestClient(
        {"toss-4": _FakeTossOrder("toss-4", "PENDING", 1, _FakeExecution(0, None))}
    )
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod")

    await feed.sync_once()

    assert await _status_of(store, "c4") == "submitted"


@pytest.mark.asyncio
async def test_sync_once_publishes_order_filled_event(store) -> None:
    await _insert_order(store, "c5", "toss-5")
    rest = _FakeRestClient(
        {"toss-5": _FakeTossOrder("toss-5", "FILLED", 1, _FakeExecution(1, Decimal("75000")))}
    )
    bus = EventBus()
    published = []
    bus.publish_nowait = lambda event: published.append(event)  # type: ignore[method-assign]
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod", bus=bus)

    await feed.sync_once()

    assert any(e.type == EventType.ORDER_FILLED for e in published)


@pytest.mark.asyncio
async def test_sync_once_skips_order_on_broker_error_and_continues(store) -> None:
    """한 주문 조회가 실패해도 나머지는 계속 처리해야 한다 (부분 실패 격리)."""
    await _insert_order(store, "c6", "toss-6")
    await _insert_order(store, "c7", "toss-7")
    rest = _FakeRestClient(
        {
            "toss-6": RuntimeError("네트워크 오류"),
            "toss-7": _FakeTossOrder("toss-7", "FILLED", 1, _FakeExecution(1, Decimal("75000"))),
        }
    )
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod")

    await feed.sync_once()

    assert await _status_of(store, "c6") == "submitted"  # 실패한 건 그대로
    assert await _status_of(store, "c7") == "filled"  # 나머지는 정상 처리


@pytest.mark.asyncio
async def test_sync_once_ignores_orders_without_broker_order_id(store) -> None:
    """place_order 응답 전(broker_order_id 없음) 주문은 조회 대상에서 제외."""
    now = datetime.now(UTC).isoformat()
    await store.conn.execute(
        """
        INSERT INTO orders
            (client_order_id, symbol, market, env, side, order_type, qty, price,
             status, broker_order_id, created_at, updated_at)
        VALUES ('c8', '005930', 'domestic', 'prod', 'buy', 'limit', 1, 75000,
                'pending', NULL, ?, ?)
        """,
        (now, now),
    )
    await store.conn.commit()
    rest = _FakeRestClient({})
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod")

    await feed.sync_once()

    assert rest.calls == []
    assert await _status_of(store, "c8") == "pending"


@pytest.mark.asyncio
async def test_sync_once_isolates_db_update_failure_from_other_orders(store, monkeypatch) -> None:
    """update_order_status() 실패가 나머지 주문 처리를 막지 않아야 한다 (부분 실패 격리)."""
    await _insert_order(store, "c9", "toss-9")
    await _insert_order(store, "c10", "toss-10")
    rest = _FakeRestClient(
        {
            "toss-9": _FakeTossOrder("toss-9", "FILLED", 1, _FakeExecution(1, Decimal("75000"))),
            "toss-10": _FakeTossOrder("toss-10", "FILLED", 1, _FakeExecution(1, Decimal("75000"))),
        }
    )
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod")

    original_update = store.update_order_status
    call_count = 0

    async def _flaky_update(client_order_id: str, status: str, broker_order_id: str | None = None) -> None:
        nonlocal call_count
        call_count += 1
        if client_order_id == "c9":
            raise RuntimeError("DB 갱신 실패")
        await original_update(client_order_id, status, broker_order_id)

    monkeypatch.setattr(store, "update_order_status", _flaky_update)

    await feed.sync_once()

    assert await _status_of(store, "c9") == "submitted"  # 갱신 실패 — 그대로
    assert await _status_of(store, "c10") == "filled"  # 나머지는 정상 처리
    assert call_count == 2  # 둘 다 시도는 됨


@pytest.mark.asyncio
async def test_sync_once_logs_unmapped_status_without_crashing(store, caplog) -> None:
    """CANCEL_REJECTED처럼 매핑에 없는 상태는 로컬 상태를 유지하되 로그로는 남긴다."""
    await _insert_order(store, "c11", "toss-11")
    rest = _FakeRestClient(
        {"toss-11": _FakeTossOrder("toss-11", "CANCEL_REJECTED", 1, _FakeExecution(0, None))}
    )
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod")

    with caplog.at_level("DEBUG", logger="core.execution.order_sync"):
        await feed.sync_once()

    assert await _status_of(store, "c11") == "submitted"
    assert any("CANCEL_REJECTED" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_sync_once_still_updates_db_when_event_type_mapping_missing(store, monkeypatch) -> None:
    """_CLOSED_STATUS_MAP과 _EVENT_TYPE_MAP의 키가 어긋나도 DB 갱신은 성공해야 한다."""
    await _insert_order(store, "c12", "toss-12")
    rest = _FakeRestClient(
        {"toss-12": _FakeTossOrder("toss-12", "FILLED", 1, _FakeExecution(1, Decimal("75000")))}
    )
    bus = EventBus()
    published = []
    bus.publish_nowait = lambda event: published.append(event)  # type: ignore[method-assign]
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod", bus=bus)

    # 의도적으로 매핑 불일치 상황을 재현 — "filled"에 대한 이벤트 타입이 없음.
    monkeypatch.setattr(order_sync_module, "_EVENT_TYPE_MAP", {})

    await feed.sync_once()

    assert await _status_of(store, "c12") == "filled"  # DB 갱신은 이벤트와 무관하게 성공
    assert published == []  # 이벤트는 발행되지 않음 (조용히 스킵, 크래시 없음)


@pytest.mark.asyncio
async def test_run_loop_exits_promptly_after_stop(store) -> None:
    """run()의 무한 루프가 stop() 호출 후 실제로 종료돼야 한다 (SIGTERM 행 버그 회귀)."""
    rest = _FakeRestClient({})
    feed = OrderSyncFeed(rest_client=rest, store=store, env="prod", poll_interval=3600.0)

    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0.05)  # run()이 sync_once() 1회를 돌고 대기 상태로 들어갈 시간
    assert not task.done()

    await feed.stop()
    await asyncio.wait_for(task, timeout=2.0)  # 타임아웃 시 실패 — 루프가 안 끝났다는 뜻

    assert task.done()
