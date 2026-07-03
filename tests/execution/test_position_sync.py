"""PositionSyncFeed — 실계좌 잔고 → 로컬 positions 테이블 동기화 테스트."""

from __future__ import annotations

import asyncio

import pytest

from core.adapters.models import BalanceInfo, BalanceItem
from core.config.settings import Market
from core.events.bus import EventBus
from core.events.types import EventType
from core.execution.position_sync import _CONSECUTIVE_FAILURE_ALERT_THRESHOLD, PositionSyncFeed
from core.store.db import StateStore


def _item(symbol: str, qty: float, avg_price: float, market: Market = Market.DOMESTIC) -> BalanceItem:
    return BalanceItem(
        symbol=symbol,
        symbol_name=symbol,
        qty=qty,
        avg_price=avg_price,
        current_price=avg_price,
        eval_amount=qty * avg_price,
        profit_loss=0.0,
        profit_loss_rate=0.0,
        market=market,
    )


class _FakeRestClient:
    def __init__(self, items: list[BalanceItem]) -> None:
        self._items = items

    async def get_balance(self, symbol: str | None = None) -> BalanceInfo:
        return BalanceInfo(items=self._items, total_eval_amount_krw=0.0, total_profit_loss_krw=0.0, deposit=0.0)


@pytest.fixture
async def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "test.db"))
    await s.open()
    yield s
    await s.close()


async def _fetch_positions(store: StateStore) -> list[dict]:
    async with store.conn.execute(
        "SELECT symbol, market, env, qty, avg_price FROM positions ORDER BY symbol"
    ) as cursor:
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@pytest.mark.asyncio
async def test_sync_once_inserts_new_positions(store):
    rest = _FakeRestClient([_item("005930", 10, 70000.0)])
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod")

    await feed.sync_once()

    rows = await _fetch_positions(store)
    assert rows == [
        {"symbol": "005930", "market": "domestic", "env": "prod", "qty": 10, "avg_price": 70000.0}
    ]


@pytest.mark.asyncio
async def test_sync_once_updates_existing_position_qty(store):
    rest = _FakeRestClient([_item("005930", 10, 70000.0)])
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod")
    await feed.sync_once()

    feed._rest = _FakeRestClient([_item("005930", 15, 71000.0)])
    await feed.sync_once()

    rows = await _fetch_positions(store)
    assert len(rows) == 1
    assert rows[0]["qty"] == 15
    assert rows[0]["avg_price"] == 71000.0


@pytest.mark.asyncio
async def test_sync_once_closes_position_no_longer_held(store):
    rest = _FakeRestClient([_item("005930", 10, 70000.0)])
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod")
    await feed.sync_once()

    # 실계좌에서 전량 매도됨 — 다음 동기화에서 holdings 목록에서 사라짐
    feed._rest = _FakeRestClient([])
    await feed.sync_once()

    async with store.conn.execute(
        "SELECT qty FROM positions WHERE symbol = ? AND env = ?", ("005930", "prod")
    ) as cursor:
        row = await cursor.fetchone()
    assert row["qty"] == 0

    # /positions 라우트와 동일하게 qty > 0 필터링하면 더 이상 노출되지 않는다
    async with store.conn.execute("SELECT * FROM positions WHERE qty > 0") as cursor:
        rows = await cursor.fetchall()
    assert rows == []


@pytest.mark.asyncio
async def test_sync_once_preserves_opened_at_on_update(store):
    rest = _FakeRestClient([_item("005930", 10, 70000.0)])
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod")
    await feed.sync_once()

    async with store.conn.execute(
        "SELECT opened_at FROM positions WHERE symbol = ?", ("005930",)
    ) as cursor:
        first_opened_at = (await cursor.fetchone())["opened_at"]

    feed._rest = _FakeRestClient([_item("005930", 20, 72000.0)])
    await feed.sync_once()

    async with store.conn.execute(
        "SELECT opened_at FROM positions WHERE symbol = ?", ("005930",)
    ) as cursor:
        second_opened_at = (await cursor.fetchone())["opened_at"]

    assert first_opened_at == second_opened_at


def _drain(bus: EventBus) -> list:
    events = []
    while not bus._queue.empty():
        events.append(bus._queue.get_nowait())
    return events


@pytest.mark.asyncio
async def test_sync_once_publishes_position_updated_for_new_position(store):
    bus = EventBus()
    rest = _FakeRestClient([_item("005930", 10, 70000.0)])
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod", bus=bus)

    await feed.sync_once()

    events = _drain(bus)
    assert len(events) == 1
    assert events[0].type == EventType.POSITION_UPDATED
    assert events[0].payload.symbol == "005930"
    assert events[0].payload.change == "opened"


