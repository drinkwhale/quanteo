"""
MockNotifier — 테스트용 알림 전송기.

실제 Telegram API 호출 없이 전송된 이벤트를 메모리에 누적한다.
"""

from __future__ import annotations

import asyncio
import logging

from core.notifier.base import NotifyEvent, NotifyLevel, level_rank

logger = logging.getLogger(__name__)


class MockNotifier:
    """테스트·개발용 더미 Notifier.

    send()로 수신한 이벤트를 sent_events 리스트에 누적한다.
    Notifier Protocol을 완전히 구현하므로 TelegramNotifier 대체재로 사용 가능.

    Args:
        min_level: 이 레벨 이상의 이벤트만 누적한다. 기본값 DEBUG (전부).
    """

    def __init__(self, min_level: NotifyLevel = NotifyLevel.DEBUG) -> None:
        self._min_level = min_level
        self._running = False
        self.sent_events: list[NotifyEvent] = []

    # ------------------------------------------------------------------
    # Notifier Protocol 구현
    # ------------------------------------------------------------------

    async def send(self, event: NotifyEvent) -> None:
        """이벤트를 sent_events에 추가한다."""
        if level_rank(event.level) < level_rank(self._min_level):
            return
        self.sent_events.append(event)
        logger.debug("MockNotifier 수신: [%s] %s", event.level, event.title)

    async def run(self) -> None:
        """더미 루프 — asyncio.gather 호환을 위해 존재한다."""
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    async def stop(self) -> None:
        """루프를 종료한다."""
        self._running = False

    # ------------------------------------------------------------------
    # 테스트 헬퍼
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """누적된 이벤트를 초기화한다."""
        self.sent_events.clear()

    def events_by_level(self, level: NotifyLevel) -> list[NotifyEvent]:
        """특정 레벨의 이벤트만 필터링해서 반환한다."""
        return [e for e in self.sent_events if e.level == level]

    @property
    def count(self) -> int:
        """수신한 이벤트 수."""
        return len(self.sent_events)
