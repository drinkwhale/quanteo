"""
실적발표 일정 데이터 (2026 하반기).

스펙 2-4절 기준 하드코딩. EarningsEvent는 CalEvent 서브클래스.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import pytz

from info.calendar.google_cal import CalEvent

KST = pytz.timezone("Asia/Seoul")


@dataclass
class EarningsEvent(CalEvent):
    """실적발표 이벤트 (CalEvent 확장)."""

    ticker: str = ""
    consensus_eps: str | None = None
    consensus_sales: str | None = None
    timing: Literal["장전", "장중", "장후"] = "장후"
    sk_impact: Literal["🔴 최고", "🔴 높음", "🟡 중간"] = "🟡 중간"


def _kst(year: int, month: int, day: int, hour: int = 5, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=KST)


# ---------------------------------------------------------------------------
# 2026 하반기 실적 발표 스케줄
# ---------------------------------------------------------------------------

EARNINGS_SCHEDULE: list[EarningsEvent] = [
    EarningsEvent(
        summary="ASML 실적발표",
        ticker="ASML",
        start=_kst(2026, 7, 15, 14, 0),
        end=_kst(2026, 7, 15, 15, 0),
        importance="HIGH",
        description="EUV 수주잔고 / Q2 €8.4~9.0B 가이던스",
        timing="장전",
        consensus_eps="€5.20",
        consensus_sales="€8.7B",
        sk_impact="🟡 중간",
    ),
    EarningsEvent(
        summary="TSM 실적발표",
        ticker="TSM",
        start=_kst(2026, 7, 16, 10, 0),
        end=_kst(2026, 7, 16, 11, 0),
        importance="CRITICAL",
        description="HBM 수요 / AI·HPC 2026 달러매출 +30% 가이던스",
        timing="장중",
        consensus_eps="$2.85",
        consensus_sales="$30.2B",
        sk_impact="🔴 최고",
    ),
    EarningsEvent(
        summary="AMD 실적발표",
        ticker="AMD",
        start=_kst(2026, 8, 4, 5, 0),
        end=_kst(2026, 8, 4, 6, 0),
        importance="CRITICAL",
        description="MI400 GPU / Q2 $11.2B 가이던스 (+46% YoY)",
        timing="장후",
        consensus_eps="$0.87",
        consensus_sales="$11.2B",
        sk_impact="🔴 높음",
    ),
    EarningsEvent(
        summary="NVDA 실적발표",
        ticker="NVDA",
        start=_kst(2026, 8, 26, 5, 0),
        end=_kst(2026, 8, 26, 6, 0),
        importance="CRITICAL",
        description="Blackwell 수요 / HBM 최대 고객 / SK하이닉스 직결",
        timing="장후",
        consensus_eps="$0.72",
        consensus_sales="$45.0B",
        sk_impact="🔴 최고",
    ),
    EarningsEvent(
        summary="AVGO 실적발표",
        ticker="AVGO",
        start=_kst(2026, 9, 3, 5, 0),
        end=_kst(2026, 9, 3, 6, 0),
        importance="HIGH",
        description="AI ASIC / Q3 AI반도체 $16B (+200%+ YoY)",
        timing="장후",
        consensus_eps="$1.57",
        consensus_sales="$15.8B",
        sk_impact="🟡 중간",
    ),
    EarningsEvent(
        summary="MU 실적발표",
        ticker="MU",
        start=_kst(2026, 9, 22, 5, 0),
        end=_kst(2026, 9, 22, 6, 0),
        importance="CRITICAL",
        description="HBM/DRAM 직접 경쟁·동반 / 메모리 업황 바로미터",
        timing="장후",
        consensus_eps="$1.85",
        consensus_sales="$9.7B",
        sk_impact="🔴 최고",
    ),
    # 추가 관심 종목
    EarningsEvent(
        summary="AMAT 실적발표",
        ticker="AMAT",
        start=_kst(2026, 8, 15, 5, 0),
        end=_kst(2026, 8, 15, 6, 0),
        importance="MEDIUM",
        description="반도체 장비 — DRAM 투자 선행지표",
        timing="장후",
        sk_impact="🟡 중간",
    ),
    EarningsEvent(
        summary="MRVL 실적발표",
        ticker="MRVL",
        start=_kst(2026, 9, 4, 5, 0),
        end=_kst(2026, 9, 4, 6, 0),
        importance="MEDIUM",
        description="AI 커스텀칩 / 데이터센터",
        timing="장후",
        sk_impact="🟡 중간",
    ),
]


def next_events(days: int = 7) -> list[CalEvent]:
    """오늘 기준 N일 내 이벤트를 반환한다."""
    now = datetime.now(tz=KST)
    cutoff = now + timedelta(days=days)
    result: list[CalEvent] = []
    for ev in EARNINGS_SCHEDULE:
        if now <= ev.start <= cutoff:
            result.append(ev)
    return sorted(result, key=lambda e: e.start)


def today_us_earnings() -> list[EarningsEvent]:
    """오늘 미국 장후(22:30~익일 08:00 KST) 발표 예정 종목을 반환한다."""
    now = datetime.now(tz=KST)
    today_open = now.replace(hour=22, minute=30, second=0, microsecond=0)
    tomorrow_close = today_open + timedelta(hours=9, minutes=30)  # 익일 08:00 KST

    result: list[EarningsEvent] = []
    for ev in EARNINGS_SCHEDULE:
        if not isinstance(ev, EarningsEvent):
            continue
        if ev.timing == "장후" and today_open <= ev.start <= tomorrow_close:
            result.append(ev)
    return sorted(result, key=lambda e: e.start)
