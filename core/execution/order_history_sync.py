"""
OrderHistorySyncFeed — Toss 실계좌 주문 목록(list_orders)을 로컬 orders 테이블과 동기화.

배경: 로컬 orders 테이블은 원래 OrderExecutor.submit()이 우리 봇 자신이 낸
주문만 기록하는 용도로 설계됐다. 하지만 Toss는 모의투자 구분이 없는 단일
계좌라, 사용자가 Toss 앱에서 직접 낸 주문도 실제 계좌 상태의 일부다. 그리고
OrderExecutor.submit()은 현재 어떤 신호 파이프라인에도 연결돼 있지 않아
(StrategyEngine이 SIGNAL을 발행해도 이를 소비해 RiskManager.evaluate()·
executor.submit()을 호출하는 구독자가 없다), 로컬 DB만으로는 "주문내역"이
실제 계좌 상태를 반영하지 못한다.

이 피드는 Toss list_orders(status=OPEN/CLOSED)를 주기적으로 조회해 브로커를
source of truth로 삼아 orders 테이블을 채운다 (PositionSyncFeed가 positions에
대해 하는 일과 동일한 역할을 orders에 대해 수행).

읽기 전용 GET 호출만 수행하므로 --with-trading 게이트와 무관하게 항상 안전하게
동작한다 (주문을 내거나 취소하지 않는다).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal, Protocol

from core.adapters.toss.models import TossOrder
from core.events.bus import EventBus
from core.events.types import Event, EventType
from core.store.db import StateStore

logger = logging.getLogger(__name__)

_CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 3

# CLOSED 그룹 조회 시 페이지당 반환 건수 — 최초 백필 이후에는 최신 페이지만
# 확인하면 되므로(첫 페이지가 최신순), API 호출 비용을 억제하기 위해 적당히
# 넉넉한 값으로 고정한다.
_CLOSED_PAGE_LIMIT = 50

# 최초 백필 시 CLOSED 페이지네이션을 순회할 최대 횟수 — cursor 로직 이상으로
# 무한 루프에 빠지는 걸 막는 안전망. 페이지당 50건이면 최대 5,000건까지
# 백필한다(일반적인 계정 이력을 다 담기에 충분히 넉넉한 값).
_MAX_BACKFILL_PAGES = 100

# Toss 주문 상태 → 로컬 orders.status 매핑. CANCEL_REJECTED/REPLACE_REJECTED는
# "취소/정정 시도가 거부됐을 뿐 원주문 자체는 여전히 살아있다"는 뜻이라
# pending으로 취급한다 — order_sync.py의 _CLOSED_STATUS_MAP과 달리 여기서는
# OPEN 그룹 상태까지 전부 다뤄야 하므로 별도 테이블을 둔다.
_TOSS_STATUS_MAP: dict[str, str] = {
    "PENDING": "pending",
    "PENDING_CANCEL": "pending",
    "PENDING_REPLACE": "pending",
    "CANCEL_REJECTED": "pending",
    "REPLACE_REJECTED": "pending",
    "PARTIAL_FILLED": "partial",
    "FILLED": "filled",
    "CANCELED": "cancelled",
    "REJECTED": "rejected",
    "REPLACED": "cancelled",
}


class _OrderListRestClient(Protocol):
    async def list_orders(
        self,
        status: Literal["OPEN", "CLOSED"],
        symbol: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[TossOrder], str | None]: ...


class OrderHistorySyncFeed:
    """주기적으로 브로커 주문 목록을 조회해 orders 테이블 전체를 갱신한다.

    Args:
        rest_client: list_orders()를 제공하는 브로커 클라이언트.
        store: StateStore.
        poll_interval: 조회 주기(초). 기본 60초 — 체결 확인용 OrderSyncFeed(30초)
                       보다 여유 있게 잡는다 (전체 이력 재조회라 비용이 더 크다).
        bus: 동기화 실패 임계치 초과 시 이벤트를 발행할 EventBus. None이면 발행하지 않는다.
    """

    def __init__(
        self,
        rest_client: _OrderListRestClient,
        store: StateStore,
        poll_interval: float = 60.0,
        bus: EventBus | None = None,
    ) -> None:
        self._rest = rest_client
        self._store = store
        self._poll_interval = poll_interval
        self._bus = bus
        self._stop_event = asyncio.Event()
        self._consecutive_failures = 0
        # 최초 1회는 CLOSED 전체 이력을 끝까지 페이지네이션해 백필하고,
        # 이후 주기부터는 최신 페이지만 확인한다 — 매 주기 전체 이력을
        # 다시 훑으면 계정 개설 이후 전체 주문을 60초마다 재요청하게 되어
        # ORDER_HISTORY Rate Limit을 불필요하게 소모한다.
        self._closed_history_backfilled = False

    async def run(self) -> None:
        """동기화 루프 실행 — stop()이 호출될 때까지 지속."""
        self._stop_event.clear()
        logger.info("주문 이력 동기화 시작 (interval=%.1fs)", self._poll_interval)

        while not self._stop_event.is_set():
            try:
                count = await self.sync_once()
                logger.debug("주문 이력 동기화 완료: %d건 반영", count)
                self._consecutive_failures = 0
            except Exception as exc:
                self._consecutive_failures += 1
                logger.warning(
                    "주문 이력 동기화 실패 (%d회 연속, 다음 주기에 재시도): %s",
                    self._consecutive_failures,
                    exc,
                    exc_info=True,
                )
                if (
                    self._consecutive_failures == _CONSECUTIVE_FAILURE_ALERT_THRESHOLD
                    and self._bus is not None
                ):
                    await self._bus.publish(
                        Event(
                            type=EventType.ERROR,
                            payload={
                                "source": "order-history-sync",
                                "message": f"주문 이력 동기화가 {self._consecutive_failures}회 연속 실패했습니다: {exc}",
                            },
                            source="order-history-sync",
                        )
                    )

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
                break  # stop_event 수신 시 종료
            except TimeoutError:
                pass  # 정상 폴링 주기 완료, 계속 진행

        logger.info("주문 이력 동기화 종료")

    async def stop(self) -> None:
        """동기화 루프를 종료한다."""
        self._stop_event.set()

    async def sync_once(self) -> int:
        """OPEN(전량) + CLOSED(최초 1회는 전체, 이후엔 최근 페이지) 주문을 조회해
        로컬 orders 테이블에 반영한다.

        Returns:
            반영에 성공한 주문 건수.
        """
        open_orders, _ = await self._rest.list_orders(status="OPEN")

        if self._closed_history_backfilled:
            closed_orders, _ = await self._rest.list_orders(
                status="CLOSED", limit=_CLOSED_PAGE_LIMIT
            )
        else:
            closed_orders = await self._fetch_all_closed_orders()
            self._closed_history_backfilled = True

        reflected = 0
        for toss_order in (*open_orders, *closed_orders):
            try:
                if await self._upsert(toss_order):
                    reflected += 1
            except Exception as exc:
                # 개별 주문 반영 실패가 나머지 주문 처리를 막으면 안 된다
                # (order_sync.py와 동일한 부분 실패 격리 원칙).
                logger.error(
                    "주문 이력 반영 실패 (order_id=%s): %s",
                    toss_order.order_id,
                    exc,
                    exc_info=True,
                )
        return reflected

    async def _fetch_all_closed_orders(self) -> list[TossOrder]:
        """CLOSED 그룹 전체를 커서 끝까지 순회해 반환한다 (최초 백필 전용).

        _MAX_BACKFILL_PAGES를 넘기면 더 있어도 멈추고 경고를 남긴다 —
        조용히 잘라내면 "전체 이력을 다 받았다"고 착각하기 쉽다.
        """
        all_orders: list[TossOrder] = []
        cursor: str | None = None

        for _ in range(_MAX_BACKFILL_PAGES):
            page, cursor = await self._rest.list_orders(
                status="CLOSED", limit=_CLOSED_PAGE_LIMIT, cursor=cursor
            )
            all_orders.extend(page)
            if cursor is None:
                return all_orders

        logger.warning(
            "CLOSED 주문 백필이 최대 페이지 수(%d)에 도달해 중단됨 — %d건까지만 반영, 더 오래된 이력은 누락될 수 있음",
            _MAX_BACKFILL_PAGES,
            len(all_orders),
        )
        return all_orders

    async def _upsert(self, toss_order: TossOrder) -> bool:
        """단건을 로컬 orders 테이블에 반영한다.

        Returns:
            실제로 반영했으면 True, 알 수 없는 상태라 건너뛰었으면 False.
        """
        local_status = _TOSS_STATUS_MAP.get(toss_order.status)
        if local_status is None:
            logger.warning(
                "알 수 없는 Toss 주문 상태 — 반영 건너뜀 (order_id=%s, status=%s)",
                toss_order.order_id,
                toss_order.status,
            )
            return False

        await self._store.upsert_broker_order(
            broker_order_id=toss_order.order_id,
            client_order_id=toss_order.client_order_id,
            symbol=toss_order.symbol,
            market="domestic" if toss_order.currency == "KRW" else "overseas",
            side=toss_order.side.lower(),
            order_type=toss_order.order_type.lower(),
            qty=toss_order.quantity,
            price=float(toss_order.price) if toss_order.price is not None else 0.0,
            status=local_status,
            ordered_at=toss_order.ordered_at.isoformat(),
        )
        return True
