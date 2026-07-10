"""OrderHistorySyncFeed — 브로커 실제 주문 목록을 로컬 orders 테이블과 동기화하는 테스트.

버그 배경: 로컬 orders 테이블은 OrderExecutor.submit()이 만든 행만 채워졌는데,
이 executor.submit()을 실제로 호출하는 신호 파이프라인이 없다(StrategyEngine이
SIGNAL을 발행해도 소비자가 없음). 그래서 "주문내역" 화면이 실제 계좌 상태를
반영하지 못했다 — 이 피드는 Toss list_orders()를 브로커 source of truth로 삼아
orders 테이블을 채운다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

import core.execution.order_history_sync as order_history_sync_module
from core.adapters.toss.models import OrderExecution, TossOrder
from core.execution.order_history_sync import OrderHistorySyncFeed
from core.store.db import StateStore

_ORDERED_AT = datetime(2026, 7, 10, 9, 0, 0, tzinfo=UTC)


def _toss_order(
    order_id: str,
    status: str,
    *,
    symbol: str = "005930",
    side: str = "BUY",
    order_type: str = "LIMIT",
    quantity: int = 1,
    price: Decimal | None = Decimal("75000"),
    currency: str = "KRW",
    client_order_id: str | None = None,
) -> TossOrder:
    return TossOrder(
        order_id=order_id,
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        order_type=order_type,  # type: ignore[arg-type]
        status=status,
        quantity=quantity,
        currency=currency,
        ordered_at=_ORDERED_AT,
        execution=OrderExecution(filled_quantity=0, avg_fill_price=None, fees=None),
        client_order_id=client_order_id,
        price=price,
    )


class _FakeRestClient:
    """closed_orders를 리스트의 리스트로 주면 페이지네이션을 시뮬레이션한다
    (예: [[order1, order2], [order3]] → 첫 호출은 cursor="1"과 함께 2건,
    cursor="1"로 재호출하면 마지막 1건과 cursor=None)."""

    def __init__(
        self,
        open_orders: list[TossOrder],
        closed_orders: list[TossOrder] | list[list[TossOrder]],
    ) -> None:
        self._open = open_orders
        self._closed_pages: list[list[TossOrder]] = (
            closed_orders
            if closed_orders and isinstance(closed_orders[0], list)
            else [closed_orders]
        )
        self.calls: list[str] = []

    async def list_orders(self, status, symbol=None, cursor=None, limit=100):
        self.calls.append(status)
        if status == "OPEN":
            return self._open, None

        page_index = int(cursor) if cursor is not None else 0
        page = self._closed_pages[page_index] if page_index < len(self._closed_pages) else []
        next_index = page_index + 1
        next_cursor = str(next_index) if next_index < len(self._closed_pages) else None
        return page, next_cursor


@pytest.fixture
async def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "test.db"))
    await s.open()
    yield s
    await s.close()


async def _fetch_order(store: StateStore, client_order_id: str) -> dict | None:
    async with store.conn.execute(
        "SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


@pytest.mark.asyncio
async def test_sync_once_inserts_native_order_not_placed_by_bot(store) -> None:
    """clientOrderId가 없는(Toss 앱에서 직접 낸) 주문은 toss-native-* 로 새로 삽입된다."""
    rest = _FakeRestClient(
        open_orders=[_toss_order("toss-100", "PENDING", client_order_id=None)],
        closed_orders=[],
    )
    feed = OrderHistorySyncFeed(rest_client=rest, store=store)

    reflected = await feed.sync_once()

    assert reflected == 1
    row = await _fetch_order(store, "toss-native-toss-100")
    assert row is not None
    assert row["broker_order_id"] == "toss-100"
    assert row["status"] == "pending"
    assert row["side"] == "buy"
    assert row["order_type"] == "limit"
    assert row["market"] == "domestic"


@pytest.mark.asyncio
async def test_sync_once_updates_existing_order_by_client_order_id(store) -> None:
    """OrderExecutor.submit()이 먼저 만든 행(client_order_id 존재)은 브로커 상태로 갱신된다."""
    now = datetime.now(UTC).isoformat()
    await store.conn.execute(
        """
        INSERT INTO orders
            (client_order_id, symbol, market, env, side, order_type, qty, price,
             status, broker_order_id, created_at, updated_at)
        VALUES ('c1', '005930', 'domestic', 'prod', 'buy', 'limit', 1, 75000, 'submitted', 'toss-200', ?, ?)
        """,
        (now, now),
    )
    await store.conn.commit()

    rest = _FakeRestClient(
        open_orders=[],
        closed_orders=[_toss_order("toss-200", "FILLED", client_order_id="c1")],
    )
    feed = OrderHistorySyncFeed(rest_client=rest, store=store)

    reflected = await feed.sync_once()

    assert reflected == 1
    row = await _fetch_order(store, "c1")
    assert row["status"] == "filled"
    assert row["broker_order_id"] == "toss-200"

    # 중복 삽입되지 않아야 한다 (client_order_id 기준으로 갱신만 일어남).
    async with store.conn.execute("SELECT COUNT(*) FROM orders") as cursor:
        (total,) = await cursor.fetchone()
    assert total == 1


@pytest.mark.asyncio
async def test_sync_once_infers_overseas_market_from_currency(store) -> None:
    rest = _FakeRestClient(
        open_orders=[
            _toss_order(
                "toss-300", "PENDING", symbol="AAPL", currency="USD", price=Decimal("185.5")
            )
        ],
        closed_orders=[],
    )
    feed = OrderHistorySyncFeed(rest_client=rest, store=store)

    await feed.sync_once()

    row = await _fetch_order(store, "toss-native-toss-300")
    assert row["market"] == "overseas"


@pytest.mark.asyncio
async def test_sync_once_skips_unknown_status_without_raising(store) -> None:
    rest = _FakeRestClient(
        open_orders=[_toss_order("toss-400", "SOME_NEW_TOSS_STATUS")],
        closed_orders=[],
    )
    feed = OrderHistorySyncFeed(rest_client=rest, store=store)

    reflected = await feed.sync_once()

    assert reflected == 0
    assert await _fetch_order(store, "toss-native-toss-400") is None


@pytest.mark.asyncio
async def test_sync_once_isolates_partial_failures(store, monkeypatch) -> None:
    """한 주문 반영이 실패해도 나머지 주문은 계속 처리된다."""
    rest = _FakeRestClient(
        open_orders=[
            _toss_order("toss-500", "PENDING"),
            _toss_order("toss-501", "PENDING"),
        ],
        closed_orders=[],
    )
    feed = OrderHistorySyncFeed(rest_client=rest, store=store)

    original_upsert = store.upsert_broker_order

    async def _flaky_upsert(*, broker_order_id, **kwargs):
        if broker_order_id == "toss-500":
            raise RuntimeError("DB 오류 시뮬레이션")
        return await original_upsert(broker_order_id=broker_order_id, **kwargs)

    monkeypatch.setattr(store, "upsert_broker_order", _flaky_upsert)

    reflected = await feed.sync_once()

    assert reflected == 1
    assert await _fetch_order(store, "toss-native-toss-500") is None
    assert await _fetch_order(store, "toss-native-toss-501") is not None


@pytest.mark.asyncio
async def test_sync_once_queries_both_open_and_closed_groups(store) -> None:
    rest = _FakeRestClient(open_orders=[], closed_orders=[])
    feed = OrderHistorySyncFeed(rest_client=rest, store=store)

    await feed.sync_once()

    assert rest.calls == ["OPEN", "CLOSED"]


@pytest.mark.asyncio
async def test_sync_once_paginates_full_closed_history_on_first_call(store) -> None:
    """최초 호출은 CLOSED 커서를 끝까지 순회해 전체 이력을 백필해야 한다."""
    page1 = [_toss_order("toss-600", "FILLED")]
    page2 = [_toss_order("toss-601", "FILLED")]
    rest = _FakeRestClient(open_orders=[], closed_orders=[page1, page2])
    feed = OrderHistorySyncFeed(rest_client=rest, store=store)

    reflected = await feed.sync_once()

    assert reflected == 2
    assert rest.calls == ["OPEN", "CLOSED", "CLOSED"]
    assert await _fetch_order(store, "toss-native-toss-600") is not None
    assert await _fetch_order(store, "toss-native-toss-601") is not None


@pytest.mark.asyncio
async def test_second_sync_once_only_fetches_latest_closed_page(store) -> None:
    """백필이 끝난 뒤에는 CLOSED를 매번 끝까지 순회하지 않고 최신 페이지만 확인한다."""
    page1 = [_toss_order("toss-700", "FILLED")]
    page2 = [_toss_order("toss-701", "FILLED")]
    rest = _FakeRestClient(open_orders=[], closed_orders=[page1, page2])
    feed = OrderHistorySyncFeed(rest_client=rest, store=store)

    await feed.sync_once()  # 최초 호출 — 전체 백필
    rest.calls.clear()

    await feed.sync_once()  # 두 번째 호출 — 최신 페이지만

    assert rest.calls == ["OPEN", "CLOSED"]


@pytest.mark.asyncio
async def test_backfill_hitting_page_cap_retries_full_backfill_next_cycle(
    store, monkeypatch
) -> None:
    """백필이 _MAX_BACKFILL_PAGES 상한에 걸려 일부만 받았으면, 완료로 표시하면
    안 된다 — 다음 주기에도 여전히 전체 백필을 다시 시도해야 한다.

    버그였던 동작: 상한에 걸려도 _closed_history_backfilled=True로 고정돼
    버려서, 대량 거래 계정은 오래된 이력을 영영 못 가져왔다.
    """
    monkeypatch.setattr(order_history_sync_module, "_MAX_BACKFILL_PAGES", 2)

    page1 = [_toss_order("toss-800", "FILLED")]
    page2 = [_toss_order("toss-801", "FILLED")]
    page3 = [_toss_order("toss-802", "FILLED")]  # 상한(2페이지)을 넘는 3번째 페이지
    rest = _FakeRestClient(open_orders=[], closed_orders=[page1, page2, page3])
    feed = OrderHistorySyncFeed(rest_client=rest, store=store)

    await feed.sync_once()  # 상한에 걸려 page3는 못 받음

    assert feed._closed_history_backfilled is False
    assert await _fetch_order(store, "toss-native-toss-802") is None

    rest.calls.clear()
    await feed.sync_once()  # 두 번째 호출도 여전히 전체 백필을 재시도해야 함

    assert rest.calls == ["OPEN", "CLOSED", "CLOSED"]
