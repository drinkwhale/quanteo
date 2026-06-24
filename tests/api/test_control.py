"""Control API /control/* 엔드포인트 테스트."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.api.deps import AppContainer
from core.events.bus import EventBus
from core.risk.manager import RiskManager
from core.risk.models import HaltLevel
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


def test_pause_sets_halt_level(client, container):
    res = client.post("/control/pause")
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert container.risk._halt == HaltLevel.PAUSE


def test_resume_clears_halt(client, container):
    container.risk._halt = HaltLevel.PAUSE
    res = client.post("/control/resume")
    assert res.status_code == 200
    assert container.risk._halt == HaltLevel.NONE


def test_kill_activates_kill_switch(client, container):
    res = client.post("/control/kill")
    assert res.status_code == 200
    assert container.risk._halt == HaltLevel.KILL


def test_pause_blocked_in_kill_state(client, container):
    """킬스위치 활성 상태에서는 pause 불가."""
    container.risk._halt = HaltLevel.KILL
    res = client.post("/control/pause")
    assert res.status_code == 409


def test_resume_blocked_in_kill_state(client, container):
    """킬스위치 활성 상태에서는 resume 불가."""
    container.risk._halt = HaltLevel.KILL
    res = client.post("/control/resume")
    assert res.status_code == 409
