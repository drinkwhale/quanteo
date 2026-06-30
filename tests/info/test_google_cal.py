"""GoogleCalendarClient 단위 테스트."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import pytz

from info.calendar.google_cal import CalEvent, GoogleCalendarClient, COLOR_MAP

KST = pytz.timezone("Asia/Seoul")


def _event(
    summary: str = "NVDA 실적",
    importance: str = "CRITICAL",
    offset_hours: int = 1,
) -> CalEvent:
    start = datetime(2026, 8, 26, 5, 0, 0, tzinfo=KST)
    return CalEvent(
        summary=summary,
        start=start,
        end=start + timedelta(hours=offset_hours),
        importance=importance,  # type: ignore
        description="테스트 설명",
    )


def _mock_cal(existing_events=None):
    cal = MagicMock()
    cal.get_events.return_value = existing_events or []
    cal.add_event = MagicMock()
    return cal


# ---------------------------------------------------------------------------
# 색상 코딩 및 알람 설정
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critical_event_color():
    client = GoogleCalendarClient("~/.quanteo/google/credentials.json")
    added = []

    def _mock_add(ev):
        added.append(ev)

    mock_cal = _mock_cal()
    mock_cal.add_event.side_effect = _mock_add

    with patch.object(client, "_get_cal", return_value=mock_cal):
        await client.add_event(_event(summary="NVDA 실적발표", importance="CRITICAL"))

    assert len(added) == 1
    assert added[0].color_id == COLOR_MAP["CRITICAL"]


@pytest.mark.asyncio
async def test_nvda_event_double_alarm():
    """NVDA 이벤트는 2중 알람(120분+30분) 설정."""
    client = GoogleCalendarClient("~/.quanteo/google/credentials.json")
    added = []

    def _mock_add(ev):
        added.append(ev)

    mock_cal = _mock_cal()
    mock_cal.add_event.side_effect = _mock_add

    with patch.object(client, "_get_cal", return_value=mock_cal):
        await client.add_event(_event(summary="NVDA 실적발표", importance="CRITICAL"))

    assert len(added[0].reminders) == 2
    alarm_mins = {r.minutes_before_start for r in added[0].reminders}
    assert alarm_mins == {120, 30}


# ---------------------------------------------------------------------------
# 중복 방지
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_event_skipped():
    client = GoogleCalendarClient("~/.quanteo/google/credentials.json")
    ev = _event(summary="NVDA 실적발표")

    existing = [MagicMock(summary="NVDA 실적발표")]
    mock_cal = _mock_cal(existing_events=existing)

    with patch.object(client, "_get_cal", return_value=mock_cal):
        await client.add_event(ev)

    mock_cal.add_event.assert_not_called()


# ---------------------------------------------------------------------------
# 401 → 토큰 갱신 트리거
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_triggers_token_refresh():
    client = GoogleCalendarClient("~/.quanteo/google/credentials.json")
    call_count = {"n": 0}

    mock_cal1 = _mock_cal()
    mock_cal2 = _mock_cal()

    def _fail_then_succeed(ev):
        call_count["n"] += 1
        if call_count["n"] == 1:
            exc = Exception("token expired")
            exc.status_code = 401
            raise exc

    mock_cal1.add_event.side_effect = _fail_then_succeed
    mock_cal2.add_event = MagicMock()

    cals = iter([mock_cal1, mock_cal2])

    with patch.object(client, "_get_cal", side_effect=lambda: next(cals)):
        with patch("time.sleep"):
            await client.add_event(_event())

    mock_cal2.add_event.assert_called_once()


# ---------------------------------------------------------------------------
# 429 → 백오프 후 다음 이벤트 처리
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_429_backoff_continues_bulk():
    client = GoogleCalendarClient("~/.quanteo/google/credentials.json")

    ev1 = _event(summary="CPI 발표", importance="CRITICAL")
    ev2 = _event(summary="NFP 발표", importance="HIGH")

    mock_cal = _mock_cal()
    call_count = {"n": 0}

    def _always_429(ev):
        exc = Exception("quota exceeded")
        exc.status_code = 429
        raise exc

    mock_cal.add_event.side_effect = _always_429

    with patch.object(client, "_get_cal", return_value=mock_cal):
        with patch("time.sleep"):
            # bulk_add은 첫 이벤트 실패해도 두 번째 시도
            await client.bulk_add([ev1, ev2])

    # 두 이벤트 모두 시도됨 (각 3회 재시도)
    assert mock_cal.add_event.call_count >= 2
