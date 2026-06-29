"""RssCollector 단위 테스트."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz

from info.ai_filter.claude_filter import FilterResult
from info.news.rss_collector import (
    NewsItem,
    RssCollector,
    _fetch_one_feed,
    _init_dedup_db,
    _is_seen,
    _mark_seen,
)

KST = pytz.timezone("Asia/Seoul")


def _make_temp_db() -> Path:
    tmp = tempfile.mktemp(suffix=".db")
    return Path(tmp)


def _mock_feed(entries: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.entries = []
    for e in entries:
        entry = MagicMock()
        entry.link = e.get("link", "")
        entry.title = e.get("title", "")
        entry.summary = e.get("summary", "")
        entry.published_parsed = None
        mock.entries.append(entry)
    return mock


# ---------------------------------------------------------------------------
# dedup 동작
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_prevents_duplicate():
    db = _make_temp_db()
    await _init_dedup_db(db)
    await _mark_seen("https://example.com/news/1", db)
    assert await _is_seen("https://example.com/news/1", db)
    assert not await _is_seen("https://example.com/news/2", db)


@pytest.mark.asyncio
async def test_restart_dedup_same_url_blocked():
    """재시작 후 동일 URL 재수신 시 발송 차단 — SQLite 영속 dedup 검증."""
    db = _make_temp_db()
    mock_notifier = AsyncMock()
    mock_notifier.send_news_alert = AsyncMock()
    mock_filter = AsyncMock()
    mock_filter.classify = AsyncMock(
        return_value=FilterResult(score="HIGH", reason="test", action="관망")
    )

    collector = RssCollector(
        sources={"테스트": "http://test.rss"},
        dedup_db_path=db,
        claude_filter=mock_filter,
        info_notifier=mock_notifier,
    )

    feed = _mock_feed([{"link": "https://news.com/1", "title": "SK하이닉스 공시"}])
    with patch("feedparser.parse", return_value=feed):
        await collector.fetch()  # 첫 수집 → 발송
        await collector.fetch()  # 재수집 → 차단

    # send_news_alert는 첫 번째 수집에서만 1회
    assert mock_notifier.send_news_alert.call_count == 1


# ---------------------------------------------------------------------------
# KST 변환
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kst_conversion():
    db = _make_temp_db()
    collector = RssCollector(sources={"테스트": "http://test.rss"}, dedup_db_path=db)

    import time
    parsed_time = time.strptime("2026-06-29 00:00:00", "%Y-%m-%d %H:%M:%S")
    entry = MagicMock()
    entry.link = "https://news.com/kst"
    entry.title = "한국경제 기사"
    entry.summary = ""
    entry.published_parsed = parsed_time

    feed = MagicMock()
    feed.entries = [entry]

    with patch("feedparser.parse", return_value=feed):
        items = await collector.fetch()

    assert len(items) == 1
    assert items[0].published_kst.tzinfo is not None
    # UTC 00:00 → KST 09:00
    assert items[0].published_kst.hour == 9


# ---------------------------------------------------------------------------
# HIGH 필터 연동
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high_filter_triggers_alert():
    db = _make_temp_db()
    mock_notifier = AsyncMock()
    mock_notifier.send_news_alert = AsyncMock()
    mock_filter = AsyncMock()
    mock_filter.classify = AsyncMock(
        return_value=FilterResult(score="HIGH", reason="테스트 HIGH", action="매수검토")
    )

    collector = RssCollector(
        sources={"테스트": "http://test.rss"},
        dedup_db_path=db,
        claude_filter=mock_filter,
        info_notifier=mock_notifier,
    )

    feed = _mock_feed([{"link": "https://news.com/h1", "title": "SK하이닉스 급등"}])
    with patch("feedparser.parse", return_value=feed):
        items = await collector.fetch()

    assert len(items) == 1
    mock_notifier.send_news_alert.assert_called_once()


@pytest.mark.asyncio
async def test_medium_filter_no_alert():
    db = _make_temp_db()
    mock_notifier = AsyncMock()
    mock_notifier.send_news_alert = AsyncMock()
    mock_filter = AsyncMock()
    mock_filter.classify = AsyncMock(
        return_value=FilterResult(score="MEDIUM", reason="중간", action="관망")
    )

    collector = RssCollector(
        sources={"테스트": "http://test.rss"},
        dedup_db_path=db,
        claude_filter=mock_filter,
        info_notifier=mock_notifier,
    )

    feed = _mock_feed([{"link": "https://news.com/m1", "title": "일반 경제 뉴스"}])
    with patch("feedparser.parse", return_value=feed):
        await collector.fetch()

    mock_notifier.send_news_alert.assert_not_called()


# ---------------------------------------------------------------------------
# 피드 실패 처리
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_feeds_timeout_returns_empty():
    db = _make_temp_db()
    collector = RssCollector(
        sources={"A": "http://a.rss", "B": "http://b.rss"},
        dedup_db_path=db,
    )

    with patch("feedparser.parse", side_effect=TimeoutError("timeout")):
        items = await collector.fetch()  # 예외 전파 없음

    assert items == []


@pytest.mark.asyncio
async def test_partial_feed_failure_returns_successful():
    db = _make_temp_db()
    ok_feed = _mock_feed([{"link": "https://news.com/ok", "title": "정상 뉴스"}])
    fail_feed = TimeoutError("timeout")

    call_count = {"n": 0}

    def _parse_side_effect(url):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ok_feed
        raise fail_feed

    collector = RssCollector(
        sources={"A": "http://a.rss", "B": "http://b.rss"},
        dedup_db_path=db,
    )

    with patch("feedparser.parse", side_effect=_parse_side_effect):
        items = await collector.fetch()

    assert len(items) == 1
    assert items[0].url == "https://news.com/ok"
