"""
통합 테스트: 실적발표 데이터 → Google Calendar 저장 → 중복 방지 라운드트립.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz

from info.calendar.earnings_data import EARNINGS_SCHEDULE, EarningsEvent
from info.calendar.google_cal import CalEvent, GoogleCalendarClient

KST = pytz.timezone("Asia/Seoul")


def _nvda_event() -> EarningsEvent:
    return next(ev for ev in EARNINGS_SCHEDULE if ev.ticker == "NVDA")


# ────────────────────────────────────────────────────────────────────────────
# 테스트
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_earnings_event_added_to_calendar():
    """EarningsEvent가 GoogleCalendarClient.add_event를 통해 추가되어야 한다."""
    client = GoogleCalendarClient("~/.quanteo/google/credentials.json")
    nvda = _nvda_event()

    added = []
    mock_cal = MagicMock()
    mock_cal.get_events.return_value = []
    mock_cal.add_event.side_effect = lambda ev: added.append(ev)

    with patch.object(client, "_get_cal", return_value=mock_cal):
        await client.add_event(nvda)

    assert len(added) == 1
    assert added[0].summary == "NVDA 실적발표"


@pytest.mark.asyncio
async def test_duplicate_earnings_event_skipped():
    """동일 summary + start 이벤트는 두 번 추가되지 않아야 한다."""
    client = GoogleCalendarClient("~/.quanteo/google/credentials.json")
    nvda = _nvda_event()

    existing = [MagicMock(summary=nvda.summary)]
    mock_cal = MagicMock()
    mock_cal.get_events.return_value = existing

    with patch.object(client, "_get_cal", return_value=mock_cal):
        await client.add_event(nvda)

    mock_cal.add_event.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_add_continues_on_individual_failure():
    """bulk_add에서 일부 이벤트 실패해도 나머지는 처리되어야 한다."""
    client = GoogleCalendarClient("~/.quanteo/google/credentials.json")

    events = list(EARNINGS_SCHEDULE[:3])
    call_count = {"n": 0}

    mock_cal = MagicMock()
    mock_cal.get_events.return_value = []

    def _sometimes_fail(ev):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("첫 번째 이벤트 실패")

    mock_cal.add_event.side_effect = _sometimes_fail

    with patch.object(client, "_get_cal", return_value=mock_cal):
        await client.bulk_add(events)

    # 세 이벤트 모두 add_event 시도됨 (첫 번째 실패해도 두 번째, 세 번째 진행)
    assert mock_cal.add_event.call_count >= 2


@pytest.mark.asyncio
async def test_critical_earnings_gets_correct_color():
    """CRITICAL 중요도 이벤트는 COLOR_MAP["CRITICAL"] 색상을 가져야 한다."""
    from info.calendar.google_cal import COLOR_MAP

    client = GoogleCalendarClient("~/.quanteo/google/credentials.json")
    nvda = _nvda_event()
    assert nvda.importance == "CRITICAL"

    added = []
    mock_cal = MagicMock()
    mock_cal.get_events.return_value = []
    mock_cal.add_event.side_effect = lambda ev: added.append(ev)

    with patch.object(client, "_get_cal", return_value=mock_cal):
        await client.add_event(nvda)

    assert added[0].color_id == COLOR_MAP["CRITICAL"]


@pytest.mark.asyncio
async def test_macro_event_added_to_calendar():
    """MacroEvent도 CalEvent 서브클래스로 Calendar에 추가될 수 있어야 한다."""
    from info.calendar.macro_events import MACRO_SCHEDULE

    fomc = next(ev for ev in MACRO_SCHEDULE if ev.category == "FOMC")
    client = GoogleCalendarClient("~/.quanteo/google/credentials.json")

    added = []
    mock_cal = MagicMock()
    mock_cal.get_events.return_value = []
    mock_cal.add_event.side_effect = lambda ev: added.append(ev)

    with patch.object(client, "_get_cal", return_value=mock_cal):
        await client.add_event(fomc)

    assert len(added) == 1
    assert "FOMC" in added[0].summary
