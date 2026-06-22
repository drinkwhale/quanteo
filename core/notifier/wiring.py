"""
Notifier ↔ EventBus 배선 유틸리티.

wire_notifier()를 호출하면 EventBus의 알림 대상 이벤트 타입을
Notifier로 자동 라우팅하는 핸들러가 등록된다.
"""

from __future__ import annotations

import logging

from core.events.bus import EventBus
from core.events.types import Event, EventType
from core.notifier.base import Notifier
from core.notifier.templates import event_to_notify

logger = logging.getLogger(__name__)

# 알림을 보낼 이벤트 타입 목록 (TICK/QUOTE/CANDLE 제외 — 고빈도)
_NOTIFY_TYPES: tuple[EventType, ...] = (
    EventType.SIGNAL,
    EventType.ORDER_SUBMITTED,
    EventType.ORDER_FILLED,
    EventType.ORDER_CANCELLED,
    EventType.ORDER_REJECTED,
    EventType.RISK_BREACH,
    EventType.KILL_SWITCH,
    EventType.ERROR,
    EventType.STATUS,
)


def wire_notifier(bus: EventBus, notifier: Notifier) -> None:
    """EventBus에 Notifier 라우팅 핸들러를 등록한다.

    bus.start() 호출 전에 이 함수를 실행해야 한다.
    등록된 핸들러는 Event를 templates.event_to_notify()로 변환한 뒤
    notifier.send()로 전달한다.

    Args:
        bus: 구독을 등록할 EventBus 인스턴스.
        notifier: 알림을 받을 Notifier 구현체.
    """
    async def _route(event: Event) -> None:
        notify_event = event_to_notify(event)
        if notify_event is None:
            return
        await notifier.send(notify_event)

    for event_type in _NOTIFY_TYPES:
        bus.subscribe(event_type, _route)

    logger.info(
        "Notifier 배선 완료 (%d 타입, notifier=%s)",
        len(_NOTIFY_TYPES),
        type(notifier).__name__,
    )
