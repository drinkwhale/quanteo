"""InfoNotifier 단위 테스트."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import pytz

from info.ai_filter.claude_filter import FilterResult
from info.news.rss_collector import NewsItem
from info.telegram.info_notifier import InfoNotifier, _DlqItem

KST = pytz.timezone("Asia/Seoul")


def _make_notifier(tg=None):
    tg = tg or AsyncMock()
    tg.send = AsyncMock()
    return InfoNotifier(telegram_notifier=tg), tg


def _news_item(title: str = "SK하이닉스 공시") -> NewsItem:
    return NewsItem(
        title=title,
        url="https://news.com/1",
        source="TEST",
        published_kst=datetime.now(tz=KST),
    )


def _high_result() -> FilterResult:
    return FilterResult(score="HIGH", reason="테스트 HIGH", action="매수검토")


# ---------------------------------------------------------------------------
# 포맷 스냅샷 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_news_alert_contains_score():
    n, tg = _make_notifier()
    await n.send_news_alert(_news_item(), _high_result())
    tg.send.assert_called_once()
    body = tg.send.call_args[0][0].body
    assert "[HIGH]" in body
    assert "SK하이닉스 공시" in body
    assert "매수검토" in body


@pytest.mark.asyncio
async def test_send_fx_alert_contains_rate():
    n, tg = _make_notifier()

    fx = MagicMock()
    fx.usdkrw = 1380.5
    fx.usdkrw_change_pct = 1.2
    fx.dxy = 104.3
    fx.dxy_change_pct = 0.4

    await n.send_fx_alert(fx)
    body = tg.send.call_args[0][0].body
    assert "1380.50" in body
    assert "+1.20%" in body
    assert "원화 약세" in body


@pytest.mark.asyncio
async def test_send_fx_daily_report_format():
    n, tg = _make_notifier()

    report = MagicMock()
    report.usdkrw = 1380.0
    report.usdkrw_change_pct = 0.5
    report.dxy = 104.0
    report.dxy_change_pct = 0.2
    report.jpykrw = 9.2
    report.jpykrw_change_pct = -0.3
    report.cnykrw = 190.0
    report.cnykrw_change_pct = 0.1
    report.summary = "원화 소폭 약세 — SK하이닉스 중립"
    report.date = datetime(2026, 6, 29, tzinfo=pytz.UTC)

    await n.send_fx_daily_report(report)
    body = tg.send.call_args[0][0].body
    assert "USD/KRW" in body
    assert "DXY" in body
    assert "원화 소폭 약세" in body


# ---------------------------------------------------------------------------
# 발송 재시도 성공
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_failure_then_success():
    tg = AsyncMock()
    call_count = {"n": 0}

    async def _fail_then_succeed(event):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError("Telegram 일시 장애")

    tg.send = _fail_then_succeed
    n = InfoNotifier(telegram_notifier=tg)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await n.send_news_alert(_news_item(), _high_result())

    assert call_count["n"] == 3  # 2회 실패 후 3회째 성공


# ---------------------------------------------------------------------------
# 3회 모두 실패 → DLQ 적재 + logger.error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_failures_goes_to_dlq(caplog):
    import logging

    tg = AsyncMock()
    tg.send = AsyncMock(side_effect=RuntimeError("Telegram 완전 장애"))
    n = InfoNotifier(telegram_notifier=tg)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with caplog.at_level(logging.ERROR):
            await n.send_news_alert(_news_item(), _high_result())

    assert not n._dlq.empty()
    item = n._dlq.get_nowait()
    assert isinstance(item, _DlqItem)
    assert any("DLQ" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# DLQ 재시도
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_dlq_drains_queue():
    tg = AsyncMock()
    n = InfoNotifier(telegram_notifier=tg)

    # DLQ에 직접 2개 적재
    await n._dlq.put(_DlqItem(text="메시지1"))
    await n._dlq.put(_DlqItem(text="메시지2"))

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await n.retry_dlq()

    assert n._dlq.empty()
    assert tg.send.call_count == 2
