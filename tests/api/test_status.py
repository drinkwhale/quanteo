"""Control API /status 엔드포인트 테스트."""

from __future__ import annotations

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
    app = create_app(container)
    return TestClient(app)


def test_status_returns_200(client):
    res = client.get("/status")
    assert res.status_code == 200


def test_status_fields(client):
    data = client.get("/status").json()
    assert data["running"] is True
    assert data["halt_level"] == "none"
    assert data["env"] == "vps"
    assert data["market"] == "domestic"
    assert data["uptime_seconds"] >= 0
