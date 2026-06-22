"""
Event 타입 정의.

시스템 전체에서 Event Bus를 통해 교환되는 이벤트 타입.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventType(str, Enum):
    # 시세
    TICK = "tick"
    QUOTE = "quote"
    CANDLE = "candle"

    # 시그널
    SIGNAL = "signal"

    # 주문
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"

    # 리스크
    RISK_BREACH = "risk_breach"
    KILL_SWITCH = "kill_switch"

    # 시스템
    ERROR = "error"
    STATUS = "status"


@dataclass(frozen=True)
class Event:
    """버스를 통해 전달되는 이벤트."""

    type: EventType
    payload: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""
