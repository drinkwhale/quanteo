"""
거시경제 이벤트 캘린더 데이터 (2026 하반기).

미국 FOMC/CPI/NFP/PCE/GDP, 한국 기준금리/수출입통계, 중국 PMI 포함.
SK하이닉스 매매 판단에 영향을 주는 핵심 지표만 수록.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import pytz

from info.calendar.google_cal import CalEvent

KST = pytz.timezone("Asia/Seoul")


@dataclass
class MacroEvent(CalEvent):
    """거시경제 이벤트 (CalEvent 확장)."""

    region: Literal["US", "KR", "CN"] = "US"
    category: str = ""  # FOMC / CPI / NFP / PCE / GDP / BOK / TRADE / PMI


def _kst(year: int, month: int, day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=KST)


# ---------------------------------------------------------------------------
# 2026 하반기 거시경제 이벤트 스케줄
# ---------------------------------------------------------------------------
# US 지표 KST 변환 기준:
#   EDT (UTC-4, 여름): 8:30 AM ET → 21:30 KST / 2:00 PM ET → 03:00 KST 익일
#   EST (UTC-5, 겨울 11월~): 8:30 AM ET → 22:30 KST / 2:00 PM ET → 04:00 KST 익일

MACRO_SCHEDULE: list[MacroEvent] = [
    # ── FOMC 금리결정 ──────────────────────────────────────────────────────
    MacroEvent(
        summary="FOMC 금리결정",
        start=_kst(2026, 7, 30, 3, 0),
        end=_kst(2026, 7, 30, 4, 0),
        importance="CRITICAL",
        description="연준 금리결정 / 파월 기자회견 / 점도표",
        region="US",
        category="FOMC",
    ),
    MacroEvent(
        summary="FOMC 금리결정",
        start=_kst(2026, 9, 17, 3, 0),
        end=_kst(2026, 9, 17, 4, 0),
        importance="CRITICAL",
        description="연준 금리결정 / 파월 기자회견 / SEP 점도표",
        region="US",
        category="FOMC",
    ),
    MacroEvent(
        summary="FOMC 금리결정",
        start=_kst(2026, 10, 29, 3, 0),
        end=_kst(2026, 10, 29, 4, 0),
        importance="CRITICAL",
        description="연준 금리결정 / 파월 기자회견",
        region="US",
        category="FOMC",
    ),
    MacroEvent(
        summary="FOMC 금리결정",
        start=_kst(2026, 12, 10, 4, 0),   # EST: +14h
        end=_kst(2026, 12, 10, 5, 0),
        importance="CRITICAL",
        description="연준 금리결정 / 파월 기자회견 / SEP 점도표",
        region="US",
        category="FOMC",
    ),
    # ── CPI ──────────────────────────────────────────────────────────────
    MacroEvent(
        summary="미국 CPI (6월)",
        start=_kst(2026, 7, 14, 21, 30),
        end=_kst(2026, 7, 14, 22, 0),
        importance="HIGH",
        description="헤드라인 CPI / 근원 CPI (식품·에너지 제외)",
        region="US",
        category="CPI",
    ),
    MacroEvent(
        summary="미국 CPI (7월)",
        start=_kst(2026, 8, 12, 21, 30),
        end=_kst(2026, 8, 12, 22, 0),
        importance="HIGH",
        description="헤드라인 CPI / 근원 CPI",
        region="US",
        category="CPI",
    ),
    MacroEvent(
        summary="미국 CPI (8월)",
        start=_kst(2026, 9, 10, 21, 30),
        end=_kst(2026, 9, 10, 22, 0),
        importance="HIGH",
        description="헤드라인 CPI / 근원 CPI / FOMC 1주전",
        region="US",
        category="CPI",
    ),
    MacroEvent(
        summary="미국 CPI (9월)",
        start=_kst(2026, 10, 14, 21, 30),
        end=_kst(2026, 10, 14, 22, 0),
        importance="HIGH",
        description="헤드라인 CPI / 근원 CPI",
        region="US",
        category="CPI",
    ),
    MacroEvent(
        summary="미국 CPI (10월)",
        start=_kst(2026, 11, 13, 22, 30),  # EST 전환 후
        end=_kst(2026, 11, 13, 23, 0),
        importance="HIGH",
        description="헤드라인 CPI / 근원 CPI",
        region="US",
        category="CPI",
    ),
    MacroEvent(
        summary="미국 CPI (11월)",
        start=_kst(2026, 12, 10, 22, 30),
        end=_kst(2026, 12, 10, 23, 0),
        importance="HIGH",
        description="헤드라인 CPI / 근원 CPI / FOMC 당일",
        region="US",
        category="CPI",
    ),
    # ── NFP ──────────────────────────────────────────────────────────────
    MacroEvent(
        summary="미국 NFP (6월)",
        start=_kst(2026, 7, 2, 21, 30),
        end=_kst(2026, 7, 2, 22, 0),
        importance="HIGH",
        description="비농업 고용 / 실업률 / 임금 상승률",
        region="US",
        category="NFP",
    ),
    MacroEvent(
        summary="미국 NFP (7월)",
        start=_kst(2026, 8, 7, 21, 30),
        end=_kst(2026, 8, 7, 22, 0),
        importance="HIGH",
        description="비농업 고용 / 실업률 / 임금 상승률",
        region="US",
        category="NFP",
    ),
    MacroEvent(
        summary="미국 NFP (8월)",
        start=_kst(2026, 9, 4, 21, 30),
        end=_kst(2026, 9, 4, 22, 0),
        importance="HIGH",
        description="비농업 고용 / 실업률 / 임금 상승률",
        region="US",
        category="NFP",
    ),
    MacroEvent(
        summary="미국 NFP (9월)",
        start=_kst(2026, 10, 2, 21, 30),
        end=_kst(2026, 10, 2, 22, 0),
        importance="HIGH",
        description="비농업 고용 / 실업률 / 임금 상승률",
        region="US",
        category="NFP",
    ),
    MacroEvent(
        summary="미국 NFP (10월)",
        start=_kst(2026, 11, 6, 22, 30),  # EST
        end=_kst(2026, 11, 6, 23, 0),
        importance="HIGH",
        description="비농업 고용 / 실업률 / 임금 상승률",
        region="US",
        category="NFP",
    ),
    MacroEvent(
        summary="미국 NFP (11월)",
        start=_kst(2026, 12, 4, 22, 30),
        end=_kst(2026, 12, 4, 23, 0),
        importance="HIGH",
        description="비농업 고용 / 실업률 / 임금 상승률",
        region="US",
        category="NFP",
    ),
    # ── GDP 속보치 ────────────────────────────────────────────────────────
    MacroEvent(
        summary="미국 GDP 속보치 (Q2 2026)",
        start=_kst(2026, 7, 30, 21, 30),
        end=_kst(2026, 7, 30, 22, 0),
        importance="HIGH",
        description="Q2 GDP 성장률 속보치 / FOMC 당일 발표",
        region="US",
        category="GDP",
    ),
    MacroEvent(
        summary="미국 GDP 속보치 (Q3 2026)",
        start=_kst(2026, 10, 29, 21, 30),
        end=_kst(2026, 10, 29, 22, 0),
        importance="HIGH",
        description="Q3 GDP 성장률 속보치 / FOMC 당일 발표",
        region="US",
        category="GDP",
    ),
    # ── PCE ──────────────────────────────────────────────────────────────
    MacroEvent(
        summary="미국 PCE (6월)",
        start=_kst(2026, 7, 31, 21, 30),
        end=_kst(2026, 7, 31, 22, 0),
        importance="MEDIUM",
        description="연준 선호 인플레이션 지표 / FOMC 이후 주요 재료",
        region="US",
        category="PCE",
    ),
    MacroEvent(
        summary="미국 PCE (8월)",
        start=_kst(2026, 9, 25, 21, 30),
        end=_kst(2026, 9, 25, 22, 0),
        importance="MEDIUM",
        description="연준 선호 인플레이션 지표",
        region="US",
        category="PCE",
    ),
    # ── 한국 기준금리 ─────────────────────────────────────────────────────
    MacroEvent(
        summary="한국은행 기준금리 결정",
        start=_kst(2026, 7, 9, 10, 0),
        end=_kst(2026, 7, 9, 11, 0),
        importance="KR",
        description="금융통화위원회 기준금리 결정 / 통화정책방향 의결문",
        region="KR",
        category="BOK",
    ),
    MacroEvent(
        summary="한국은행 기준금리 결정",
        start=_kst(2026, 8, 27, 10, 0),
        end=_kst(2026, 8, 27, 11, 0),
        importance="KR",
        description="금융통화위원회 기준금리 결정",
        region="KR",
        category="BOK",
    ),
    MacroEvent(
        summary="한국은행 기준금리 결정",
        start=_kst(2026, 10, 15, 10, 0),
        end=_kst(2026, 10, 15, 11, 0),
        importance="KR",
        description="금융통화위원회 기준금리 결정",
        region="KR",
        category="BOK",
    ),
    MacroEvent(
        summary="한국은행 기준금리 결정",
        start=_kst(2026, 11, 26, 10, 0),
        end=_kst(2026, 11, 26, 11, 0),
        importance="KR",
        description="금융통화위원회 기준금리 결정",
        region="KR",
        category="BOK",
    ),
    # ── 한국 수출입통계 (반도체 수출 핵심 선행지표) ───────────────────────
    MacroEvent(
        summary="한국 수출입통계 (7월)",
        start=_kst(2026, 8, 1, 8, 0),
        end=_kst(2026, 8, 1, 8, 30),
        importance="KR",
        description="수출 YoY / 반도체 수출 / 대미·대중 무역수지",
        region="KR",
        category="TRADE",
    ),
    MacroEvent(
        summary="한국 수출입통계 (8월)",
        start=_kst(2026, 9, 1, 8, 0),
        end=_kst(2026, 9, 1, 8, 30),
        importance="KR",
        description="수출 YoY / 반도체 수출",
        region="KR",
        category="TRADE",
    ),
    MacroEvent(
        summary="한국 수출입통계 (9월)",
        start=_kst(2026, 10, 1, 8, 0),
        end=_kst(2026, 10, 1, 8, 30),
        importance="KR",
        description="수출 YoY / 반도체 수출",
        region="KR",
        category="TRADE",
    ),
    MacroEvent(
        summary="한국 수출입통계 (10월)",
        start=_kst(2026, 11, 1, 8, 0),
        end=_kst(2026, 11, 1, 8, 30),
        importance="KR",
        description="수출 YoY / 반도체 수출",
        region="KR",
        category="TRADE",
    ),
    MacroEvent(
        summary="한국 수출입통계 (11월)",
        start=_kst(2026, 12, 1, 8, 0),
        end=_kst(2026, 12, 1, 8, 30),
        importance="KR",
        description="수출 YoY / 반도체 수출",
        region="KR",
        category="TRADE",
    ),
    # ── 중국 제조업 PMI (반도체 수요 선행지표) ────────────────────────────
    MacroEvent(
        summary="중국 제조업 PMI (7월)",
        start=_kst(2026, 7, 31, 10, 0),
        end=_kst(2026, 7, 31, 10, 30),
        importance="MEDIUM",
        description="국가통계국 제조업 PMI / 50 기준 경기확장/수축",
        region="CN",
        category="PMI",
    ),
    MacroEvent(
        summary="중국 제조업 PMI (8월)",
        start=_kst(2026, 8, 31, 10, 0),
        end=_kst(2026, 8, 31, 10, 30),
        importance="MEDIUM",
        description="국가통계국 제조업 PMI",
        region="CN",
        category="PMI",
    ),
    MacroEvent(
        summary="중국 제조업 PMI (9월)",
        start=_kst(2026, 9, 30, 10, 0),
        end=_kst(2026, 9, 30, 10, 30),
        importance="MEDIUM",
        description="국가통계국 제조업 PMI",
        region="CN",
        category="PMI",
    ),
    MacroEvent(
        summary="중국 제조업 PMI (10월)",
        start=_kst(2026, 10, 31, 10, 0),
        end=_kst(2026, 10, 31, 10, 30),
        importance="MEDIUM",
        description="국가통계국 제조업 PMI",
        region="CN",
        category="PMI",
    ),
    MacroEvent(
        summary="중국 제조업 PMI (11월)",
        start=_kst(2026, 11, 30, 10, 0),
        end=_kst(2026, 11, 30, 10, 30),
        importance="MEDIUM",
        description="국가통계국 제조업 PMI",
        region="CN",
        category="PMI",
    ),
]


def next_macro_events(days: int = 7) -> list[MacroEvent]:
    """오늘 기준 N일 내 거시경제 이벤트를 반환한다."""
    now = datetime.now(tz=KST)
    cutoff = now + timedelta(days=days)
    result = [ev for ev in MACRO_SCHEDULE if now <= ev.start <= cutoff]
    return sorted(result, key=lambda e: e.start)


def today_kr_macro() -> list[MacroEvent]:
    """오늘(KST 기준) 발표되는 거시경제 이벤트를 반환한다."""
    now = datetime.now(tz=KST)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    result = [ev for ev in MACRO_SCHEDULE if day_start <= ev.start <= day_end]
    return sorted(result, key=lambda e: e.start)
