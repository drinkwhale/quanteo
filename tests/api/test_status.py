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
    # info 서브시스템을 조립하지 않은 컨테이너는 기본값 False여야 한다.
    assert data["info_enabled"] is False


async def test_status_reports_info_enabled_when_wired(tmp_path):
    """AppContainer.info_enabled=True가 그대로 응답에 반영되는지 확인.

    core.app.run()이 InfoSystem 초기화 성공 여부를 여기로 흘려보내는데,
    라우트가 그 값을 무시하고 항상 기본값을 반환하는 회귀를 잡기 위한 테스트.
    """
    store = StateStore(db_path=str(tmp_path / "test.db"))
    await store.open()
    bus = EventBus()
    risk = RiskManager(bus=bus)
    container = AppContainer(
        store=store, risk=risk, bus=bus, env="vps", market="domestic", info_enabled=True
    )
    app = create_app(container)
    client = TestClient(app)

    data = client.get("/status").json()

    assert data["info_enabled"] is True

    await store.close()
