"""
OrderSyncFeed — 브로커 주문 상태를 로컬 orders 테이블과 동기화.

OrderExecutor.submit()은 주문을 브로커에 전송하고 'submitted'로 1회 기록할 뿐,
이후 체결·취소·거부 여부를 다시 확인하지 않는다. Toss는 주문 체결을 알려주는
WebSocket이 없으므로, 이 서브시스템이 없으면 로컬 DB 상태는 실제 브로커 상태와
무관하게 영원히 'submitted'로 남는다 (PositionSyncFeed가 포지션에 대해 하는 일을
주문에 대해서 하는 대응 모듈).

읽기 전용 GET 호출만 수행하므로 --with-trading 게이트와 무관하게 항상 안전하게
동작한다 (주문을 내거나 취소하지 않는다).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Protocol

from core.events.bus import EventBus
from core.events.types import Event, EventType
from core.store.db import StateStore

logger = logging.getLogger(__name__)

_CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 3

# Toss 주문 상태(CLOSED 그룹) → 로컬 orders.status 매핑.
# OPEN 그룹(PENDING/PARTIAL_FILLED/PENDING_CANCEL/PENDING_REPLACE)과
# CANCEL_REJECTED/REPLACE_REJECTED는 여기 없음 — 로컬 상태를 그대로 둔다
# (아직 종료되지 않았거나, 판단이 애매한 상태를 함부로 확정 짓지 않기 위함).
_CLOSED_STATUS_MAP: dict[str, str] = {
    "FILLED": "filled",
    "CANCELED": "cancelled",
    "REJECTED": "rejected",
    "REPLACED": "cancelled",
}

_EVENT_TYPE_MAP: dict[str, EventType] = {
    "filled": EventType.ORDER_FILLED,
    "cancelled": EventType.ORDER_CANCELLED,
    "rejected": EventType.ORDER_REJECTED,
}


class _TossOrderLike(Protocol):
    status: str


class _OrderRestClient(Protocol):
    async def get_order(self, order_id: str) -> _TossOrderLike: ...


class OrderSyncFeed:
    """주기적으로 미체결 주문의 브로커 상태를 조회해 orders 테이블을 갱신한다.

    Args:
        rest_client: get_order(order_id)를 제공하는 브로커 클라이언트.
        store: StateStore.
        env: 조회 대상 orders.env 값.
        poll_interval: 조회 주기(초). 기본 30초 — 체결 확인은 실시간성보다
                       주문량 대비 API 호출 비용을 우선한다.
        bus: 상태 전이 시 이벤트를 발행할 EventBus. None이면 발행하지 않는다.
    """

    def __init__(
        self,
        rest_client: _OrderRestClient,
        store: StateStore,
        env: str = "prod",
        poll_interval: float = 30.0,
        bus: EventBus | None = None,
    ) -> None:
        self._rest = rest_client
        self._store = store
        self._env = env
        self._poll_interval = poll_interval
        self._bus = bus
        self._stop_event = asyncio.Event()
        self._consecutive_failures = 0

    async def run(self) -> None:
        """동기화 루프 실행 — stop()이 호출될 때까지 지속."""
        self._stop_event.clear()
        logger.info("주문 상태 동기화 시작 (interval=%.1fs)", self._poll_interval)

        while not self._stop_event.is_set():
            try:
                await self.sync_once()
                self._consecutive_failures = 0
            except Exception as exc:
                self._consecutive_failures += 1
                logger.warning(
                    "주문 상태 동기화 실패 (%d회 연속, 다음 주기에 재시도): %s",
                    self._consecutive_failures,
                    exc,
                    exc_info=True,
                )
                if self._consecutive_failures == _CONSECUTIVE_FAILURE_ALERT_THRESHOLD and self._bus is not None:
                    await self._bus.publish(
                        Event(
                            type=EventType.ERROR,
                            payload={
                                "source": "order-sync",
                                "message": f"주문 상태 동기화가 {self._consecutive_failures}회 연속 실패했습니다: {exc}",
                            },
                            source="order-sync",
                        )
                    )

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)

        logger.info("주문 상태 동기화 종료")

    async def stop(self) -> None:
        """루프를 정상 종료한다."""
        self._stop_event.set()

    async def sync_once(self) -> None:
        """미체결 주문을 1회 순회하며 브로커 상태와 대조한다.

        개별 주문 조회가 실패해도 나머지 주문 처리는 계속한다 (부분 실패 격리) —
        `run()`의 상위 예외 처리는 전체 사이클 단위 재시도용이라, 여기서
        하나씩 잡지 않으면 앞쪽 주문 오류로 뒤쪽 주문 전체가 스킵된다.
        """
        pending = await self._store.get_pending_orders(env=self._env)

        for order in pending:
            if not order.broker_order_id:
                # place_order 응답을 아직 못 받은 주문 — 조회 대상 아님.
                continue

            try:
                toss_order = await self._rest.get_order(order.broker_order_id)
            except Exception as exc:
                logger.warning(
                    "주문 조회 실패 (client_order_id=%s, broker_order_id=%s): %s",
                    order.client_order_id,
                    order.broker_order_id,
                    exc,
                )
                continue

            new_status = _CLOSED_STATUS_MAP.get(toss_order.status)
            if new_status is None:
                # 여전히 OPEN 그룹이거나 판단이 애매한 상태 — 그대로 둔다.
                continue

            await self._store.update_order_status(order.client_order_id, new_status)
            logger.info(
                "주문 상태 갱신: %s %s → %s (broker_status=%s)",
                order.symbol,
                order.client_order_id,
                new_status,
                toss_order.status,
            )

            if self._bus is not None:
                event_type = _EVENT_TYPE_MAP[new_status]
                self._bus.publish_nowait(
                    Event(
                        type=event_type,
                        payload={
                            "client_order_id": order.client_order_id,
                            "broker_order_id": order.broker_order_id,
                            "symbol": order.symbol,
                            "status": new_status,
                        },
                        source="order-sync",
                    )
                )
