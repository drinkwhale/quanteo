"""Control API /orders 엔드포인트 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

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


def _make_container(store):
    bus = EventBus()
    risk = RiskManager(bus=bus)
    return AppContainer(store=store, risk=risk, bus=bus, env="vps", market="domestic")


async def _insert_order(store: StateStore, status: str = "submitted") -> str:
    cid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    await store.conn.execute(
        "INSERT INTO orders (client_order_id, symbol, market, env, side, "
        "order_type, qty, price, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cid, "005930", "domestic", "vps", "buy", "market", 5, 0.0, status, now, now),
    )
    await store.conn.commit()
    return cid


def test_orders_empty(store):
    client = TestClient(create_app(_make_container(store)))
    res = client.get("/orders")
    assert res.status_code == 200
    assert res.json()["total"] == 0


@pytest.mark.asyncio
async def test_orders_with_data(store):
    await _insert_order(store, "submitted")
    await _insert_order(store, "filled")

    client = TestClient(create_app(_make_container(store)))
    data = client.get("/orders").json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_orders_status_filter(store):
    await _insert_order(store, "submitted")
    await _insert_order(store, "filled")

    client = TestClient(create_app(_make_container(store)))
    data = client.get("/orders?status=filled").json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "filled"


def test_orders_invalid_status(store):
    client = TestClient(create_app(_make_container(store)))
    res = client.get("/orders?status=unknown")
    assert res.status_code == 400
