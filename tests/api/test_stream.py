"""Control API /stream(WebSocket) 엔드포인트 테스트.

회귀 방지: `_get_container` 의존성이 `Request` 타입만 받으면 WebSocket 스코프에서
FastAPI가 인자를 채우지 못해 TypeError로 500이 발생한다 (HTTPConnection으로 수정됨).
"""

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
    return TestClient(create_app(container))


def test_stream_connects_and_sends_connected_message(client):
    with client.websocket_connect("/stream") as ws:
        msg = ws.receive_json()
        assert msg["event_type"] == "connected"
        assert "timestamp" in msg
