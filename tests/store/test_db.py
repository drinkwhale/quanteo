"""StateStore — SQLite 스키마 초기화 및 CRUD 테스트."""

from __future__ import annotations

import pytest

from core.store.db import StateStore, WatchlistEntry


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

    async with store.conn.execute(
        "SELECT value FROM settings WHERE key=?", ("kill_switch",)
    ) as cur:
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
    async with store.conn.execute(
        "SELECT id FROM orders WHERE client_order_id=?", ("ORD-003",)
    ) as cur:
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


# ---------------------------------------------------------------------------
# upsert_broker_order — OrderHistorySyncFeed 전용
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_broker_order_finds_existing_row_by_broker_order_id_only(store: StateStore):
    """client_order_id가 다시 채워져도(예: Toss가 뒤늦게 clientOrderId를 되돌려줌)
    broker_order_id만으로 기존 행을 찾아 갱신해야 한다 — 중복 삽입되면 안 된다.

    시나리오: 처음엔 clientOrderId 없이 들어와 toss-native-{orderId}로 저장됐다가,
    이후 조회에서 진짜 clientOrderId가 붙어 들어와도 여전히 broker_order_id로
    같은 행을 찾아야 한다(effective_client_id가 바뀌어도 SELECT의 OR 조건이
    broker_order_id로 커버한다).
    """
    await store.upsert_broker_order(
        broker_order_id="toss-999",
        client_order_id=None,  # Toss 앱에서 직접 낸 주문 — clientOrderId 없음
        symbol="005930",
        market="domestic",
        side="buy",
        order_type="limit",
        qty=10,
        price=75000.0,
        status="pending",
        ordered_at="2026-07-01T00:00:00+00:00",
    )

    # 두 번째 조회에서는 진짜 clientOrderId가 붙어 들어옴 + 상태도 바뀜
    await store.upsert_broker_order(
        broker_order_id="toss-999",
        client_order_id="real-client-id",
        symbol="005930",
        market="domestic",
        side="buy",
        order_type="limit",
        qty=10,
        price=75000.0,
        status="filled",
        ordered_at="2026-07-01T00:00:00+00:00",
    )

    async with store.conn.execute(
        "SELECT COUNT(*) FROM orders WHERE broker_order_id = ?", ("toss-999",)
    ) as cur:
        (total,) = await cur.fetchone()
    assert total == 1  # 중복 삽입 안 됨

    async with store.conn.execute(
        "SELECT client_order_id, status FROM orders WHERE broker_order_id = ?", ("toss-999",)
    ) as cur:
        row = await cur.fetchone()
    # 최초 삽입 시 만든 client_order_id가 식별자로 유지된다 — 매 조회마다
    # Toss가 다른 clientOrderId를 되돌려줘도 같은 행을 계속 갱신해야 하므로.
    assert row["client_order_id"] == "toss-native-toss-999"
    assert row["status"] == "filled"


@pytest.mark.asyncio
async def test_upsert_broker_order_preserves_fractional_qty(store: StateStore):
    """해외주식 fractional investing 수량이 저장 과정에서 잘리지 않아야 한다."""
    await store.upsert_broker_order(
        broker_order_id="toss-frac-1",
        client_order_id=None,
        symbol="AAPL",
        market="overseas",
        side="sell",
        order_type="market",
        qty=0.000151,
        price=185.5,
        status="filled",
        ordered_at="2026-07-10T00:00:00+00:00",
    )

    async with store.conn.execute(
        "SELECT qty FROM orders WHERE broker_order_id = ?", ("toss-frac-1",)
    ) as cur:
        row = await cur.fetchone()

    assert row["qty"] == pytest.approx(0.000151)


@pytest.mark.asyncio
async def test_upsert_watchlist_inserts_new_entry(store: StateStore):
    await store.upsert_watchlist(
        symbol="005930", name="삼성전자", score_snapshot={"growth": 4, "valuation": 3}
    )

    entries = await store.get_watchlist()

    assert len(entries) == 1
    assert entries[0] == WatchlistEntry(
        symbol="005930",
        name="삼성전자",
        added_at=entries[0].added_at,
        source="screener",
        score_snapshot={"growth": 4, "valuation": 3},
    )


@pytest.mark.asyncio
async def test_upsert_watchlist_updates_existing_entry(store: StateStore):
    await store.upsert_watchlist(symbol="005930", name="삼성전자", score_snapshot={"growth": 2})
    await store.upsert_watchlist(symbol="005930", name="삼성전자", score_snapshot={"growth": 5})

    entries = await store.get_watchlist()

    assert len(entries) == 1  # UNIQUE(symbol) — 갱신이지 중복 삽입이 아님
    assert entries[0].score_snapshot == {"growth": 5}


@pytest.mark.asyncio
async def test_get_watchlist_empty_by_default(store: StateStore):
    entries = await store.get_watchlist()

    assert entries == []
