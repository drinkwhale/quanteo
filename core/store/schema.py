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
    env         TEXT    NOT NULL DEFAULT 'prod',
    -- REAL: 해외주식(미국)은 Toss에서 소수점 단위 매매(fractional investing)를
    -- 지원해 정수가 아닐 수 있다. SQLite는 컬럼 타입과 무관하게 REAL 값을
    -- 그대로 저장하므로(type affinity), 기존 DB에도 안전하게 적용된다.
    qty         REAL    NOT NULL DEFAULT 0.0,
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
    broker_order_id  TEXT,
    symbol           TEXT    NOT NULL,
    market           TEXT    NOT NULL,
    env              TEXT    NOT NULL,
    side             TEXT    NOT NULL CHECK(side IN ('buy', 'sell')),
    order_type       TEXT    NOT NULL DEFAULT 'market',
    -- REAL: positions.qty와 동일한 이유 — 해외주식 fractional investing 주문은
    -- 수량이 정수가 아닐 수 있다. SQLite는 컬럼 타입과 무관하게 REAL 값을
    -- 그대로 저장하므로(type affinity), 기존 DB에도 안전하게 적용된다.
    qty              REAL    NOT NULL,
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

# Phase 16 — Stock Miner 워치리스트 (bounded autonomy: 사용자 승인 시에만 기록)
CREATE_WATCHLIST = """
CREATE TABLE IF NOT EXISTS watchlist (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    name            TEXT    NOT NULL DEFAULT '',
    added_at        TEXT    NOT NULL,
    source          TEXT    NOT NULL DEFAULT 'screener' CHECK(source IN ('screener')),
    score_snapshot  TEXT,
    UNIQUE(symbol)
)
"""

# Phase 17 — 마켓 데이터 수집 (거래대금/거래량 기준 종목 모니터링)
CREATE_MARKET_DATA = """
CREATE TABLE IF NOT EXISTS market_data (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    price           REAL    NOT NULL,
    change_rate     REAL    NOT NULL,
    trading_volume  BIGINT  NOT NULL,
    trading_value   BIGINT  NOT NULL,
    market_cap      BIGINT,
    timestamp       TEXT    NOT NULL,
    UNIQUE(symbol, timestamp)
)
"""

CREATE_ACTIVE_SYMBOLS = """
CREATE TABLE IF NOT EXISTS active_symbols (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL UNIQUE,
    last_seen   TEXT    NOT NULL
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
    "CREATE INDEX IF NOT EXISTS idx_watchlist_symbol ON watchlist(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_market_data_symbol ON market_data(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_market_data_timestamp ON market_data(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_market_data_value ON market_data(trading_value)",
]

# 실행 순서 (FK 의존성 고려)
ALL_TABLES: list[str] = [
    CREATE_POSITIONS,
    CREATE_ORDERS,
    CREATE_FILLS,
    CREATE_SIGNALS,
    CREATE_SETTINGS,
    CREATE_EVENTS_LOG,
    CREATE_WATCHLIST,
    CREATE_MARKET_DATA,
    CREATE_ACTIVE_SYMBOLS,
]
