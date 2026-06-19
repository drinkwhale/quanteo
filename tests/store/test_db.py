"""StateStore — SQLite 스키마 초기화 테스트."""

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
