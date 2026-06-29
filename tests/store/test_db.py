"""StateStore — SQLite 스키마 초기화 및 CRUD 테스트."""

from __future__ import annotations

import pytest

from core.store.db import StateStore


@pytest.fixture
async def store():
    s = StateStore(":memory:")
    await s.open()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_open_creates_all_tables(store: StateStore):
    tables_q = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    async with store.conn.execute(tables_q) as cur:
        rows = await cur.fetchall()
    names = {r[0] for r in rows}
    expected = {"positions", "orders", "fills", "signals", "settings", "events_log"}
    assert expected.issubset(names)


@pytest.mark.asyncio
async def test_open_is_idempotent():
    """두 번 open해도 에러 없이 동작해야 한다 (IF NOT EXISTS)."""
    s = StateStore(":memory:")
    await s.open()
    await s._migrate()  # 재실행해도 에러 없음
    await s.close()


@pytest.mark.asyncio
async def test_context_manager():
    async with StateStore(":memory:") as store:
        assert store.conn is not None


@pytest.mark.asyncio
async def test_conn_raises_before_open():
    s = StateStore(":memory:")
    with pytest.raises(RuntimeError, match="open()"):
        _ = s.conn


# ---------------------------------------------------------------------------
# settings CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_and_select_settings(store: StateStore):
    now = "2026-06-19T00:00:00+00:00"
    await store.conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ("kill_switch", "false", now),
    )
    await store.conn.commit()

    async with store.conn.execute("SELECT value FROM settings WHERE key=?", ("kill_switch",)) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == "false"


# ---------------------------------------------------------------------------
# orders CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_and_select_order(store: StateStore):
    now = "2026-06-19T00:00:00+00:00"
    await store.conn.execute(
        """INSERT INTO orders
           (client_order_id, symbol, market, env, side, qty, price, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("ORD-001", "005930", "domestic", "prod", "buy", 10, 75000.0, now, now),
    )
    await store.conn.commit()

    async with store.conn.execute(
        "SELECT symbol, side, qty, status FROM orders WHERE client_order_id=?", ("ORD-001",)
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == "005930"
    assert row[1] == "buy"
    assert row[2] == 10
    assert row[3] == "pending"  # DEFAULT 값 확인


@pytest.mark.asyncio
async def test_order_status_update(store: StateStore):
    now = "2026-06-19T00:00:00+00:00"
    await store.conn.execute(
        """INSERT INTO orders
           (client_order_id, symbol, market, env, side, qty, price, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("ORD-002", "AAPL", "overseas", "prod", "sell", 5, 185.5, now, now),
    )
    await store.conn.execute(
        "UPDATE orders SET status=?, updated_at=? WHERE client_order_id=?",
        ("filled", now, "ORD-002"),
    )
    await store.conn.commit()

    async with store.conn.execute(
        "SELECT status FROM orders WHERE client_order_id=?", ("ORD-002",)
    ) as cur:
        row = await cur.fetchone()
    assert row[0] == "filled"


# ---------------------------------------------------------------------------
# positions CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_and_select_position(store: StateStore):
    now = "2026-06-19T00:00:00+00:00"
    await store.conn.execute(
        """INSERT INTO positions (symbol, market, env, qty, avg_price, opened_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("005930", "domestic", "prod", 10, 74000.0, now, now),
    )
    await store.conn.commit()

    async with store.conn.execute(
        "SELECT qty, avg_price FROM positions WHERE symbol=? AND env=?", ("005930", "prod")
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == 10
    assert row[1] == 74000.0


# ---------------------------------------------------------------------------
# fills CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_and_select_fill(store: StateStore):
    now = "2026-06-19T00:00:00+00:00"
    # orders FK를 위해 먼저 주문 삽입
    await store.conn.execute(
        """INSERT INTO orders
           (client_order_id, symbol, market, env, side, qty, price, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("ORD-003", "005930", "domestic", "prod", "buy", 10, 75000.0, now, now),
    )
    async with store.conn.execute("SELECT id FROM orders WHERE client_order_id=?", ("ORD-003",)) as cur:
        order_row = await cur.fetchone()
    order_id = order_row[0]

    await store.conn.execute(
        """INSERT INTO fills (order_id, client_order_id, symbol, env, fill_qty, fill_price, filled_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (order_id, "ORD-003", "005930", "prod", 10, 75000.0, now),
    )
    await store.conn.commit()

    async with store.conn.execute(
        "SELECT fill_qty, fill_price FROM fills WHERE order_id=?", (order_id,)
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == 10
    assert row[1] == 75000.0
