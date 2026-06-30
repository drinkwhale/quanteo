"""캘린더 데이터 단위 테스트 (earnings_data + macro_events)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
import pytz

from info.calendar.earnings_data import (
    EARNINGS_SCHEDULE,
    EarningsEvent,
    next_events,
    today_us_earnings,
)
from info.calendar.macro_events import (
    MACRO_SCHEDULE,
    MacroEvent,
    next_macro_events,
    today_kr_macro,
)

KST = pytz.timezone("Asia/Seoul")


# ────────────────────────────────────────────────────────────────────────────
# EARNINGS_SCHEDULE 정적 검증
# ────────────────────────────────────────────────────────────────────────────


def test_earnings_schedule_not_empty():
    assert len(EARNINGS_SCHEDULE) >= 6


def test_earnings_all_fields_populated():
    for ev in EARNINGS_SCHEDULE:
        assert ev.summary
        assert ev.ticker
        assert ev.start.tzinfo is not None
        assert ev.end > ev.start


def test_earnings_critical_events_exist():
    critical = [ev for ev in EARNINGS_SCHEDULE if ev.importance == "CRITICAL"]
    assert len(critical) >= 2
    tickers = [ev.ticker for ev in critical]
    assert "NVDA" in tickers


def test_earnings_sk_impact_values():
    valid = {"🔴 최고", "🔴 높음", "🟡 중간"}
    for ev in EARNINGS_SCHEDULE:
        assert ev.sk_impact in valid, f"{ev.ticker}: {ev.sk_impact!r} 는 유효하지 않음"


# ────────────────────────────────────────────────────────────────────────────
# next_events
# ────────────────────────────────────────────────────────────────────────────


def test_next_events_returns_future_events():
    fake_now = datetime(2026, 7, 1, 9, 0, tzinfo=KST)
    with patch("info.calendar.earnings_data.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        events = next_events(days=365)
    assert len(events) > 0


def test_next_events_sorted_by_start():
    fake_now = datetime(2026, 7, 1, 9, 0, tzinfo=KST)
    with patch("info.calendar.earnings_data.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        events = next_events(days=365)
    starts = [ev.start for ev in events]
    assert starts == sorted(starts)


def test_next_events_excludes_past():
    # 2026-10-01 기준: ASML, TSM, AMD, AMAT, NVDA, AVGO, MRVL, MU 중 일부 이미 경과
    fake_now = datetime(2026, 10, 1, 9, 0, tzinfo=KST)
    with patch("info.calendar.earnings_data.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        events = next_events(days=365)
    for ev in events:
        assert ev.start >= fake_now


# ────────────────────────────────────────────────────────────────────────────
# today_us_earnings
# ────────────────────────────────────────────────────────────────────────────


def test_today_us_earnings_nvda_detected():
    # NVDA는 2026-08-26 05:00 KST 발표 → 2026-08-25 22:30 ~ 2026-08-26 08:00 범위에 포함
    fake_now = datetime(2026, 8, 25, 23, 0, tzinfo=KST)
    with patch("info.calendar.earnings_data.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        result = today_us_earnings()
    tickers = [ev.ticker for ev in result]
    assert "NVDA" in tickers


def test_today_us_earnings_returns_only_janghu():
    fake_now = datetime(2026, 8, 25, 23, 0, tzinfo=KST)
    with patch("info.calendar.earnings_data.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        result = today_us_earnings()
    assert all(ev.timing == "장후" for ev in result)


def test_today_us_earnings_empty_on_nonevent_day():
    empty_day = datetime(2026, 7, 20, 9, 0, tzinfo=KST)
    with patch("info.calendar.earnings_data.datetime") as mock_dt:
        mock_dt.now.return_value = empty_day
        result = today_us_earnings()
    assert result == []


# ────────────────────────────────────────────────────────────────────────────
# MACRO_SCHEDULE 정적 검증
# ────────────────────────────────────────────────────────────────────────────


def test_macro_schedule_not_empty():
    assert len(MACRO_SCHEDULE) >= 10


def test_macro_fomc_events_count():
    fomc = [ev for ev in MACRO_SCHEDULE if ev.category == "FOMC"]
    assert len(fomc) >= 3


def test_macro_kr_events_exist():
    kr = [ev for ev in MACRO_SCHEDULE if ev.region == "KR"]
    assert len(kr) >= 4


def test_macro_all_have_timezone():
    for ev in MACRO_SCHEDULE:
        assert ev.start.tzinfo is not None, f"{ev.summary} timezone 누락"
        assert ev.end > ev.start


# ────────────────────────────────────────────────────────────────────────────
# next_macro_events
# ────────────────────────────────────────────────────────────────────────────


def test_next_macro_events_sorted():
    fake_now = datetime(2026, 7, 1, 9, 0, tzinfo=KST)
    with patch("info.calendar.macro_events.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        events = next_macro_events(days=365)
    starts = [ev.start for ev in events]
    assert starts == sorted(starts)
    assert len(events) > 0


def test_next_macro_events_contains_fomc():
    fake_now = datetime(2026, 7, 1, 9, 0, tzinfo=KST)
    with patch("info.calendar.macro_events.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        events = next_macro_events(days=365)
    assert any(ev.category == "FOMC" for ev in events)


# ────────────────────────────────────────────────────────────────────────────
# today_kr_macro
# ────────────────────────────────────────────────────────────────────────────


def test_today_kr_macro_fomc_day():
    # FOMC 결정(2026-07-30 03:00 KST) → 당일 이벤트로 반환
    fomc_day = datetime(2026, 7, 30, 9, 0, tzinfo=KST)
    with patch("info.calendar.macro_events.datetime") as mock_dt:
        mock_dt.now.return_value = fomc_day
        result = today_kr_macro()
    assert any(ev.category == "FOMC" for ev in result)


def test_today_kr_macro_empty_nonevent():
    empty_day = datetime(2026, 7, 20, 9, 0, tzinfo=KST)
    with patch("info.calendar.macro_events.datetime") as mock_dt:
        mock_dt.now.return_value = empty_day
        result = today_kr_macro()
    assert result == []
