"""
PositionSyncFeed — Toss 실계좌 보유 종목(holdings)을 로컬 positions 테이블과 동기화.

로컬 positions 테이블은 봇이 직접 체결시킨 주문 기록용으로 설계됐지만, 사용자가
앱에서 직접 매매한 종목이나 재시작 전 이력도 반영해야 대시보드가 실제 계좌 상태를
보여줄 수 있다. Toss 실계좌를 주기적으로 조회해 broker를 source of truth로 삼아
동기화한다.

읽기 전용 GET 호출이라 --with-trading 트레이딩 게이트와 무관하게 항상 동작해도
안전하다 (주문을 내지 않는다).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Protocol

from core.adapters.models import BalanceInfo
from core.store.db import StateStore

logger = logging.getLogger(__name__)


class _BalanceRestClient(Protocol):
    async def get_balance(self, symbol: str | None = None) -> BalanceInfo: ...


class PositionSyncFeed:
    """주기적으로 실계좌 잔고를 조회해 positions 테이블을 갱신한다.

    Args:
        rest_client: get_balance()를 제공하는 브로커 클라이언트.
        store: StateStore.
        env: positions 테이블의 env 컬럼 값 (Toss는 모의/실전 구분 없이 단일 환경).
        poll_interval: 조회 주기(초). 기본값 15초 — 체결처럼 실시간성이 중요하지
                       않은 정보라 시세 폴링(2초)보다 여유 있게 잡는다.
    """

    def __init__(
        self,
        rest_client: _BalanceRestClient,
        store: StateStore,
        env: str = "prod",
        poll_interval: float = 15.0,
    ) -> None:
        self._rest = rest_client
        self._store = store
        self._env = env
        self._poll_interval = poll_interval
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        """동기화 루프 실행 — stop()이 호출될 때까지 지속."""
        self._stop_event.clear()
        logger.info("포지션 동기화 시작 (interval=%.1fs)", self._poll_interval)

        while not self._stop_event.is_set():
            try:
                await self.sync_once()
            except Exception as exc:
                logger.warning("포지션 동기화 실패 (다음 주기에 재시도): %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
                break  # stop_event 수신 시 종료
            except TimeoutError:
                pass  # 정상 폴링 주기 완료, 계속 진행

        logger.info("포지션 동기화 종료")

    async def stop(self) -> None:
        """동기화 루프를 종료한다."""
        self._stop_event.set()

    async def sync_once(self) -> None:
        """실계좌 잔고를 1회 조회해 로컬 positions 테이블에 반영한다."""
        balance = await self._rest.get_balance()
        now = datetime.now(UTC).isoformat()
        live_symbols = {item.symbol for item in balance.items}

        for item in balance.items:
            await self._store.conn.execute(
                """
                INSERT INTO positions (symbol, market, env, qty, avg_price, opened_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, env) DO UPDATE SET
                    market = excluded.market,
                    qty = excluded.qty,
                    avg_price = excluded.avg_price,
                    updated_at = excluded.updated_at
                """,
                (item.symbol, item.market.value, self._env, item.qty, item.avg_price, now, now),
            )

        # 로컬엔 남아있지만 실계좌엔 더 이상 없는 종목 — 청산 처리 (qty=0)
        async with self._store.conn.execute(
            "SELECT symbol FROM positions WHERE env = ? AND qty > 0", (self._env,)
        ) as cursor:
            rows = await cursor.fetchall()
        stale = [row["symbol"] for row in rows if row["symbol"] not in live_symbols]
        for symbol in stale:
            await self._store.conn.execute(
                "UPDATE positions SET qty = 0, updated_at = ? WHERE symbol = ? AND env = ?",
                (now, symbol, self._env),
            )

        await self._store.conn.commit()
        logger.debug(
            "포지션 동기화 완료: %d종목 반영, %d종목 청산 처리",
            len(balance.items),
            len(stale),
        )
