"""Control API /watchlist 엔드포인트 테스트 — 실제 파일시스템 대신 tmp_path 사용."""

from __future__ import annotations

import json

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
    # 브로커 없이도 /watchlist는 동작해야 한다 — screener 파일 결과물만 읽는다.
    return AppContainer(store=store, risk=risk, bus=bus, env="vps", market="domestic")


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


def _write_watchlist(tmp_path, monkeypatch, filename: str, content):
    watchlist_dir = tmp_path / "watchlist"
    watchlist_dir.mkdir(exist_ok=True)
    (watchlist_dir / filename).write_text(
        json.dumps(content, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr("core.api.routes.watchlist._WATCHLIST_DIR", watchlist_dir)


def test_watchlist_404_when_no_files(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "core.api.routes.watchlist._WATCHLIST_DIR", tmp_path / "empty"
    )
    res = client.get("/watchlist")
    assert res.status_code == 404


def test_watchlist_returns_latest_file(client, monkeypatch, tmp_path):
    older = [
        {
            "ticker": "000001",
            "name": "구버전종목",
            "market_cap_billion": 100.0,
            "asset_growth_pct": 1.0,
            "oi_growth_pct": 1.0,
            "revenue_growth_pct": 1.0,
        }
    ]
    newer = [
        {
            "ticker": "005930",
            "name": "삼성전자",
            "market_cap_billion": 500.0,
            "asset_growth_pct": 12.3,
            "oi_growth_pct": 4.5,
            "revenue_growth_pct": 6.7,
        }
    ]
    _write_watchlist(tmp_path, monkeypatch, "watchlist_2026-08-30.json", older)
    _write_watchlist(tmp_path, monkeypatch, "watchlist_2026-08-31.json", newer)

    res = client.get("/watchlist")
    assert res.status_code == 200
    data = res.json()
    assert data["date"] == "2026-08-31"
    assert data["items"] == newer


def test_watchlist_502_on_corrupted_file(client, monkeypatch, tmp_path):
    watchlist_dir = tmp_path / "watchlist"
    watchlist_dir.mkdir()
    (watchlist_dir / "watchlist_2026-08-31.json").write_text(
        "not valid json", encoding="utf-8"
    )
    monkeypatch.setattr("core.api.routes.watchlist._WATCHLIST_DIR", watchlist_dir)

    res = client.get("/watchlist")
    assert res.status_code == 502
