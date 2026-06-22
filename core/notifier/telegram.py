"""
TelegramNotifier — aiogram v3 기반 Telegram 알림 전송기.

asyncio.Queue 기반 버퍼 + rate limit으로 메시지를 순차 전송한다.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from core.notifier.base import NotifyEvent, NotifyLevel, level_rank

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram 알림 전송기.

    aiogram v3 Bot을 사용해 지정된 chat_id로 메시지를 전송한다.
    asyncio.Queue 기반 버퍼와 rate limit으로 Telegram API 제한을 준수한다.

    Args:
        bot_token: Telegram Bot API 토큰.
        chat_id: 메시지를 받을 채팅 ID.
        min_level: 이 레벨 이상의 이벤트만 전송한다. 기본값 INFO.
        rate_limit: 초당 최대 전송 횟수. 기본값 1.0 (Telegram 권장).
        queue_maxsize: 전송 버퍼 최대 크기. 초과 시 드롭.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        min_level: NotifyLevel = NotifyLevel.INFO,
        rate_limit: float = 1.0,
        queue_maxsize: int = 100,
    ) -> None:
        self._bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self._chat_id = chat_id
        self._min_level = min_level
        self._rate_limit = rate_limit
        self._queue: asyncio.Queue[NotifyEvent] = asyncio.Queue(maxsize=queue_maxsize)
        self._running = False

    # ------------------------------------------------------------------
    # Notifier Protocol 구현
    # ------------------------------------------------------------------

    async def send(self, event: NotifyEvent) -> None:
        """이벤트를 전송 큐에 넣는다. 레벨 미달·큐 포화 시 드롭."""
        if level_rank(event.level) < level_rank(self._min_level):
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "TelegramNotifier 큐 포화 — 이벤트 드롭 (level=%s title=%s)",
                event.level,
                event.title,
            )

    async def run(self) -> None:
        """전송 루프: 큐에서 이벤트를 꺼내 Telegram으로 전송한다."""
        self._running = True
        logger.info("TelegramNotifier 시작 (chat_id=%s)", self._chat_id)
        try:
            while self._running:
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                await self._send_message(event)
                self._queue.task_done()

                # Rate limit: 다음 메시지 전송까지 대기
                await asyncio.sleep(1.0 / self._rate_limit)
        finally:
            await self._bot.session.close()
            logger.info("TelegramNotifier 종료")

    async def stop(self) -> None:
        """전송 루프를 종료한다."""
        self._running = False

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    async def _send_message(self, event: NotifyEvent) -> None:
        """Telegram Bot API로 메시지를 전송한다."""
        text = _format_message(event)
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text)
            logger.debug("Telegram 전송 완료: %s", event.title)
        except TelegramAPIError as exc:
            logger.error("Telegram API 오류: %s", exc, exc_info=True)
        except Exception as exc:
            logger.error("Telegram 전송 실패: %s", exc, exc_info=True)

    @property
    def qsize(self) -> int:
        return self._queue.qsize()


# ---------------------------------------------------------------------------
# 메시지 포맷 헬퍼
# ---------------------------------------------------------------------------

_LEVEL_EMOJI: dict[NotifyLevel, str] = {
    NotifyLevel.DEBUG: "🔍",
    NotifyLevel.INFO: "ℹ️",
    NotifyLevel.WARNING: "⚠️",
    NotifyLevel.ERROR: "🚨",
    NotifyLevel.CRITICAL: "🔴",
}


def _format_message(event: NotifyEvent) -> str:
    """NotifyEvent를 Telegram HTML 메시지로 변환한다."""
    emoji = _LEVEL_EMOJI.get(event.level, "📢")
    ts = event.timestamp.strftime("%H:%M:%S")
    lines = [
        f"{emoji} <b>{event.title}</b>",
        event.body,
    ]
    if event.source:
        lines.append(f"<i>source: {event.source}</i>")
    lines.append(f"<code>{ts}</code>")
    return "\n".join(lines)
