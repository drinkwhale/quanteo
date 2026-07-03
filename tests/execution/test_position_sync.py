"""PositionSyncFeed — 실계좌 잔고 → 로컬 positions 테이블 동기화 테스트."""

from __future__ import annotations

import pytest

from core.adapters.models import BalanceInfo, BalanceItem
from core.config.settings import Market
from core.execution.position_sync import PositionSyncFeed
from core.store.db import StateStore


def _item(symbol: str, qty: int, avg_price: float, market: Market = Market.DOMESTIC) -> BalanceItem:
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
        return BalanceInfo(items=self._items, total_eval_amount=0.0, total_profit_loss=0.0, deposit=0.0)


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
