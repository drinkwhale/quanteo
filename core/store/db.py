"""
SQLite DB 연결 및 초기화.

StateStore: 단일 aiosqlite 연결을 관리하는 컨텍스트 매니저.
재시작 복구용 메서드: get_open_positions(), get_pending_orders().
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from core.store.schema import ALL_TABLES, CREATE_INDEXES

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / "quanteo" / "data" / "quanteo.db"


# ---------------------------------------------------------------------------
# 복구 데이터 타입
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionSnapshot:
    """재시작 복구용 포지션 스냅샷.

    qty는 float — 해외주식은 소수점 단위 보유(fractional investing)가 가능하다.
    """

    symbol: str
    market: str
    env: str
    qty: float
    avg_price: float
    opened_at: str


@dataclass(frozen=True)
class PendingOrder:
    """재시작 복구용 미체결 주문 스냅샷.

    qty는 float — orders.qty가 REAL로 바뀌면서 해외주식 fractional
    investing 주문(OrderHistorySyncFeed가 Toss 앱에서 직접 낸 주문까지
    반영)도 이 스냅샷에 담길 수 있다. int로 두면 재시작 복구 로그에서
    소수점 수량이 0으로 잘려 "미체결 주문 없음"처럼 보이는 사고가 난다.
    """

    client_order_id: str
    symbol: str
    market: str
    env: str
    side: str
    qty: float
    status: str
    created_at: str
    broker_order_id: str | None = None


@dataclass(frozen=True)
class WatchlistEntry:
    """Stock Miner(Phase 16) 워치리스트 항목."""

    symbol: str
    name: str
    added_at: str
    source: str
    score_snapshot: dict


class StateStore:
    """quanteo 상태 저장소.

    Args:
        db_path: SQLite 파일 경로. `:memory:` 지정 시 인메모리 DB.
    """

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None:
        self.db_path = str(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        """DB 연결을 열고 스키마를 초기화한다."""
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        # WAL은 리더-라이터 블로킹을 줄여주지만 동시 쓰기(라이터끼리)는 여전히
        # 직렬화된다. busy_timeout 없이는 락 충돌 시 즉시 "database is locked"
        # 예외가 나므로, quanteo-core(주문 실행)와 quanteo-screener(워치리스트
        # 등록)가 별도 프로세스로 같은 DB 파일을 동시에 쓰는 배포 구성에서
        # 재시도 여유를 준다.
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._migrate()
        logger.info("StateStore 연결 완료: %s", self.db_path)

    async def close(self) -> None:
        """DB 연결을 닫는다."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _migrate(self) -> None:
        """테이블과 인덱스를 생성한다 (IF NOT EXISTS — 멱등)."""
        if self._conn is None:
            raise RuntimeError("StateStore가 열려 있지 않습니다. open()을 먼저 호출하세요.")
        for ddl in ALL_TABLES:
            await self._conn.execute(ddl)
        for idx in CREATE_INDEXES:
            await self._conn.execute(idx)
        await self._conn.commit()
        logger.debug("DB 마이그레이션 완료")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("StateStore가 열려 있지 않습니다. open()을 먼저 호출하세요.")
        return self._conn

    # ---------------------------------------------------------------------------
    # 재시작 복구 메서드
    # ---------------------------------------------------------------------------

    async def get_open_positions(self, env: str | None = None) -> list[PositionSnapshot]:
        """수량이 남아 있는 포지션을 반환한다.

        Args:
            env: 특정 환경만 필터. None이면 전체.

        Returns:
            PositionSnapshot 리스트.
        """
        if env:
            cursor = await self.conn.execute(
                "SELECT * FROM positions WHERE qty > 0 AND env = ? ORDER BY opened_at",
                (env,),
            )
        else:
            cursor = await self.conn.execute(
                "SELECT * FROM positions WHERE qty > 0 ORDER BY opened_at"
            )
        rows = await cursor.fetchall()
        return [
            PositionSnapshot(
                symbol=row["symbol"],
                market=row["market"],
                env=row["env"],
                qty=int(row["qty"]),
                avg_price=float(row["avg_price"]),
                opened_at=row["opened_at"],
            )
            for row in rows
        ]

    async def get_pending_orders(self, env: str | None = None) -> list[PendingOrder]:
        """미체결(pending/submitted/partial) 주문을 반환한다.

        Args:
            env: 특정 환경만 필터. None이면 전체.

        Returns:
            PendingOrder 리스트.
        """
        statuses = ("pending", "submitted", "partial")
        placeholders = ",".join("?" * len(statuses))

        if env:
            cursor = await self.conn.execute(
                f"SELECT * FROM orders WHERE status IN ({placeholders}) AND env = ? ORDER BY created_at",
                (*statuses, env),
            )
        else:
            cursor = await self.conn.execute(
                f"SELECT * FROM orders WHERE status IN ({placeholders}) ORDER BY created_at",
                statuses,
            )
        rows = await cursor.fetchall()
        return [
            PendingOrder(
                client_order_id=row["client_order_id"],
                symbol=row["symbol"],
                market=row["market"],
                env=row["env"],
                side=row["side"],
                qty=float(row["qty"]),
                status=row["status"],
                created_at=row["created_at"],
                broker_order_id=row["broker_order_id"],
            )
            for row in rows
        ]

    async def update_order_status(
        self,
        client_order_id: str,
        status: str,
        broker_order_id: str | None = None,
    ) -> None:
        """주문 상태를 갱신한다 (OrderExecutor·OrderSyncFeed 공용).

        호출 패턴이 둘로 나뉜다:
        - OrderExecutor: place_order() 직후 broker_order_id를 처음 채우면서
          'submitted'/'rejected'로 전이 (broker_order_id 전달).
        - OrderSyncFeed: 이미 broker_order_id가 채워진 주문의 상태만 브로커
          조회 결과로 갱신 (broker_order_id 생략, 기존 값 유지).

        Args:
            client_order_id: 대상 주문의 클라이언트 ID.
            status: 새 상태값.
            broker_order_id: 갱신할 브로커 주문 ID. None이면 기존 값 유지.
        """
        now = datetime.now(UTC).isoformat()
        if broker_order_id is not None:
            await self.conn.execute(
                "UPDATE orders SET status = ?, broker_order_id = ?, updated_at = ? WHERE client_order_id = ?",
                (status, broker_order_id, now, client_order_id),
            )
        else:
            await self.conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE client_order_id = ?",
                (status, now, client_order_id),
            )
        await self.conn.commit()

    async def upsert_broker_order(
        self,
        *,
        broker_order_id: str,
        client_order_id: str | None,
        symbol: str,
        market: str,
        side: str,
        order_type: str,
        qty: float,
        price: float,
        status: str,
        ordered_at: str,
    ) -> None:
        """브로커의 실제 주문 목록(list_orders)을 로컬 orders 테이블에 반영한다.

        OrderExecutor.submit()이 만든 행은 client_order_id로, 우리 봇이
        만들지 않은 주문(Toss 앱에서 직접 낸 주문 등)은 broker_order_id로
        기존 행을 찾는다 — Toss가 clientOrderId를 항상 되돌려주는 건 아니라
        broker_order_id가 더 신뢰할 수 있는 매칭 키다.

        기존 행이 없으면 새로 삽입한다. client_order_id 컬럼은 NOT NULL
        UNIQUE라 Toss가 clientOrderId를 안 주면 "toss-native-{broker_order_id}"로
        대신 채운다(이 값으로 "우리 봇이 만든 주문이 아님"을 구분할 수 있다).

        Args:
            broker_order_id: Toss 주문 ID (orderId).
            client_order_id: Toss가 되돌려준 clientOrderId. 없으면 None.
            symbol: 종목 코드.
            market: 'domestic' | 'overseas'.
            side: 'buy' | 'sell' (소문자).
            order_type: 'limit' | 'market' (소문자).
            qty: 주문 수량.
            price: 주문 가격.
            status: 로컬 status 값 ('pending'|'submitted'|'partial'|'filled'|'cancelled'|'rejected').
            ordered_at: 주문 생성 시각(ISO 8601) — 신규 삽입 시 created_at으로 사용.
        """
        now = datetime.now(UTC).isoformat()
        effective_client_id = client_order_id or f"toss-native-{broker_order_id}"

        cursor = await self.conn.execute(
            "SELECT client_order_id FROM orders WHERE client_order_id = ? OR broker_order_id = ?",
            (effective_client_id, broker_order_id),
        )
        row = await cursor.fetchone()

        if row is not None:
            await self.conn.execute(
                """
                UPDATE orders
                SET broker_order_id = ?, symbol = ?, market = ?, side = ?,
                    order_type = ?, qty = ?, price = ?, status = ?, updated_at = ?
                WHERE client_order_id = ?
                """,
                (
                    broker_order_id,
                    symbol,
                    market,
                    side,
                    order_type,
                    qty,
                    price,
                    status,
                    now,
                    row["client_order_id"],
                ),
            )
        else:
            await self.conn.execute(
                """
                INSERT INTO orders
                    (client_order_id, broker_order_id, symbol, market, env, side,
                     order_type, qty, price, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'prod', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    effective_client_id,
                    broker_order_id,
                    symbol,
                    market,
                    side,
                    order_type,
                    qty,
                    price,
                    status,
                    ordered_at,
                    now,
                ),
            )
        await self.conn.commit()

    # ---------------------------------------------------------------------------
    # 워치리스트 (Phase 16 — Stock Miner, bounded autonomy)
    # ---------------------------------------------------------------------------

    async def upsert_watchlist(
        self,
        symbol: str,
        name: str,
        score_snapshot: dict,
        source: str = "screener",
    ) -> None:
        """워치리스트에 종목을 등록한다 (이미 있으면 스냅샷·시각 갱신).

        사용자의 명시적 승인(인라인 버튼) 하에서만 호출되어야 한다 — 이
        메서드 자체는 자동 매매 경로와 연결되지 않는다(주문 실행 없음).
        """
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            INSERT INTO watchlist (symbol, name, added_at, source, score_snapshot)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name = excluded.name,
                added_at = excluded.added_at,
                score_snapshot = excluded.score_snapshot
            """,
            (symbol, name, now, source, json.dumps(score_snapshot, ensure_ascii=False)),
        )
        await self.conn.commit()

    async def get_watchlist(self) -> list[WatchlistEntry]:
        """전체 워치리스트를 등록일 순으로 반환한다."""
        cursor = await self.conn.execute("SELECT * FROM watchlist ORDER BY added_at")
        rows = await cursor.fetchall()
        return [
            WatchlistEntry(
                symbol=row["symbol"],
                name=row["name"],
                added_at=row["added_at"],
                source=row["source"],
                score_snapshot=json.loads(row["score_snapshot"]) if row["score_snapshot"] else {},
            )
            for row in rows
        ]

    async def __aenter__(self) -> StateStore:
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


@asynccontextmanager
async def get_store(db_path: str | Path = _DEFAULT_DB_PATH) -> AsyncIterator[StateStore]:
    """StateStore 컨텍스트 매니저 헬퍼."""
    store = StateStore(db_path)
    async with store:
        yield store
