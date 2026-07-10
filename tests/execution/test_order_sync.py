"""OrderSyncFeed — 브로커 주문 상태를 로컬 orders 테이블과 동기화하는 테스트.

버그 배경: OrderExecutor.submit()은 주문을 'submitted'로 한 번 기록한 뒤
다시는 상태를 확인하지 않는다 (record_fill()을 호출하는 곳이 아무 데도 없음).
Toss는 WebSocket 체결 통지가 없어 REST 폴링으로 직접 확인해야 하는데, 이
동기화 루프가 없어서 실제로는 체결/취소/거부된 주문이 로컬 DB에는 영원히
'submitted'로 남아 있었다 (005930 28건 적체 사례).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

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
