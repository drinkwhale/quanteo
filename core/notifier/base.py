"""
Notifier — 기본 타입 & Protocol 정의.

모든 Notifier 구현체가 따르는 인터페이스와 공통 데이터 타입을 정의한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# 알림 레벨
# ---------------------------------------------------------------------------


class NotifyLevel(str, Enum):
    """알림 중요도 레벨 (낮음 → 높음 순)."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


_LEVEL_RANK: dict[NotifyLevel, int] = {
    NotifyLevel.DEBUG: 0,
    NotifyLevel.INFO: 1,
    NotifyLevel.WARNING: 2,
    NotifyLevel.ERROR: 3,
    NotifyLevel.CRITICAL: 4,
}


def level_rank(level: NotifyLevel) -> int:
    """레벨의 숫자 순위를 반환한다 (높을수록 중요)."""
    return _LEVEL_RANK[level]


# ---------------------------------------------------------------------------
# 알림 이벤트
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NotifyEvent:
    """Notifier로 전달되는 알림 이벤트."""

    level: NotifyLevel
    title: str
    body: str
    source: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Notifier Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Notifier(Protocol):
    """알림 전송기 인터페이스.

    모든 Notifier 구현체는 이 Protocol을 따라야 한다.
    """

    async def send(self, event: NotifyEvent) -> None:
        """알림 이벤트를 비동기로 전송한다."""
        ...

    async def run(self) -> None:
        """백그라운드 전송 루프를 시작한다 (asyncio.gather에 포함)."""
        ...

    async def stop(self) -> None:
        """전송 루프를 종료한다."""
        ...
