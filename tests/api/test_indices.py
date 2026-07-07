"""Control API /indices 엔드포인트 테스트 — 외부 API는 모킹, 실제 네트워크 호출 없음."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.api.deps import AppContainer
from core.events.bus import EventBus
from core.marketdata.index_quotes import IndexQuote
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
    # 브로커 없이도 /indices는 동작해야 한다 — Toss 인증과 무관한 외부 조회.
    return AppContainer(store=store, risk=risk, bus=bus, env="vps", market="domestic")


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


def test_indices_returns_200(client, monkeypatch):
    monkeypatch.setattr(
        "core.api.routes.indices.get_index_quotes",
        AsyncMock(
            return_value=[
                IndexQuote(
                    key="kospi",
                    label="코스피",
                    price=8051.33,
                    change=-37.01,
                    change_rate=-0.0045,
                    currency="KRW",
                ),
            ]
        ),
    )
    res = client.get("/indices")
    assert res.status_code == 200


def test_indices_item_fields(client, monkeypatch):
    monkeypatch.setattr(
        "core.api.routes.indices.get_index_quotes",
        AsyncMock(
            return_value=[
                IndexQuote(
                    key="nasdaq",
                    label="나스닥",
                    price=25832.67,
                    change=-207.36,
                    change_rate=-0.0079,
                    currency="USD",
                ),
            ]
        ),
    )
    data = client.get("/indices").json()
    item = data["items"][0]
    assert item["key"] == "nasdaq"
    assert item["label"] == "나스닥"
    assert item["price"] == 25832.67
    assert item["change_rate"] == -0.0079


def test_indices_502_on_failure(client, monkeypatch):
    monkeypatch.setattr(
        "core.api.routes.indices.get_index_quotes",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    res = client.get("/indices")
    assert res.status_code == 502
