"""CCI+BBC 통합 전략 플러그인 테스트.

4단계 의사결정 전체 시나리오, 스코어링 합산, 분할매수 수량, score < 0 → position_size = 0.0.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.strategy.plugins.cci_bbc_strategy import (
    ReliabilityScore,
    calculate_position_size,
    compute_reliability_score,
)
from core.strategy.plugins.intraday_signal import IntradaySignalType
from core.strategy.timeframe_judge import MarketDirection


# ============================================================================
# ReliabilityScore 테스트
# ============================================================================


def test_score_aggressive():
    """7점 이상 → 적극매수."""
    score = ReliabilityScore.from_breakdown(
        {
            "monthly_gc": 1,
            "weekly_gc": 1,
            "daily_gc": 2,
            "sixty_min_gc": 1,
            "volume_surge": 1,
            "intraday_positive": 1,
            "alignment": 1,
        }
    )
    assert score.score == 8
    assert score.action == "적극매수"


def test_score_conservative():
    """4~6점 → 소극매수."""
    score = ReliabilityScore.from_breakdown(
        {
            "monthly_gc": 1,
            "weekly_gc": 1,
            "daily_gc": 2,
        }
    )
    assert score.score == 4
    assert score.action == "소극매수"


def test_score_wait():
    """0~3점 → 관망."""
    score = ReliabilityScore.from_breakdown(
        {
            "monthly_gc": 1,
        }
    )
    assert score.score == 1
    assert score.action == "관망"


def test_score_sell():
    """음수 → 매도검토."""
    score = ReliabilityScore.from_breakdown(
        {
            "daily_dc": -2,
            "intraday_type4": -2,
        }
    )
    assert score.score == -4
    assert score.action == "매도검토"


def test_score_positive_max_8():
    """양성 항목 합계 최대 8점 검증."""
    # 모든 양성 항목 합산: 1+1+2+1+1+1+1 = 8
    score = ReliabilityScore.from_breakdown(
        {
            "monthly_gc": 1,    # +1
            "weekly_gc": 1,     # +1
            "daily_gc": 2,      # +2 (가중치 2배)
            "sixty_min_gc": 1,  # +1
            "volume_surge": 1,  # +1
            "intraday_positive": 1,  # +1
            "alignment": 1,     # +1
        }
    )
    assert score.score == 8


# ============================================================================
# calculate_position_size 테스트
# ============================================================================


def test_position_size_aggressive():
    """적극매수(7점 이상) → 30%."""
    assert calculate_position_size(7, 1_000_000) == pytest.approx(0.30)
    assert calculate_position_size(8, 1_000_000) == pytest.approx(0.30)


def test_position_size_conservative():
    """소극매수(4~6점) → 10%."""
    assert calculate_position_size(4, 1_000_000) == pytest.approx(0.10)
    assert calculate_position_size(6, 1_000_000) == pytest.approx(0.10)


def test_position_size_wait():
    """관망(0~3점) → 0%."""
    assert calculate_position_size(3, 1_000_000) == 0.0
    assert calculate_position_size(0, 1_000_000) == 0.0


def test_position_size_negative_score():
    """음수 스코어 → 0.0 (음수에서 양수 비율 반환 방지)."""
    assert calculate_position_size(-1, 1_000_000) == 0.0
    assert calculate_position_size(-5, 1_000_000) == 0.0


# ============================================================================
# compute_reliability_score 테스트
# ============================================================================


def _all_bullish_directions() -> dict[str, MarketDirection]:
    return {
        "monthly": MarketDirection.BULLISH,
        "weekly": MarketDirection.BULLISH,
        "daily": MarketDirection.BULLISH,
        "sixty_min": MarketDirection.BULLISH,
    }


def test_compute_full_score():
    """모든 양성 조건 충족 시 8점."""
    cci = [50.0, 60.0]    # 골든크로스용 (prev <= signal, curr > signal)
    signal = [55.0, 55.0]  # cci[-2](50) <= signal[-2](55), cci[-1](60) > signal[-1](55) → GC

    score = compute_reliability_score(
        mtf_directions=_all_bullish_directions(),
        daily_cci=cci,
        daily_signal=signal,
        current_volume=2000,
        volume_ma20=1000.0,
        ma5=110.0,
        ma20=100.0,
        intraday_type=IntradaySignalType.TYPE_1,
        has_45deg_decline=False,
    )
    assert score.score == 8
    assert score.action == "적극매수"
    assert score.breakdown["daily_gc"] == 2


def test_compute_dead_cross_penalty():
    """일봉 데드크로스 발생 시 -2점."""
    cci = [70.0, 50.0]    # 데드크로스: prev >= signal, curr < signal
    signal = [60.0, 60.0]  # cci[-2](70) >= signal[-2](60), cci[-1](50) < signal[-1](60) → DC

    score = compute_reliability_score(
        mtf_directions={"monthly": MarketDirection.BULLISH, "weekly": MarketDirection.NEUTRAL,
                        "daily": MarketDirection.NEUTRAL, "sixty_min": MarketDirection.NEUTRAL},
        daily_cci=cci,
        daily_signal=signal,
        current_volume=500,
        volume_ma20=1000.0,
        ma5=100.0,
        ma20=105.0,   # 역배열
        intraday_type=IntradaySignalType.NONE,
        has_45deg_decline=False,
    )
    assert "daily_dc" in score.breakdown
    assert score.breakdown["daily_dc"] == -2


def test_compute_type4_penalty():
    """④번 유형 발생 시 -2점."""
    score = compute_reliability_score(
        mtf_directions={"monthly": MarketDirection.BULLISH, "weekly": MarketDirection.NEUTRAL,
                        "daily": MarketDirection.NEUTRAL, "sixty_min": MarketDirection.NEUTRAL},
        daily_cci=[50.0, 60.0],
        daily_signal=[60.0, 55.0],
        current_volume=500,
        volume_ma20=1000.0,
        ma5=105.0,
        ma20=100.0,
        intraday_type=IntradaySignalType.TYPE_4,
        has_45deg_decline=False,
    )
    assert "intraday_type4" in score.breakdown
    assert score.breakdown["intraday_type4"] == -2


def test_compute_45deg_penalty():
    """45도 하락 패턴 시 -1점."""
    score = compute_reliability_score(
        mtf_directions={"monthly": MarketDirection.BULLISH, "weekly": MarketDirection.NEUTRAL,
                        "daily": MarketDirection.NEUTRAL, "sixty_min": MarketDirection.NEUTRAL},
        daily_cci=[50.0, 60.0],
        daily_signal=[60.0, 55.0],
        current_volume=500,
        volume_ma20=1000.0,
        ma5=105.0,
        ma20=100.0,
        intraday_type=IntradaySignalType.NONE,
        has_45deg_decline=True,
    )
    assert "decline_45deg" in score.breakdown
    assert score.breakdown["decline_45deg"] == -1


def test_compute_volume_surge():
    """거래량 1.5배 이상 시 +1점."""
    score = compute_reliability_score(
        mtf_directions={"monthly": MarketDirection.NEUTRAL, "weekly": MarketDirection.NEUTRAL,
                        "daily": MarketDirection.NEUTRAL, "sixty_min": MarketDirection.NEUTRAL},
        daily_cci=[50.0, 60.0],
        daily_signal=[60.0, 55.0],
        current_volume=1600,   # > 1000 * 1.5
        volume_ma20=1000.0,
        ma5=100.0,
        ma20=100.0,
        intraday_type=IntradaySignalType.NONE,
        has_45deg_decline=False,
    )
    assert "volume_surge" in score.breakdown
    assert score.breakdown["volume_surge"] == 1


def test_compute_alignment_bonus():
    """정배열(ma5 > ma20) 시 +1점."""
    score = compute_reliability_score(
        mtf_directions={"monthly": MarketDirection.NEUTRAL, "weekly": MarketDirection.NEUTRAL,
                        "daily": MarketDirection.NEUTRAL, "sixty_min": MarketDirection.NEUTRAL},
        daily_cci=[50.0, 60.0],
        daily_signal=[60.0, 55.0],
        current_volume=500,
        volume_ma20=1000.0,
        ma5=110.0,   # > ma20
        ma20=100.0,
        intraday_type=IntradaySignalType.NONE,
        has_45deg_decline=False,
    )
    assert "alignment" in score.breakdown
    assert score.breakdown["alignment"] == 1


def test_compute_intraday_type3_bonus():
    """장중 ③번 유형 시 +1점."""
    score = compute_reliability_score(
        mtf_directions={"monthly": MarketDirection.NEUTRAL, "weekly": MarketDirection.NEUTRAL,
                        "daily": MarketDirection.NEUTRAL, "sixty_min": MarketDirection.NEUTRAL},
        daily_cci=[50.0, 60.0],
        daily_signal=[60.0, 55.0],
        current_volume=500,
        volume_ma20=1000.0,
        ma5=100.0,
        ma20=100.0,
        intraday_type=IntradaySignalType.TYPE_3,
        has_45deg_decline=False,
    )
    assert "intraday_positive" in score.breakdown
    assert score.breakdown["intraday_positive"] == 1


def test_score_boundary_3_to_4():
    """경계값: 3점 → 관망, 4점 → 소극매수."""
    s3 = ReliabilityScore.from_breakdown({"monthly_gc": 1, "weekly_gc": 1, "alignment": 1})
    assert s3.score == 3
    assert s3.action == "관망"

    s4 = ReliabilityScore.from_breakdown({"monthly_gc": 1, "weekly_gc": 1, "daily_gc": 2})
    assert s4.score == 4
    assert s4.action == "소극매수"


def test_score_boundary_6_to_7():
    """경계값: 6점 → 소극매수, 7점 → 적극매수."""
    s6 = ReliabilityScore.from_breakdown(
        {"monthly_gc": 1, "weekly_gc": 1, "daily_gc": 2, "sixty_min_gc": 1, "volume_surge": 1}
    )
    assert s6.score == 6
    assert s6.action == "소극매수"

    s7 = ReliabilityScore.from_breakdown(
        {"monthly_gc": 1, "weekly_gc": 1, "daily_gc": 2, "sixty_min_gc": 1, "volume_surge": 1, "alignment": 1}
    )
    assert s7.score == 7
    assert s7.action == "적극매수"

    s8 = ReliabilityScore.from_breakdown(
        {"monthly_gc": 1, "weekly_gc": 1, "daily_gc": 2, "sixty_min_gc": 1, "volume_surge": 1, "intraday_positive": 1, "alignment": 1}
    )
    assert s8.score == 8
    assert s8.action == "적극매수"
