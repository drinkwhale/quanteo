"""InfoScheduler 단위 테스트."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


def _make_mock_system() -> MagicMock:
    sys = MagicMock()
    sys.rss_collector = MagicMock()
    sys.rss_collector.fetch = AsyncMock(return_value=[])
    sys.claude_filter = MagicMock()
    sys.claude_filter.classify = AsyncMock(return_value=MagicMock(score="LOW"))
    sys.fx_monitor = MagicMock()
    sys.fx_monitor.check_and_alert = AsyncMock()
    sys.fx_reporter = MagicMock()
    sys.fx_reporter.generate = AsyncMock(return_value=MagicMock())
    sys.finnhub_collector = MagicMock()
    sys.finnhub_collector.fetch = AsyncMock(return_value=[])
    sys.notifier = MagicMock()
    sys.notifier.send_news_alert = AsyncMock()
    sys.notifier.send_earnings_alert = AsyncMock()
    sys.notifier.send_fx_daily_report = AsyncMock()
    sys.notifier.send_morning_brief = AsyncMock()
    sys.notifier._send_text = AsyncMock()
    sys.calendar_client = MagicMock()
    sys.calendar_client.bulk_add = AsyncMock()
    return sys


def _make_scheduler(mock_sys=None):
    """AsyncIOScheduler를 mock으로 교체한 InfoScheduler 반환."""
    from info.scheduler import InfoScheduler
    mock_sched = MagicMock()
    mock_sched.running = True
    with patch("info.scheduler.AsyncIOScheduler", return_value=mock_sched):
        s = InfoScheduler(mock_sys or _make_mock_system())
    s._scheduler = mock_sched
    return s, mock_sched


# ────────────────────────────────────────────────────────────────────────────
# 잡 등록 검증 — 뉴스 폴링이 비활성이어도 잡 자체는 7개 모두 등록된다
# (본문에서 _NEWS_POLLING_ENABLED로 가드하는 방식이라 등록은 영향받지 않음)
# ────────────────────────────────────────────────────────────────────────────


def test_seven_jobs_registered():
    _, mock_sched = _make_scheduler()
    assert mock_sched.add_job.call_count == 7


def test_scheduler_timezone():
    """AsyncIOScheduler가 Asia/Seoul timezone으로 생성되는지 검증."""
    with patch("info.scheduler.AsyncIOScheduler") as mock_cls:
        mock_cls.return_value = MagicMock()
        from info.scheduler import InfoScheduler
        InfoScheduler(_make_mock_system())
    mock_cls.assert_called_once_with(timezone="Asia/Seoul")


def test_job_ids_unique():
    _, mock_sched = _make_scheduler()
    job_ids = [call.kwargs.get("id") for call in mock_sched.add_job.call_args_list]
    assert len(job_ids) == len(set(job_ids)), "잡 ID 중복"


def test_morning_brief_cron_trigger():
    _, mock_sched = _make_scheduler()
    calls = mock_sched.add_job.call_args_list
    morning = next(c for c in calls if c.kwargs.get("id") == "morning_brief")
    trigger = morning.args[1]
    assert isinstance(trigger, CronTrigger)


def test_domestic_rss_interval_trigger():
    """뉴스 폴링이 비활성 상태여도 잡 등록·트리거 설정 자체는 정상이어야 한다
    (재활성화 시 _NEWS_POLLING_ENABLED만 바꾸면 되므로 설정값이 계속 검증돼야 함)."""
    _, mock_sched = _make_scheduler()
    calls = mock_sched.add_job.call_args_list
    rss = next(c for c in calls if c.kwargs.get("id") == "domestic_rss")
    trigger = rss.args[1]
    assert isinstance(trigger, IntervalTrigger)


def test_us_news_interval_trigger():
    _, mock_sched = _make_scheduler()
    calls = mock_sched.add_job.call_args_list
    us_news = next(c for c in calls if c.kwargs.get("id") == "us_news")
    trigger = us_news.args[1]
    assert isinstance(trigger, IntervalTrigger)


def test_monthly_calendar_cron_trigger():
    _, mock_sched = _make_scheduler()
    calls = mock_sched.add_job.call_args_list
    cal = next(c for c in calls if c.kwargs.get("id") == "monthly_calendar")
    trigger = cal.args[1]
    assert isinstance(trigger, CronTrigger)


def test_all_jobs_have_misfire_grace_time():
    _, mock_sched = _make_scheduler()
    for call in mock_sched.add_job.call_args_list:
        assert call.kwargs.get("misfire_grace_time") == 60
        assert call.kwargs.get("coalesce") is True


# ────────────────────────────────────────────────────────────────────────────
# _NEWS_POLLING_ENABLED=False(기본값) → 뉴스 관련 3개 잡이 Claude API를
# 호출하지 않고 즉시/조용히 스킵해야 한다 (비용 급증 방지가 실제로 지켜지는지 검증)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_domestic_rss_noop_when_news_polling_disabled():
    mock_sys = _make_mock_system()
    s, _ = _make_scheduler(mock_sys)

    with patch("info.scheduler._in_kr_market_hours", return_value=True):
        await s._job_domestic_rss()

    mock_sys.rss_collector.fetch.assert_not_called()
    mock_sys.claude_filter.classify.assert_not_called()


@pytest.mark.asyncio
async def test_us_news_noop_when_news_polling_disabled():
    mock_sys = _make_mock_system()
    s, _ = _make_scheduler(mock_sys)

    with patch("info.scheduler._in_us_session", return_value=True):
        await s._job_us_news()

    mock_sys.finnhub_collector.fetch.assert_not_called()
    mock_sys.claude_filter.classify.assert_not_called()


@pytest.mark.asyncio
async def test_morning_brief_skips_news_when_disabled():
    """뉴스 폴링 비활성 시 morning_brief는 Claude를 호출하지 않고
    캘린더 브리핑만 정상 발송해야 한다."""
    mock_sys = _make_mock_system()
    s, _ = _make_scheduler(mock_sys)

    await s._job_morning_brief()

    mock_sys.rss_collector.fetch.assert_not_called()
    mock_sys.claude_filter.classify.assert_not_called()
    mock_sys.notifier.send_morning_brief.assert_called_once()


@pytest.mark.asyncio
async def test_start_notifies_when_news_polling_disabled():
    """뉴스 폴링이 비활성 상태로 기동되면 운영자에게 Telegram 알림을 보내야 한다."""
    mock_sys = _make_mock_system()
    s, _ = _make_scheduler(mock_sys)

    s.start()
    await asyncio.sleep(0)  # asyncio.create_task로 예약된 알림 태스크 실행 대기

    mock_sys.notifier._send_text.assert_called_once()


# ────────────────────────────────────────────────────────────────────────────
# _NEWS_POLLING_ENABLED=True(재활성화 가정) → 뉴스 관련 3개 잡의 기존 로직이
# 여전히 올바르게 동작해야 한다 (플래그로만 잠긴 휴면 코드가 방치되지 않도록 검증)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_domestic_rss_calls_claude_when_enabled_and_in_market_hours():
    mock_sys = _make_mock_system()
    mock_sys.claude_filter.classify = AsyncMock(return_value=MagicMock(score="HIGH"))
    item = MagicMock(title="t", raw_body="b")
    mock_sys.rss_collector.fetch = AsyncMock(return_value=[item])
    s, _ = _make_scheduler(mock_sys)

    with (
        patch("info.scheduler._NEWS_POLLING_ENABLED", True),
        patch("info.scheduler._in_kr_market_hours", return_value=True),
    ):
        await s._job_domestic_rss()

    mock_sys.rss_collector.fetch.assert_called_once()
    mock_sys.claude_filter.classify.assert_called_once_with("t", "b")
    mock_sys.notifier.send_news_alert.assert_called_once()


@pytest.mark.asyncio
async def test_us_news_calls_claude_when_enabled_and_in_us_session():
    mock_sys = _make_mock_system()
    mock_sys.claude_filter.classify = AsyncMock(return_value=MagicMock(score="CRITICAL"))
    item = MagicMock(title="t", raw_body="b")
    mock_sys.finnhub_collector.fetch = AsyncMock(return_value=[item])
    s, _ = _make_scheduler(mock_sys)

    with (
        patch("info.scheduler._NEWS_POLLING_ENABLED", True),
        patch("info.scheduler._in_us_session", return_value=True),
    ):
        await s._job_us_news()

    mock_sys.finnhub_collector.fetch.assert_called_once()
    mock_sys.claude_filter.classify.assert_called_once_with("t", "b")
    mock_sys.notifier.send_news_alert.assert_called_once()


@pytest.mark.asyncio
async def test_morning_brief_calls_claude_when_enabled():
    mock_sys = _make_mock_system()
    mock_sys.claude_filter.classify = AsyncMock(return_value=MagicMock(score="HIGH"))
    item = MagicMock(title="t", raw_body="b")
    mock_sys.rss_collector.fetch = AsyncMock(return_value=[item])
    s, _ = _make_scheduler(mock_sys)

    with patch("info.scheduler._NEWS_POLLING_ENABLED", True):
        await s._job_morning_brief()

    mock_sys.rss_collector.fetch.assert_called_once()
    mock_sys.claude_filter.classify.assert_called_once_with("t", "b")
    mock_sys.notifier.send_news_alert.assert_called_once()
    mock_sys.notifier.send_morning_brief.assert_called_once()


# ────────────────────────────────────────────────────────────────────────────
# 잡 내부 예외 → 스케줄러 계속 실행
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_exception_does_not_propagate():
    """잡 내부 RuntimeError가 외부로 전파되지 않아야 한다."""
    mock_sys = _make_mock_system()
    mock_sys.rss_collector.fetch.side_effect = RuntimeError("network error")
    s, _ = _make_scheduler(mock_sys)

    with (
        patch("info.scheduler._NEWS_POLLING_ENABLED", True),
        patch("info.scheduler._in_kr_market_hours", return_value=True),
    ):
        await s._job_domestic_rss()  # 예외가 외부로 전파되지 않아야 함


@pytest.mark.asyncio
async def test_fx_check_exception_does_not_propagate():
    mock_sys = _make_mock_system()
    mock_sys.fx_monitor.check_and_alert.side_effect = RuntimeError("yfinance timeout")
    s, _ = _make_scheduler(mock_sys)

    with patch("info.scheduler._in_kr_market_hours", return_value=True):
        await s._job_fx_check()  # 예외가 외부로 전파되지 않아야 함


# ────────────────────────────────────────────────────────────────────────────
# today_us_earnings() 빈 결과 → Telegram 미발송
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_us_earnings_alert_no_send_when_empty():
    """today_us_earnings()가 빈 리스트 반환 시 Telegram 알람을 보내지 않아야 한다."""
    mock_sys = _make_mock_system()
    s, _ = _make_scheduler(mock_sys)

    with patch("info.calendar.earnings_data.today_us_earnings", return_value=[]):
        await s._job_us_earnings_alert()

    mock_sys.notifier.send_earnings_alert.assert_not_called()


@pytest.mark.asyncio
async def test_us_earnings_alert_sends_when_event_exists():
    """today_us_earnings()가 결과를 반환할 때 Telegram 알람이 발송되어야 한다."""
    mock_sys = _make_mock_system()
    s, _ = _make_scheduler(mock_sys)

    fake_event = MagicMock()
    with patch("info.calendar.earnings_data.today_us_earnings", return_value=[fake_event]):
        await s._job_us_earnings_alert()

    mock_sys.notifier.send_earnings_alert.assert_called_once_with(fake_event)


# ────────────────────────────────────────────────────────────────────────────
# 시간 가드 검증
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_domestic_rss_skips_outside_market_hours():
    """뉴스 폴링이 활성 상태여도 국내 장 외 시간대에는 RSS 수집을 스킵해야 한다."""
    mock_sys = _make_mock_system()
    s, _ = _make_scheduler(mock_sys)

    with (
        patch("info.scheduler._NEWS_POLLING_ENABLED", True),
        patch("info.scheduler._in_kr_market_hours", return_value=False),
    ):
        await s._job_domestic_rss()

    mock_sys.rss_collector.fetch.assert_not_called()
