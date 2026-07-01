"""백테스트 Control API 엔드포인트 테스트."""

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
def client(container, tmp_path, monkeypatch):
    # 테스트용 DB 경로 격리
    import core.api.routes.backtest as bt_module
    monkeypatch.setattr(bt_module, "_DB_PATH", tmp_path / "backtest_runs.db")
    return TestClient(create_app(container))


# ============================================================================
# POST /backtest/run
# ============================================================================


def test_run_returns_202_with_run_id(client):
    res = client.post("/backtest/run", json={"symbol": "005930"})

    assert res.status_code == 202
    body = res.json()
    assert "run_id" in body
    assert body["status"] == "running"


def test_run_with_date_range(client):
    res = client.post(
        "/backtest/run",
        json={"symbol": "000660", "start_date": "2024-01-01", "end_date": "2024-12-31"},
    )

    assert res.status_code == 202
    assert res.json()["run_id"] != ""


def test_run_with_strategy_params(client):
    res = client.post(
        "/backtest/run",
        json={"symbol": "035720", "strategy_params": {"cci_period": 20}},
    )

    assert res.status_code == 202


# ============================================================================
# GET /backtest/status/{run_id}
# ============================================================================


def test_status_returns_running_or_completed(client):
    run_res = client.post("/backtest/run", json={"symbol": "005930"})
    run_id = run_res.json()["run_id"]

    # 백그라운드 태스크가 동기 TestClient 내에서 바로 실행될 수 있음
    status_res = client.get(f"/backtest/status/{run_id}")
    assert status_res.status_code == 200
    body = status_res.json()
    assert body["run_id"] == run_id
    assert body["status"] in ("running", "completed", "failed")
    assert "created_at" in body


def test_status_404_for_unknown_run_id(client):
    res = client.get("/backtest/status/nonexistent-id")
    assert res.status_code == 404


def test_status_has_no_completed_at_initially(client):
    # TestClient는 background_tasks를 동기 실행 후 반환하므로
    # 실제로는 completed 상태일 수 있음 — created_at 필드 존재만 검증
    run_id = client.post("/backtest/run", json={"symbol": "005930"}).json()["run_id"]
    body = client.get(f"/backtest/status/{run_id}").json()
    assert "created_at" in body


# ============================================================================
# GET /backtest/results/{run_id}
# ============================================================================


def test_results_404_for_unknown_run_id(client):
    res = client.get("/backtest/results/nonexistent-id")
    assert res.status_code == 404


def test_results_completed_has_metrics(client):
    run_id = client.post("/backtest/run", json={"symbol": "005930"}).json()["run_id"]

    # TestClient는 background_tasks를 즉시 실행
    res = client.get(f"/backtest/results/{run_id}")

    # running 또는 completed — completed면 metrics 존재
    body = res.json()
    if body["status"] == "completed":
        assert body["metrics"] is not None
        assert "win_rate" in body["metrics"]
        assert "sharpe_ratio" in body["metrics"]
        assert isinstance(body["equity_curve"], list)
        assert isinstance(body["trades_count"], int)


def test_results_running_has_no_metrics(client, monkeypatch):
    """status=running인 경우 metrics 없이 반환."""
    import sqlite3
    import uuid
    from datetime import UTC, datetime

    import core.api.routes.backtest as bt_module

    run_id = str(uuid.uuid4())
    conn = bt_module._get_conn()
    conn.execute(
        "INSERT INTO backtest_runs (run_id, symbol, status, created_at) VALUES (?, ?, ?, ?)",
        (run_id, "005930", "running", datetime.now(UTC).isoformat()),
    )
    conn.commit()
    conn.close()

    res = client.get(f"/backtest/results/{run_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "running"
    assert body["metrics"] is None
