"""
TelegramNotifier — aiogram v3 기반 Telegram 알림 전송기.

asyncio.Queue 기반 버퍼 + rate limit으로 메시지를 순차 전송한다.
CRITICAL/ERROR 레벨 이벤트는 별도 urgent 큐에서 우선 처리한다.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from core.notifier.base import NotifyEvent, NotifyLevel, level_rank

logger = logging.getLogger(__name__)

# CRITICAL/ERROR는 urgent 큐에서 우선 처리 (INFO/WARNING 뒤에 묻히지 않도록)
_URGENT_LEVELS = frozenset({NotifyLevel.CRITICAL, NotifyLevel.ERROR})


class TelegramNotifier:
    """Telegram 알림 전송기.

    aiogram v3 Bot을 사용해 지정된 chat_id로 메시지를 전송한다.
    CRITICAL/ERROR 이벤트는 urgent 큐에서 INFO/WARNING보다 먼저 처리된다.
    종료 시 큐에 남은 이벤트를 배출한 뒤 세션을 닫는다.

    Args:
        bot_token: Telegram Bot API 토큰.
        chat_id: 메시지를 받을 채팅 ID.
        min_level: 이 레벨 이상의 이벤트만 전송한다. 기본값 INFO.
        rate_limit: 초당 최대 전송 횟수. 기본값 1.0 (Telegram 권장).
        queue_maxsize: 일반 전송 버퍼 최대 크기. 초과 시 드롭.
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
        # urgent: CRITICAL/ERROR 전용 (maxsize=20), queue: 나머지
        self._urgent_queue: asyncio.Queue[NotifyEvent] = asyncio.Queue(maxsize=20)
        self._queue: asyncio.Queue[NotifyEvent] = asyncio.Queue(maxsize=queue_maxsize)
        self._running = False

    # ------------------------------------------------------------------
    # Notifier Protocol 구현
    # ------------------------------------------------------------------

    async def send(self, event: NotifyEvent) -> None:
        """이벤트를 전송 큐에 넣는다.

        CRITICAL/ERROR는 urgent 큐에, 나머지는 일반 큐에 넣어 우선순위를 보장한다.
        레벨 미달 또는 큐 포화 시 드롭.
        """
        if level_rank(event.level) < level_rank(self._min_level):
            return
        queue = self._urgent_queue if event.level in _URGENT_LEVELS else self._queue
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "TelegramNotifier 큐 포화 — 이벤트 드롭 (level=%s title=%s)",
                event.level,
                event.title,
            )

    async def run(self) -> None:
        """전송 루프: urgent 큐를 우선으로 이벤트를 꺼내 Telegram으로 전송한다."""
        self._running = True
        logger.info("TelegramNotifier 시작 (chat_id=%s)", self._chat_id)
        try:
            while self._running:
                event = await self._get_next()
                if event is None:
                    continue
                await self._send_message(event)
                # Rate limit: 다음 메시지 전송까지 대기
                await asyncio.sleep(1.0 / self._rate_limit)
        finally:
            # 종료 전 남은 이벤트 배출 (urgent 우선)
            await self._drain_remaining()
            await self._bot.session.close()
            logger.info("TelegramNotifier 종료")

    async def stop(self) -> None:
        """전송 루프를 종료한다. 잔여 이벤트는 run() finally에서 배출된다."""
        self._running = False

    async def send_once(self, event: NotifyEvent) -> None:
        """단발 전송: 큐/루프 없이 즉시 전송하고 세션을 닫는다.

        전송 실패 시 예외를 호출자에게 전파한다 (run() 루프와 달리 삼키지 않음).
        스크립트나 one-shot 작업에서 사용한다.
        """
        text = _format_message(event)
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text)
            logger.debug("Telegram 단발 전송 완료: %s", event.title)
        except TelegramAPIError:
            logger.error("Telegram API 오류 (send_once)", exc_info=False)
            raise
        except Exception:
            logger.error("Telegram 전송 실패 (send_once)", exc_info=False)
            raise
        finally:
            await self._bot.session.close()

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    async def _get_next(self) -> NotifyEvent | None:
        """urgent 큐를 우선 확인하고, 없으면 일반 큐를 0.1s 간격으로 폴링(최대 1s)."""
        try:
            return self._urgent_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        for _ in range(10):  # 10 * 0.1s = 1s 타임아웃
            if not self._running:
                return None
            try:
                return self._urgent_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                return self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await asyncio.sleep(0.1)
        return None

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

    async def _drain_remaining(self) -> None:
        """종료 전 큐에 남은 이벤트를 전송한다 (urgent 우선)."""
        for queue in (self._urgent_queue, self._queue):
            while not queue.empty():
                try:
                    event = queue.get_nowait()
                    await self._send_message(event)
                except asyncio.QueueEmpty:
                    break
                except Exception as exc:
                    logger.error("종료 배출 실패: %s", exc)

    @property
    def qsize(self) -> int:
        return self._urgent_queue.qsize() + self._queue.qsize()


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
    """NotifyEvent를 Telegram HTML 메시지로 변환한다.

    title/body/source의 HTML 특수문자(<, >, &)를 이스케이프해
    Telegram API 파싱 오류를 방지한다.
    """
    emoji = _LEVEL_EMOJI.get(event.level, "📢")
    ts = event.timestamp.strftime("%H:%M:%S")
    title = html_lib.escape(event.title)
    body = html_lib.escape(event.body)
    lines = [
        f"{emoji} <b>{title}</b>",
        body,
    ]
    if event.source:
        lines.append(f"<i>source: {html_lib.escape(event.source)}</i>")
    lines.append(f"<code>{ts}</code>")
    return "\n".join(lines)
