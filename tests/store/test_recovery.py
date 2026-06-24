"""StateStore 재시작 복구 메서드 테스트."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from core.store.db import PendingOrder, PositionSnapshot, StateStore


@pytest.fixture
async def store():
    """인메모리 StateStore 픽스처."""
    s = StateStore(":memory:")
    await s.open()
    yield s
    await s.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _insert_position(store: StateStore, symbol: str, qty: int, env: str = "vps") -> None:
    now = _now()
    await store.conn.execute(
        "INSERT INTO positions (symbol, market, env, qty, avg_price, opened_at, updated_at) "
        "VALUES (?, 'domestic', ?, ?, 75000.0, ?, ?)",
        (symbol, env, qty, now, now),
    )
    await store.conn.commit()


async def _insert_order(store: StateStore, symbol: str, status: str, env: str = "vps") -> None:
    now = _now()
    await store.conn.execute(
        "INSERT INTO orders (client_order_id, symbol, market, env, side, qty, status, created_at, updated_at) "
        "VALUES (?, ?, 'domestic', ?, 'buy', 10, ?, ?, ?)",
        (f"coid-{symbol}-{status}", symbol, env, status, now, now),
    )
    await store.conn.commit()


# ---------------------------------------------------------------------------
# get_open_positions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_open_positions_returns_nonzero_qty(store: StateStore):
    await _insert_position(store, "005930", qty=10)
    await _insert_position(store, "000660", qty=0)  # 청산된 포지션 — 제외돼야 함

    result = await store.get_open_positions()
    symbols = [r.symbol for r in result]

    assert "005930" in symbols
    assert "000660" not in symbols


@pytest.mark.asyncio
async def test_get_open_positions_returns_position_snapshot_type(store: StateStore):
    """반환 타입이 PositionSnapshot 이어야 한다."""
    await _insert_position(store, "005930", qty=5)

    result = await store.get_open_positions()

    assert len(result) == 1
    assert isinstance(result[0], PositionSnapshot)
    assert result[0].symbol == "005930"
    assert result[0].qty == 5
    assert result[0].avg_price == 75000.0


@pytest.mark.asyncio
async def test_get_open_positions_filters_by_env(store: StateStore):
    await _insert_position(store, "005930", qty=5, env="vps")
    await _insert_position(store, "000660", qty=3, env="prod")

    vps_result = await store.get_open_positions(env="vps")
    prod_result = await store.get_open_positions(env="prod")

    assert len(vps_result) == 1
    assert vps_result[0].symbol == "005930"

    assert len(prod_result) == 1
    assert prod_result[0].symbol == "000660"


@pytest.mark.asyncio
async def test_get_open_positions_empty(store: StateStore):
    result = await store.get_open_positions()
    assert result == []


# ---------------------------------------------------------------------------
# get_pending_orders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pending_orders_returns_correct_statuses(store: StateStore):
    for status in ("pending", "submitted", "partial"):
        await _insert_order(store, f"stock-{status}", status)

    for status in ("filled", "cancelled", "rejected"):
        await _insert_order(store, f"stock-{status}", status)

    result = await store.get_pending_orders()
    statuses = {r.status for r in result}

    assert statuses == {"pending", "submitted", "partial"}


@pytest.mark.asyncio
async def test_get_pending_orders_returns_pending_order_type(store: StateStore):
    """반환 타입이 PendingOrder 이어야 한다."""
    await _insert_order(store, "005930", "pending")

    result = await store.get_pending_orders()

    assert len(result) == 1
    assert isinstance(result[0], PendingOrder)
    assert result[0].symbol == "005930"
    assert result[0].status == "pending"
    assert result[0].side == "buy"


@pytest.mark.asyncio
async def test_get_pending_orders_filters_by_env(store: StateStore):
    await _insert_order(store, "005930", "pending", env="vps")
    await _insert_order(store, "000660", "submitted", env="prod")

    vps_result = await store.get_pending_orders(env="vps")

    assert len(vps_result) == 1
    assert vps_result[0].env == "vps"


@pytest.mark.asyncio
async def test_get_pending_orders_empty(store: StateStore):
    result = await store.get_pending_orders()
    assert result == []


# ---------------------------------------------------------------------------
# 복합 시나리오
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_state_scenario(store: StateStore):
    """재시작 후 포지션·주문 모두 정확히 복원되는 시나리오."""
    await _insert_position(store, "005930", qty=10, env="vps")
    await _insert_position(store, "000660", qty=0, env="vps")  # 청산 — 제외
    await _insert_order(store, "005930", "submitted", env="vps")
    await _insert_order(store, "000660", "filled", env="vps")  # 체결 — 제외

    positions = await store.get_open_positions(env="vps")
    orders = await store.get_pending_orders(env="vps")

    assert len(positions) == 1
    assert positions[0].symbol == "005930"

    assert len(orders) == 1
    assert orders[0].symbol == "005930"
    assert orders[0].status == "submitted"


# ---------------------------------------------------------------------------
# _log_persisted_state 통합
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_persisted_state_logs_positions_and_orders(store: StateStore, caplog):
    """_log_persisted_state() 가 포지션·미체결 주문을 로그에 출력한다."""
    from core.app import _log_persisted_state

    await _insert_position(store, "005930", qty=10, env="vps")
    await _insert_order(store, "005930", "submitted", env="vps")

    with caplog.at_level(logging.INFO, logger="core.app"):
        await _log_persisted_state(store, "vps")

    assert "오픈 포지션 1개" in caplog.text
    assert "미체결 주문 1개" in caplog.text


@pytest.mark.asyncio
async def test_log_persisted_state_handles_db_error_gracefully(store: StateStore, caplog):
    """DB 오류 시 예외 없이 경고 로그를 남기고 계속한다."""
    from core.app import _log_persisted_state

    # get_open_positions 에서 예외 발생을 시뮬레이션
    with (
        patch.object(store, "get_open_positions", side_effect=RuntimeError("DB 손상")),
        caplog.at_level(logging.WARNING, logger="core.app"),
    ):
        # 예외가 전파되지 않아야 한다
        await _log_persisted_state(store, "vps")

    assert "DB를 확인하세요" in caplog.text
    assert "빈 상태에서 시작" in caplog.text
