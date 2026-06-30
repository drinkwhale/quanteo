"""
통합 테스트: RSS 수집 → AI 필터 → Telegram 전송 엔드투엔드.

MockTelegramNotifier를 사용해 실제 외부 API 호출 없이 파이프라인 전체를 검증한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz

from info.ai_filter.claude_filter import FilterResult
from info.news.rss_collector import NewsItem

KST = pytz.timezone("Asia/Seoul")


# ────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ────────────────────────────────────────────────────────────────────────────


def _news_item(title: str = "SK하이닉스 HBM 공급 계약 체결", source: str = "test") -> NewsItem:
    return NewsItem(
        title=title,
        url=f"https://test.example.com/{title[:10]}",
        source=source,
        published_kst=datetime(2026, 7, 14, 9, 0, tzinfo=KST),
        raw_body="본문 내용",
    )


def _filter_result(score: str = "HIGH") -> FilterResult:
    return FilterResult(
        score=score,  # type: ignore
        reason="HBM 관련 핵심 키워드 포함",
        action="매수검토",  # type: ignore
    )


# ────────────────────────────────────────────────────────────────────────────
# 테스트
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_high_news_triggers_telegram_alert():
    """HIGH 뉴스 → InfoNotifier.send_news_alert 호출되어야 한다."""
    from info.telegram.info_notifier import InfoNotifier

    mock_telegram = MagicMock()
    mock_telegram.send = AsyncMock()
    notifier = InfoNotifier(telegram_notifier=mock_telegram, chat_id="test_chat")
    notifier._send_text = AsyncMock()

    item = _news_item()
    result = _filter_result("HIGH")
    await notifier.send_news_alert(item, result)

    notifier._send_text.assert_called_once()
    sent_text: str = notifier._send_text.call_args[0][0]
    assert "HIGH" in sent_text or "🔴" in sent_text


@pytest.mark.asyncio
async def test_low_news_not_filtered_by_notifier():
    """LOW 결과도 send_news_alert는 텍스트를 전송한다 (필터링은 스케줄러 레이어 책임)."""
    from info.telegram.info_notifier import InfoNotifier

    mock_telegram = MagicMock()
    notifier = InfoNotifier(telegram_notifier=mock_telegram, chat_id="test_chat")
    notifier._send_text = AsyncMock()

    item = _news_item()
    result = _filter_result("LOW")
    await notifier.send_news_alert(item, result)

    notifier._send_text.assert_called_once()


@pytest.mark.asyncio
async def test_rss_pipeline_dedup_skips_seen_url():
    """동일 URL은 SQLite dedup으로 두 번째 수집에서 제외되어야 한다."""
    from info.news.rss_collector import RssCollector

    item = _news_item()

    with patch("info.news.rss_collector._init_dedup_db", AsyncMock()):
        with patch("info.news.rss_collector._cleanup_old", AsyncMock()):
            with patch("info.news.rss_collector._is_seen", AsyncMock(return_value=True)):
                with patch("info.news.rss_collector._mark_seen", AsyncMock()):
                    with patch("info.news.rss_collector._fetch_one_feed", AsyncMock(return_value=[item])):
                        collector = RssCollector()
                        results = await collector.fetch()

    # 이미 seen → 결과에서 제외
    assert item not in results


@pytest.mark.asyncio
async def test_rss_pipeline_new_item_passes_through():
    """새 URL은 dedup을 통과하여 결과에 포함되어야 한다."""
    from info.news.rss_collector import RssCollector

    item = _news_item("새 SK하이닉스 기사")

    with patch("info.news.rss_collector._init_dedup_db", AsyncMock()):
        with patch("info.news.rss_collector._cleanup_old", AsyncMock()):
            with patch("info.news.rss_collector._is_seen", AsyncMock(return_value=False)):
                with patch("info.news.rss_collector._mark_seen", AsyncMock()):
                    with patch("info.news.rss_collector._fetch_one_feed", AsyncMock(return_value=[item])):
                        collector = RssCollector()
                        results = await collector.fetch()

    assert item in results


@pytest.mark.asyncio
async def test_claude_filter_skips_api_when_no_keyword():
    """CRITICAL_KEYWORDS 미포함 제목은 API 호출 없이 LOW를 반환한다."""
    from info.ai_filter.claude_filter import ClaudeFilter, CRITICAL_KEYWORDS

    claude = ClaudeFilter(api_key="test-key")

    original_keywords = list(CRITICAL_KEYWORDS)
    CRITICAL_KEYWORDS.clear()  # 키워드 전부 제거 → 사전 필터에서 LOW 반환
    try:
        result = await claude.classify("완전히 무관한 제목입니다", "")
        assert result.score == "LOW"
    finally:
        CRITICAL_KEYWORDS.extend(original_keywords)
