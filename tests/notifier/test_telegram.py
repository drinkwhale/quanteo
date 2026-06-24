"""TelegramNotifier 단위 테스트.

aiogram Bot 인스턴스 생성이 필요한 부분은 토큰 포맷만 검사하므로
실제 네트워크 호출 없이 큐 동작과 메시지 포맷을 검증한다.
"""

from __future__ import annotations

import pytest

from core.notifier.base import NotifyEvent, NotifyLevel
from core.notifier.telegram import TelegramNotifier, _format_message

_FAKE_TOKEN = "123456789:AABBCCDDaabbccdd11223344"


def _make_event(level: NotifyLevel = NotifyLevel.INFO, title: str = "t", body: str = "b") -> NotifyEvent:
    return NotifyEvent(level=level, title=title, body=body)


# ---------------------------------------------------------------------------
# 우선순위 큐 라우팅
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critical_routed_to_urgent_queue():
    notifier = TelegramNotifier(bot_token=_FAKE_TOKEN, chat_id="-100")
    await notifier.send(_make_event(NotifyLevel.CRITICAL))
    assert notifier._urgent_queue.qsize() == 1
    assert notifier._queue.qsize() == 0


@pytest.mark.asyncio
async def test_error_routed_to_urgent_queue():
    notifier = TelegramNotifier(bot_token=_FAKE_TOKEN, chat_id="-100")
    await notifier.send(_make_event(NotifyLevel.ERROR))
    assert notifier._urgent_queue.qsize() == 1
    assert notifier._queue.qsize() == 0


@pytest.mark.asyncio
async def test_info_routed_to_normal_queue():
    notifier = TelegramNotifier(bot_token=_FAKE_TOKEN, chat_id="-100")
    await notifier.send(_make_event(NotifyLevel.INFO))
    assert notifier._urgent_queue.qsize() == 0
    assert notifier._queue.qsize() == 1


@pytest.mark.asyncio
async def test_qsize_sums_both_queues():
    notifier = TelegramNotifier(bot_token=_FAKE_TOKEN, chat_id="-100")
    await notifier.send(_make_event(NotifyLevel.INFO))
    await notifier.send(_make_event(NotifyLevel.CRITICAL))
    assert notifier.qsize == 2


# ---------------------------------------------------------------------------
# HTML 이스케이프
# ---------------------------------------------------------------------------


def test_format_escapes_html_in_title():
    event = NotifyEvent(level=NotifyLevel.INFO, title="price < limit", body="ok")
    msg = _format_message(event)
    assert "price &lt; limit" in msg
    assert "<b>price &lt; limit</b>" in msg


def test_format_escapes_html_in_body():
    event = NotifyEvent(level=NotifyLevel.ERROR, title="err", body="val > 100 & risk=high")
    msg = _format_message(event)
    assert "&gt;" in msg
    assert "&amp;" in msg


def test_format_escapes_html_in_source():
    event = NotifyEvent(level=NotifyLevel.INFO, title="t", body="b", source="module<x>")
    msg = _format_message(event)
    assert "module&lt;x&gt;" in msg


def test_format_safe_text_unchanged():
    event = NotifyEvent(level=NotifyLevel.INFO, title="정상 알림", body="체결 완료", source="order")
    msg = _format_message(event)
    assert "정상 알림" in msg
    assert "체결 완료" in msg
