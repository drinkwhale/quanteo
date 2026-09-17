"""Control API /watchlist 엔드포인트 테스트 — StateStore의 watchlist 테이블 기반."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.api.deps import AppContainer
from core.events.bus import EventBus
from core.risk.manager import RiskManager
from core.store.db import StateStore


@pytest.fixture
async def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "test.db"))
    await s.open()
    yield s
    await s.close()


@pytest.fixture
def container(store):
    bus = EventBus()
    risk = RiskManager(bus=bus)
    # 브로커 없이도 /watchlist는 동작해야 한다 — StateStore만 읽는다.
    return AppContainer(store=store, risk=risk, bus=bus, env="vps", market="domestic")


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


def test_watchlist_empty_returns_200_with_empty_items(client):
    res = client.get("/watchlist")
    assert res.status_code == 200
    assert res.json() == {"items": []}


async def test_watchlist_returns_registered_entry(store, client):
    await store.upsert_watchlist(
        symbol="005930",
        name="삼성전자",
        score_snapshot={"growth": 4, "valuation": 2},
    )

    res = client.get("/watchlist")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["symbol"] == "005930"
    assert items[0]["name"] == "삼성전자"
    assert items[0]["source"] == "screener"
    assert items[0]["score_snapshot"] == {"growth": 4, "valuation": 2}
    assert items[0]["added_at"]


async def test_watchlist_orders_by_added_at(store, client):
    await store.upsert_watchlist(symbol="000660", name="SK하이닉스", score_snapshot={})
    await store.upsert_watchlist(symbol="005930", name="삼성전자", score_snapshot={})

    res = client.get("/watchlist")
    symbols = [item["symbol"] for item in res.json()["items"]]
    assert symbols == ["000660", "005930"]


async def test_watchlist_upsert_updates_existing_entry(store, client):
    await store.upsert_watchlist(symbol="005930", name="삼성전자", score_snapshot={"growth": 1})
    await store.upsert_watchlist(symbol="005930", name="삼성전자", score_snapshot={"growth": 5})

    res = client.get("/watchlist")
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["score_snapshot"] == {"growth": 5}
