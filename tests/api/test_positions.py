"""Control API /positions 엔드포인트 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.api.deps import AppContainer
from core.events.bus import EventBus
from core.risk.manager import RiskManager
from core.store.db import StateStore


@pytest.fixture
async def container(tmp_path):
    store = StateStore(db_path=str(tmp_path / "test.db"))
    await store.open()
    bus = EventBus()
    risk = RiskManager(bus=bus)
    c = AppContainer(store=store, risk=risk, bus=bus, env="vps", market="domestic")
    yield c
    await store.close()


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


def test_positions_empty(client):
    res = client.get("/positions")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.fixture
async def client_with_position(tmp_path):
    store = StateStore(db_path=str(tmp_path / "test.db"))
    await store.open()
    now = datetime.now(UTC).isoformat()
    await store.conn.execute(
        "INSERT INTO positions (symbol, market, env, qty, avg_price, opened_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("005930", "domestic", "vps", 10, 75000.0, now, now),
    )
    await store.conn.commit()

    bus = EventBus()
    risk = RiskManager(bus=bus)
    container = AppContainer(store=store, risk=risk, bus=bus, env="vps", market="domestic")
    client = TestClient(create_app(container))
    yield client
    await store.close()


def test_positions_with_data(client_with_position):
    res = client_with_position.get("/positions")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["symbol"] == "005930"
    assert item["qty"] == 10
    assert item["avg_price"] == 75000.0
    assert item["book_value"] == 750000.0