@pytest.mark.asyncio
async def test_sync_once_publishes_nothing_when_unchanged(store):
    bus = EventBus()
    rest = _FakeRestClient([_item("005930", 10, 70000.0)])
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod", bus=bus)
    await feed.sync_once()
    _drain(bus)  # 최초 "opened" 이벤트 소진

    # 동일한 잔고로 재조회 — 변화 없음
    await feed.sync_once()

    assert _drain(bus) == []


@pytest.mark.asyncio
async def test_sync_once_publishes_closed_event_for_liquidated_position(store):
    bus = EventBus()
    rest = _FakeRestClient([_item("005930", 10, 70000.0)])
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod", bus=bus)
    await feed.sync_once()
    _drain(bus)

    feed._rest = _FakeRestClient([])
    await feed.sync_once()

    events = _drain(bus)
    assert len(events) == 1
    assert events[0].payload.change == "closed"
    assert events[0].payload.qty == 0


@pytest.mark.asyncio
async def test_sync_once_supports_fractional_qty_for_overseas_stock(store):
    """미국 주식은 소수점 단위 매매(fractional investing)로 정수가 아닌 수량이 나올 수 있다."""
    rest = _FakeRestClient([_item("AAPL", 10.5, 155.3, market=Market.OVERSEAS)])
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod")

    await feed.sync_once()

    rows = await _fetch_positions(store)
    assert rows[0]["qty"] == 10.5


class _FailNTimesRestClient:
    """처음 N번은 실패하고 이후 성공하는 가짜 클라이언트 (일시적 장애 시뮬레이션)."""

    def __init__(self, fail_times: int) -> None:
        self._fail_times = fail_times
        self.calls = 0

    async def get_balance(self, symbol: str | None = None) -> BalanceInfo:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("simulated network failure")
        return BalanceInfo(items=[], total_eval_amount_krw=0.0, total_profit_loss_krw=0.0, deposit=0.0)


@pytest.mark.asyncio
async def test_run_recovers_after_transient_failure(store):
    rest = _FailNTimesRestClient(fail_times=1)
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod", poll_interval=0.01)

    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0.1)
    await feed.stop()
    await task

    assert rest.calls >= 2
    assert feed._consecutive_failures == 0


class _AlwaysFailingRestClient:
    """항상 실패하는 가짜 클라이언트 (지속 장애 시뮬레이션)."""

    async def get_balance(self, symbol: str | None = None) -> BalanceInfo:
        raise RuntimeError("broker down")


@pytest.mark.asyncio
async def test_run_publishes_error_event_after_consecutive_failures(store):
    bus = EventBus()
    rest = _AlwaysFailingRestClient()
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod", poll_interval=0.01, bus=bus)

    task = asyncio.create_task(feed.run())
    # 임계치(_CONSECUTIVE_FAILURE_ALERT_THRESHOLD)만큼 실패할 시간을 준다
    await asyncio.sleep(0.01 * (_CONSECUTIVE_FAILURE_ALERT_THRESHOLD + 2))
    await feed.stop()
    await task

    events = _drain(bus)
    error_events = [e for e in events if e.type == EventType.ERROR]
    assert len(error_events) >= 1
    assert error_events[0].payload["source"] == "position-sync"


class _SlowFakeRestClient:
    """실제 네트워크 호출처럼 지연이 있는 가짜 클라이언트 — 동시 호출 레이스 재현용."""

    def __init__(self, items: list[BalanceItem]) -> None:
        self._items = items

    async def get_balance(self, symbol: str | None = None) -> BalanceInfo:
        await asyncio.sleep(0.02)
        return BalanceInfo(items=self._items, total_eval_amount_krw=0.0, total_profit_loss_krw=0.0, deposit=0.0)


@pytest.mark.asyncio
async def test_sync_once_serializes_concurrent_calls(store):
    """락이 없으면 두 호출이 동시에 SELECT(이전 상태)를 읽어 'opened' 이벤트가 중복 발행될 수 있다."""
    bus = EventBus()
    rest = _SlowFakeRestClient([_item("005930", 10, 70000.0)])
    feed = PositionSyncFeed(rest_client=rest, store=store, env="prod", bus=bus)

    await asyncio.gather(feed.sync_once(), feed.sync_once())

    rows = await _fetch_positions(store)
    assert len(rows) == 1

    events = _drain(bus)
    position_events = [e for e in events if e.type == EventType.POSITION_UPDATED]
    assert len(position_events) == 1
