"""
SQLite 스키마 정의 및 마이그레이션.

테이블: positions, orders, fills, signals, settings, events_log
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

CREATE_POSITIONS = """
CREATE TABLE IF NOT EXISTS positions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    market      TEXT    NOT NULL CHECK(market IN ('domestic', 'overseas')),
    env         TEXT    NOT NULL CHECK(env IN ('prod', 'vps')),
    qty         INTEGER NOT NULL DEFAULT 0,
    avg_price   REAL    NOT NULL DEFAULT 0.0,
    opened_at   TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    UNIQUE(symbol, env)
)
"""

CREATE_ORDERS = """
CREATE TABLE IF NOT EXISTS orders (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    client_order_id  TEXT    NOT NULL UNIQUE,
    kis_order_id     TEXT,
    symbol           TEXT    NOT NULL,
    market           TEXT    NOT NULL,
    env              TEXT    NOT NULL,
    side             TEXT    NOT NULL CHECK(side IN ('buy', 'sell')),
    order_type       TEXT    NOT NULL DEFAULT 'market',
    qty              INTEGER NOT NULL,
    price            REAL    NOT NULL DEFAULT 0.0,
    status           TEXT    NOT NULL DEFAULT 'pending'
                             CHECK(status IN ('pending','submitted','partial','filled','cancelled','rejected')),
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
)
"""

CREATE_FILLS = """
CREATE TABLE IF NOT EXISTS fills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL REFERENCES orders(id),
    client_order_id TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    env             TEXT    NOT NULL,
    fill_qty        INTEGER NOT NULL,
    fill_price      REAL    NOT NULL,
    filled_at       TEXT    NOT NULL
)
"""

CREATE_SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    strategy    TEXT    NOT NULL,
    action      TEXT    NOT NULL CHECK(action IN ('buy','sell','hold')),
    confidence  REAL,
    metadata    TEXT,
    created_at  TEXT    NOT NULL
)
"""

CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT    PRIMARY KEY,
    value       TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
)
"""

CREATE_EVENTS_LOG = """
CREATE TABLE IF NOT EXISTS events_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    payload     TEXT,
    created_at  TEXT    NOT NULL
)
"""

# 인덱스
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_orders_symbol   ON orders(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_fills_order_id  ON fills(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_signals_symbol  ON signals(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_events_type     ON events_log(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_events_created  ON events_log(created_at)",
]

# 실행 순서 (FK 의존성 고려)
ALL_TABLES: list[str] = [
    CREATE_POSITIONS,
    CREATE_ORDERS,
    CREATE_FILLS,
    CREATE_SIGNALS,
    CREATE_SETTINGS,
    CREATE_EVENTS_LOG,
]
