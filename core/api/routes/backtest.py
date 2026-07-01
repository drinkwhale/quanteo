"""POST /backtest/run, GET /backtest/results/{run_id}, GET /backtest/status/{run_id}."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["백테스트"])

# 백테스트 결과 저장 DB
_DB_PATH = Path.home() / ".quanteo" / "backtest_runs.db"


# ============================================================================
# DB 초기화
# ============================================================================


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest_runs (
            run_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            result_json TEXT,
            error_msg TEXT
        )
        """
    )
    conn.commit()
    return conn


# ============================================================================
# 요청/응답 모델
# ============================================================================


class BacktestRunRequest(BaseModel):
    symbol: str
    start_date: str | None = None  # ISO 8601
    end_date: str | None = None
    strategy_params: dict[str, Any] = {}


class BacktestRunResponse(BaseModel):
    run_id: str
    status: str


class BacktestStatusResponse(BaseModel):
    run_id: str
    status: str  # "running" | "completed" | "failed"
    created_at: str
    completed_at: str | None = None
    error_msg: str | None = None


class BacktestResultResponse(BaseModel):
    run_id: str
    status: str
    metrics: dict[str, Any] | None = None
    trades_count: int = 0
    equity_curve: list[float] = []
    unfilled_signals_count: int = 0


# ============================================================================
# 엔드포인트
# ============================================================================


@router.post("/run", response_model=BacktestRunResponse, status_code=202)
async def run_backtest(
    req: BacktestRunRequest,
    background_tasks: BackgroundTasks,
) -> BacktestRunResponse:
    """백테스트를 비동기로 실행한다.

    요청 즉시 run_id를 반환하고, 백그라운드에서 실행한다.
    결과는 GET /backtest/results/{run_id}로 조회한다.
    """
    run_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO backtest_runs (run_id, symbol, start_date, end_date, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, req.symbol, req.start_date, req.end_date, "running", now),
        )
        conn.commit()
    finally:
        conn.close()

    background_tasks.add_task(_run_backtest_task, run_id, req)

    return BacktestRunResponse(run_id=run_id, status="running")


async def _run_backtest_task(run_id: str, req: BacktestRunRequest) -> None:
    """백그라운드 백테스트 실행."""
    import json
    import traceback

    conn = _get_conn()
    try:
        # 실제 백테스트는 데이터 소스·전략이 없으면 더미 결과 반환
        # 실제 연동은 container DI 패턴으로 확장 예정
        await asyncio.sleep(0.1)  # 비동기 yield

        dummy_result = {
            "metrics": {
                "win_rate": 0.0,
                "profit_loss_ratio": 0.0,
                "mdd": 0.0,
                "sharpe_ratio": 0.0,
                "total_trades": 0,
                "annualized_return": 0.0,
            },
            "trades_count": 0,
            "equity_curve": [],
            "unfilled_signals_count": 0,
        }

        now = datetime.now(UTC).isoformat()
        conn.execute(
            "UPDATE backtest_runs SET status=?, completed_at=?, result_json=? WHERE run_id=?",
            ("completed", now, json.dumps(dummy_result), run_id),
        )
        conn.commit()
        logger.info("백테스트 완료: run_id=%s", run_id)

    except Exception as e:
        tb = traceback.format_exc()
        logger.error("백테스트 실패: run_id=%s, error=%s\n%s", run_id, e, tb)
        now = datetime.now(UTC).isoformat()
        error_detail = f"{type(e).__name__}: {e}\n{tb}"
        conn.execute(
            "UPDATE backtest_runs SET status=?, completed_at=?, error_msg=? WHERE run_id=?",
            ("failed", now, error_detail, run_id),
        )
        conn.commit()
    finally:
        conn.close()


@router.get("/status/{run_id}", response_model=BacktestStatusResponse)
async def get_backtest_status(run_id: str) -> BacktestStatusResponse:
    """백테스트 실행 상태를 조회한다."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT run_id, status, created_at, completed_at, error_msg FROM backtest_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail=f"run_id {run_id} 없음")

    return BacktestStatusResponse(
        run_id=row[0],
        status=row[1],
        created_at=row[2],
        completed_at=row[3],
        error_msg=row[4],
    )


@router.get("/results/{run_id}", response_model=BacktestResultResponse)
async def get_backtest_results(run_id: str) -> BacktestResultResponse:
    """백테스트 결과를 조회한다."""
    import json

    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT run_id, status, result_json, error_msg FROM backtest_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail=f"run_id {run_id} 없음")

    run_id_val, status, result_json, error_msg = row

    if status == "running":
        return BacktestResultResponse(run_id=run_id_val, status="running")

    if status == "failed":
        raise HTTPException(status_code=500, detail=f"백테스트 실패: {error_msg}")

    if result_json is None:
        return BacktestResultResponse(run_id=run_id_val, status="completed")

    data = json.loads(result_json)
    return BacktestResultResponse(
        run_id=run_id_val,
        status="completed",
        metrics=data.get("metrics"),
        trades_count=data.get("trades_count", 0),
        equity_curve=data.get("equity_curve", []),
        unfilled_signals_count=data.get("unfilled_signals_count", 0),
    )
