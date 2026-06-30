"""
Google Calendar API 연동.

gcsa(Google Calendar Simple API) OAuth2로 이벤트를 추가한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import pytz

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

# 색상 코딩 (스펙 3절)
COLOR_MAP: dict[str, int] = {
    "CRITICAL": 11,  # Tomato
    "HIGH": 6,       # Tangerine
    "MEDIUM": 5,     # Banana
    "FX": 7,         # Peacock
    "KR": 2,         # Sage
}

# 알람 설정 (분 단위)
ALARM_MAP: dict[str, list[int]] = {
    "FOMC": [120, 30],
    "NVDA": [120, 30],
    "MU": [120, 30],
    "CPI": [60],
    "NFP": [60],
    "TSM": [60],
    "DEFAULT": [30],
}

_MAX_RETRIES = 3


@dataclass
class CalEvent:
    """Google Calendar 이벤트 데이터."""

    summary: str
    start: datetime
    end: datetime
    importance: Literal["CRITICAL", "HIGH", "MEDIUM", "FX", "KR"]
    description: str = ""


class GoogleCalendarClient:
    """gcsa 기반 Google Calendar 클라이언트."""

    def __init__(self, credentials_path: str | Path) -> None:
        self._credentials_path = Path(credentials_path).expanduser()
        self._cal = None

    def _get_cal(self):
        """gcsa 클라이언트 초기화 (lazy)."""
        if self._cal is None:
            from gcsa.google_calendar import GoogleCalendar

            token_path = self._credentials_path.parent / "token.json"
            self._cal = GoogleCalendar(
                credentials_path=str(self._credentials_path),
                token_path=str(token_path),
            )
        return self._cal

    def _pick_alarms(self, summary: str) -> list[int]:
        """이벤트 제목에서 알람 설정 분을 결정한다."""
        for keyword, minutes in ALARM_MAP.items():
            if keyword != "DEFAULT" and keyword in summary:
                return minutes
        return ALARM_MAP["DEFAULT"]

    async def add_event(self, event: CalEvent) -> None:
        """이벤트를 Calendar에 추가한다. 중복이면 스킵."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._add_event_sync, event)

    def _add_event_sync(self, event: CalEvent) -> None:
        from gcsa.event import Event
        from gcsa.reminders import EmailReminder, PopupReminder
        from beautiful_date import hours, minutes as bdminutes

        cal = self._get_cal()

        # 중복 방지: 같은 summary + start가 있으면 스킵
        try:
            existing = list(
                cal.get_events(
                    time_min=event.start - timedelta(minutes=1),
                    time_max=event.start + timedelta(minutes=1),
                )
            )
            for ev in existing:
                if ev.summary == event.summary:
                    logger.debug("중복 이벤트 스킵: %s @ %s", event.summary, event.start)
                    return
        except Exception as exc:
            logger.warning("중복 확인 실패, 추가 시도: %s", exc)

        color_id = COLOR_MAP.get(event.importance, 5)
        alarm_minutes = self._pick_alarms(event.summary)
        reminders = [PopupReminder(minutes_before_start=m) for m in alarm_minutes]

        new_ev = Event(
            summary=event.summary,
            start=event.start,
            end=event.end,
            description=event.description,
            color_id=color_id,
            reminders=reminders,
        )

        delay = 1.0
        for attempt in range(_MAX_RETRIES):
            try:
                cal.add_event(new_ev)
                return
            except Exception as exc:
                status = getattr(exc, "status_code", None) or getattr(exc, "resp", {}).get("status")
                if str(status) == "401":
                    logger.warning("Calendar 401 — 토큰 갱신 후 재시도")
                    self._cal = None  # lazy 재초기화로 토큰 갱신
                    cal = self._get_cal()  # 새 클라이언트로 교체
                elif str(status) == "429":
                    if attempt < _MAX_RETRIES - 1:
                        logger.warning("Calendar 429 — %.0fs 후 재시도 (%d/%d)", delay, attempt + 1, _MAX_RETRIES)
                        import time
                        time.sleep(delay)
                        delay *= 2
                        continue
                    else:
                        logger.error("Calendar 429 소진 — 이벤트 스킵: %s", event.summary)
                        return
                else:
                    logger.error("Calendar 이벤트 추가 실패 (%d/%d): %s", attempt + 1, _MAX_RETRIES, exc)

                if attempt < _MAX_RETRIES - 1:
                    import time
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error("Calendar 이벤트 추가 최종 실패: %s", event.summary)

    async def bulk_add(self, events: list[CalEvent]) -> None:
        """여러 이벤트를 순차적으로 추가한다. 개별 실패 시 다음 이벤트 진행."""
        for event in events:
            try:
                await self.add_event(event)
            except Exception as exc:
                logger.error("bulk_add 이벤트 실패 — 다음 이벤트 계속: %s (%s)", event.summary, exc)
