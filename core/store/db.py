"""
SQLite DB 연결 및 초기화.

StateStore: 단일 aiosqlite 연결을 관리하는 컨텍스트 매니저.
재시작 복구용 메서드: get_open_positions(), get_pending_orders().
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
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
    """재시작 복구용 포지션 스냅샷."""

    symbol: str
    market: str
    env: str
    qty: int
    avg_price: float
    opened_at: str


@dataclass(frozen=True)
class PendingOrder:
    """재시작 복구용 미체결 주문 스냅샷."""

    client_order_id: str
    symbol: str
    market: str
    env: str
    side: str
    qty: int
    status: str
    created_at: str


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
                qty=int(row["qty"]),
                status=row["status"],
                created_at=row["created_at"],
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
