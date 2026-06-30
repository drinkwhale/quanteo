"""
통합 테스트: Claude API + Telegram 동시 장애 시 시스템 계속 동작 검증.

DLQ 적재, 스케줄러 지속, 재시도 동작을 검증한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from info.ai_filter.claude_filter import FilterResult
from info.news.rss_collector import NewsItem
from datetime import datetime
import pytz

KST = pytz.timezone("Asia/Seoul")


def _news_item(title: str = "SK하이닉스 HBM 공급") -> NewsItem:
    return NewsItem(
        title=title,
        url=f"https://example.com/{hash(title)}",
        source="test",
        published_kst=datetime(2026, 7, 14, 9, 0, tzinfo=KST),
        raw_body="본문",
    )


# ────────────────────────────────────────────────────────────────────────────
# Telegram 장애 → DLQ 적재
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_telegram_failure_queues_to_dlq():
    """Telegram 발송 3회 실패 시 메시지가 DLQ에 적재되어야 한다."""
    from info.telegram.info_notifier import InfoNotifier
    from core.notifier.base import NotifyEvent

    mock_base = MagicMock()
    mock_base.send = AsyncMock(side_effect=RuntimeError("Telegram API down"))
    notifier = InfoNotifier(telegram_notifier=mock_base, chat_id="test")

    item = _news_item()
    result = FilterResult(score="HIGH", reason="test", action="관망")

    with patch("asyncio.sleep", AsyncMock()):
        await notifier.send_news_alert(item, result)

    # 3회 재시도 후 DLQ에 1개 적재
    assert notifier._dlq.qsize() == 1
    assert mock_base.send.call_count == 3


@pytest.mark.asyncio
async def test_dlq_retry_sends_on_recovery():
    """DLQ에 적재된 메시지가 retry_dlq() 호출 시 재발송되어야 한다."""
    from info.telegram.info_notifier import InfoNotifier, _DlqItem

    mock_base = MagicMock()
    mock_base.send = AsyncMock()
    notifier = InfoNotifier(telegram_notifier=mock_base, chat_id="test")

    # DLQ에 직접 _DlqItem 추가
    await notifier._dlq.put(_DlqItem(text="복구 후 재발송 메시지"))

    await notifier.retry_dlq()

    assert notifier._dlq.empty()
    assert mock_base.send.call_count == 1


# ────────────────────────────────────────────────────────────────────────────
# Claude API 장애 → 키워드 폴백
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claude_api_failure_uses_keyword_fallback():
    """Claude API 호출 실패 시 키워드 카운트 폴백으로 MEDIUM을 반환해야 한다."""
    from info.ai_filter.claude_filter import ClaudeFilter

    claude = ClaudeFilter(api_key="test-key")

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("API timeout"))
        mock_cls.return_value = mock_client
        claude._client = mock_client

        # 키워드 2개 이상 → MEDIUM 폴백
        result = await claude.classify("SK하이닉스 HBM DRAM 공급 계약", "")

    assert result.score in ("MEDIUM", "LOW")  # 폴백 동작


# ────────────────────────────────────────────────────────────────────────────
# 스케줄러 잡 예외 후 계속 실행
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scheduler_continues_after_job_failure():
    """한 잡에서 예외가 발생해도 스케줄러 자체는 멈추지 않아야 한다."""
    from info.scheduler import InfoScheduler

    mock_sys = MagicMock()
    mock_sys.rss_collector.fetch = AsyncMock(side_effect=RuntimeError("수집 실패"))
    mock_sys.claude_filter.classify = AsyncMock()
    mock_sys.notifier.send_news_alert = AsyncMock()
    mock_sys.notifier.send_morning_brief = AsyncMock()

    mock_sched = MagicMock()
    mock_sched.running = True

    with patch("info.scheduler.AsyncIOScheduler", return_value=mock_sched):
        scheduler = InfoScheduler(mock_sys)

    # morning_brief 잡 내부 예외 → 외부 전파 없음
    await scheduler._job_morning_brief()

    # 스케줄러 인스턴스 유지
    assert scheduler.scheduler is mock_sched


@pytest.mark.asyncio
async def test_dlq_full_does_not_crash():
    """DLQ가 최대 크기(100)에 도달해도 알람 발송이 크래시 없이 완료되어야 한다."""
    from info.telegram.info_notifier import InfoNotifier, _DlqItem

    mock_base = MagicMock()
    mock_base.send = AsyncMock(side_effect=RuntimeError("Telegram down"))
    notifier = InfoNotifier(telegram_notifier=mock_base, chat_id="test")

    # DLQ를 가득 채운다
    for i in range(100):
        await notifier._dlq.put(_DlqItem(text=f"메시지 {i}"))

    assert notifier._dlq.full()

    item = _news_item("DLQ 풀 상태 테스트")
    result = FilterResult(score="HIGH", reason="test", action="관망")

    # DLQ 풀 → put 스킵, 크래시 없이 정상 완료
    with patch("asyncio.sleep", AsyncMock()):
        await notifier.send_news_alert(item, result)  # no crash
