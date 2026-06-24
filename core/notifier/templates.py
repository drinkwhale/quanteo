"""
Notifier 메시지 템플릿.

core.events.types.Event를 core.notifier.base.NotifyEvent로 변환한다.
TICK / QUOTE / CANDLE처럼 고빈도 이벤트는 None을 반환해 알림을 생략한다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.events.types import Event, EventType
from core.notifier.base import NotifyEvent, NotifyLevel

# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _get(payload: Any, *keys: str, default: str = "-") -> str:
    """dict 또는 dataclass payload에서 첫 번째로 존재하는 값을 꺼낸다."""
    for key in keys:
        v = payload.get(key) if isinstance(payload, dict) else getattr(payload, key, None)
        if v is not None:
            return str(v)
    return default


def _fmt(payload: Any) -> str:
    """payload를 읽기 좋은 문자열로 변환한다."""
    if isinstance(payload, dict):
        return "\n".join(f"  {k}: {v}" for k, v in payload.items())
    return str(payload)


# ---------------------------------------------------------------------------
# 이벤트 타입별 변환 함수
# ---------------------------------------------------------------------------


def _signal(event: Event) -> NotifyEvent:
    p = event.payload
    symbol = _get(p, "symbol")
    direction = _get(p, "direction", "side")
    strategy = _get(p, "strategy", "strategy_id")
    return NotifyEvent(
        level=NotifyLevel.INFO,
        title=f"시그널 [{symbol}] {direction}",
        body=f"전략: {strategy}\n{_fmt(p)}",
        source=event.source,
        timestamp=event.timestamp,
    )


def _order_submitted(event: Event) -> NotifyEvent:
    p = event.payload
    symbol = _get(p, "symbol")
    side = _get(p, "side", "direction")
    qty = _get(p, "qty", "quantity")
    price = _get(p, "price", "order_price")
    return NotifyEvent(
        level=NotifyLevel.INFO,
        title=f"주문 접수 [{symbol}] {side} {qty}주",
        body=f"가격: {price}\n{_fmt(p)}",
        source=event.source,
        timestamp=event.timestamp,
    )


def _order_filled(event: Event) -> NotifyEvent:
    p = event.payload
    symbol = _get(p, "symbol")
    side = _get(p, "side", "direction")
    qty = _get(p, "fill_qty", "qty", "quantity")
    price = _get(p, "fill_price", "price")
    return NotifyEvent(
        level=NotifyLevel.INFO,
        title=f"체결 [{symbol}] {side} {qty}주 @ {price}",
        body=_fmt(p),
        source=event.source,
        timestamp=event.timestamp,
    )


def _order_cancelled(event: Event) -> NotifyEvent:
    p = event.payload
    symbol = _get(p, "symbol")
    reason = _get(p, "reason", "message")
    return NotifyEvent(
        level=NotifyLevel.WARNING,
        title=f"주문 취소 [{symbol}]",
        body=f"사유: {reason}\n{_fmt(p)}",
        source=event.source,
        timestamp=event.timestamp,
    )


def _order_rejected(event: Event) -> NotifyEvent:
    p = event.payload
    symbol = _get(p, "symbol")
    reason = _get(p, "reason", "message", "error")
    return NotifyEvent(
        level=NotifyLevel.ERROR,
        title=f"주문 거부 [{symbol}]",
        body=f"사유: {reason}\n{_fmt(p)}",
        source=event.source,
        timestamp=event.timestamp,
    )


def _risk_breach(event: Event) -> NotifyEvent:
    p = event.payload
    rule = _get(p, "rule", "limit_name", "check")
    value = _get(p, "value", "current")
    limit = _get(p, "limit", "threshold")
    return NotifyEvent(
        level=NotifyLevel.ERROR,
        title=f"리스크 한도 초과: {rule}",
        body=f"현재값: {value} / 한도: {limit}\n{_fmt(p)}",
        source=event.source,
        timestamp=event.timestamp,
    )


def _kill_switch(event: Event) -> NotifyEvent:
    p = event.payload
    reason = _get(p, "reason", "message")
    return NotifyEvent(
        level=NotifyLevel.CRITICAL,
        title="킬스위치 발동",
        body=f"사유: {reason}\n{_fmt(p)}",
        source=event.source,
        timestamp=event.timestamp,
    )


def _error(event: Event) -> NotifyEvent:
    p = event.payload
    message = _get(p, "message", "error", "msg")
    module = _get(p, "module", "source")
    return NotifyEvent(
        level=NotifyLevel.ERROR,
        title=f"시스템 오류: {module}",
        body=f"메시지: {message}\n{_fmt(p)}",
        source=event.source,
        timestamp=event.timestamp,
    )


def _status(event: Event) -> NotifyEvent:
    p = event.payload
    state = _get(p, "state", "status")
    detail = _get(p, "detail", "message")
    return NotifyEvent(
        level=NotifyLevel.INFO,
        title=f"시스템 상태: {state}",
        body=detail if detail != "-" else _fmt(p),
        source=event.source,
        timestamp=event.timestamp,
    )


# ---------------------------------------------------------------------------
# 디스패치 테이블
# ---------------------------------------------------------------------------

_TEMPLATES: dict[EventType, Callable[[Event], NotifyEvent]] = {
    EventType.SIGNAL: _signal,
    EventType.ORDER_SUBMITTED: _order_submitted,
    EventType.ORDER_FILLED: _order_filled,
    EventType.ORDER_CANCELLED: _order_cancelled,
    EventType.ORDER_REJECTED: _order_rejected,
    EventType.RISK_BREACH: _risk_breach,
    EventType.KILL_SWITCH: _kill_switch,
    EventType.ERROR: _error,
    EventType.STATUS: _status,
    # TICK / QUOTE / CANDLE: 고빈도 이벤트 — 알림 생략
}


def event_to_notify(event: Event) -> NotifyEvent | None:
    """Event를 NotifyEvent로 변환한다.

    고빈도 이벤트(TICK/QUOTE/CANDLE)는 None을 반환해 알림을 생략한다.

    Args:
        event: EventBus에서 수신한 이벤트.

    Returns:
        NotifyEvent 또는 None(알림 불필요한 이벤트 타입).
    """
    handler = _TEMPLATES.get(event.type)
    if handler is None:
        return None
    return handler(event)
