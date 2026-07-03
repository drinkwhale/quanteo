"""
PositionSyncFeed — Toss 실계좌 보유 종목(holdings)을 로컬 positions 테이블과 동기화.

로컬 positions 테이블은 봇이 직접 체결시킨 주문 기록용으로 설계됐지만, 사용자가
앱에서 직접 매매한 종목이나 재시작 전 이력도 반영해야 대시보드가 실제 계좌 상태를
보여줄 수 있다. Toss 실계좌를 주기적으로 조회해 broker를 source of truth로 삼아
동기화한다.

읽기 전용 GET 호출이라 --with-trading 트레이딩 게이트와 무관하게 항상 동작해도
안전하다 (주문을 내지 않는다).

변경분(신규/수량·평균단가 변동/청산)이 있으면 EventBus로 POSITION_UPDATED를
발행한다. 대시보드는 이 이벤트를 /stream(WebSocket)으로 즉시 받아 다음 폴링
주기(5초)를 기다리지 않고 바로 반영할 수 있다. 다만 브로커 조회 자체는 여전히
poll_interval 주기로만 일어나므로, 실제 체결과 동기화 사이의 지연은 그대로
남는다 — Toss가 WebSocket을 지원하지 않아 폴링 자체를 없앨 수는 없다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from core.adapters.models import BalanceInfo
from core.events.bus import EventBus
from core.events.types import Event, EventType
from core.store.db import StateStore

logger = logging.getLogger(__name__)

# 이 횟수만큼 연속으로 동기화가 실패하면 그냥 조용히 재시도만 하지 않고
# EventType.ERROR를 발행해 대시보드에 노출한다 (silent staleness 방지).
_CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 3

PositionChange = Literal["opened", "updated", "closed"]


class _BalanceRestClient(Protocol):
    async def get_balance(self, symbol: str | None = None) -> BalanceInfo: ...


@dataclass(frozen=True)
class PositionUpdate:
    """POSITION_UPDATED 이벤트 payload."""

    symbol: str
    market: str
    env: str
    qty: float
    avg_price: float
    book_value: float
    change: PositionChange


class PositionSyncFeed:
    """주기적으로 실계좌 잔고를 조회해 positions 테이블을 갱신한다.

    Args:
        rest_client: get_balance()를 제공하는 브로커 클라이언트.
        store: StateStore.
        env: positions 테이블의 env 컬럼 값 (Toss는 모의/실전 구분 없이 단일 환경).
        poll_interval: 조회 주기(초). 기본값 15초 — 체결처럼 실시간성이 중요하지
                       않은 정보라 시세 폴링(2초)보다 여유 있게 잡는다.
        bus: 변경 감지 시 POSITION_UPDATED를 발행할 EventBus. None이면 발행하지 않는다.
    """

    def __init__(
        self,
        rest_client: _BalanceRestClient,
        store: StateStore,
        env: str = "prod",
        poll_interval: float = 15.0,
        bus: EventBus | None = None,
    ) -> None:
        self._rest = rest_client
        self._store = store
        self._env = env
        self._poll_interval = poll_interval
        self._bus = bus
        self._stop_event = asyncio.Event()
        # sync_once()가 백그라운드 루프와 (미래의) 수동 새로고침 API 양쪽에서
        # 동시에 호출돼도 SELECT(이전 상태 조회) → INSERT/UPDATE 사이에
        # 경쟁 상태가 생기지 않도록 직렬화한다.
        self._sync_lock = asyncio.Lock()
        self._consecutive_failures = 0

    async def run(self) -> None:
        """동기화 루프 실행 — stop()이 호출될 때까지 지속."""
        self._stop_event.clear()
        logger.info("포지션 동기화 시작 (interval=%.1fs)", self._poll_interval)

        while not self._stop_event.is_set():
            try:
                await self.sync_once()
                self._consecutive_failures = 0
            except Exception as exc:
                self._consecutive_failures += 1
                logger.warning(
                    "포지션 동기화 실패 (%d회 연속, 다음 주기에 재시도): %s",
                    self._consecutive_failures,
                    exc,
                    exc_info=True,
                )
                if self._consecutive_failures == _CONSECUTIVE_FAILURE_ALERT_THRESHOLD and self._bus is not None:
                    await self._bus.publish(
                        Event(
                            type=EventType.ERROR,
                            payload={
                                "source": "position-sync",
                                "message": f"포지션 동기화가 {self._consecutive_failures}회 연속 실패했습니다: {exc}",
                            },
                            source="position-sync",
                        )
                    )
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
        """실계좌 잔고를 1회 조회해 로컬 positions 테이블에 반영한다.

        변경(신규/수량·평균단가 변동/청산)이 감지되면 POSITION_UPDATED를 발행한다.
        동시 호출 시에도 안전하도록 내부적으로 직렬화된다 (self._sync_lock).
        """
        async with self._sync_lock:
            await self._sync_once_locked()

    async def _sync_once_locked(self) -> None:
        balance = await self._rest.get_balance()
        now = datetime.now(UTC).isoformat()
        live_symbols = {item.symbol for item in balance.items}

        async with self._store.conn.execute(
            "SELECT symbol, market, qty, avg_price FROM positions WHERE env = ?", (self._env,)
        ) as cursor:
            before_rows = await cursor.fetchall()
        before = {row["symbol"]: (row["market"], row["qty"], row["avg_price"]) for row in before_rows}

        changes: list[PositionUpdate] = []
        change_type: PositionChange

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

            prev = before.get(item.symbol)
            if prev is None:
                change_type = "opened"
            elif prev[1] != item.qty or prev[2] != item.avg_price:
                change_type = "updated"
            else:
                continue  # 변화 없음 — 이벤트 발행 안 함
            changes.append(
                PositionUpdate(
                    symbol=item.symbol,
                    market=item.market.value,
                    env=self._env,
                    qty=item.qty,
                    avg_price=item.avg_price,
                    book_value=item.qty * item.avg_price,
                    change=change_type,
                )
            )

        # 로컬엔 남아있지만 실계좌엔 더 이상 없는 종목 — 청산 처리 (qty=0)
        stale = [(symbol, market) for symbol, (market, qty, _) in before.items() if qty > 0 and symbol not in live_symbols]
        for symbol, market in stale:
            await self._store.conn.execute(
                "UPDATE positions SET qty = 0, updated_at = ? WHERE symbol = ? AND env = ?",
                (now, symbol, self._env),
            )
            changes.append(
                PositionUpdate(
                    symbol=symbol, market=market, env=self._env, qty=0.0, avg_price=0.0, book_value=0.0, change="closed"
                )
            )

        await self._store.conn.commit()
        logger.debug(
            "포지션 동기화 완료: %d종목 반영, %d종목 청산 처리, %d건 변경 감지",
            len(balance.items),
            len(stale),
            len(changes),
        )

        if self._bus is not None:
            for change_item in changes:
                await self._bus.publish(
                    Event(type=EventType.POSITION_UPDATED, payload=change_item, source="position-sync")
                )
