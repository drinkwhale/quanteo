"""CCI+BBC 통합 전략 플러그인 테스트.

4단계 의사결정 전체 시나리오, 스코어링 합산, 분할매수 수량, score < 0 → position_size = 0.0.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext
from core.strategy.multi_timeframe import MultiTimeframeData, TimeframeState
from core.strategy.plugins.bbc_buy import check_principle_2
from core.strategy.plugins.cci_bbc_strategy import (
    CciBbcStrategy,
    ReliabilityScore,
    calculate_position_size,
    compute_reliability_score,
)
from core.strategy.plugins.intraday_signal import IntradaySignalType
from core.strategy.timeframe_judge import MarketDirection

_KST = timezone(timedelta(hours=9))


def _make_candle(
    open_p: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: int = 1000,
    symbol: str = "TEST",
) -> Candle:
    return Candle(
        symbol=symbol,
        open=open_p,
        high=high,
        low=low,
        close=close,
        volume=volume,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        market="domestic",
    )


def _make_candles(count: int = 25, base_volume: int = 1000) -> list[Candle]:
    return [_make_candle(volume=base_volume) for _ in range(count)]


def _make_timeframe_state(
    candles: list[Candle] | None = None,
    cci: list[float] | None = None,
    cci_signal: list[float] | None = None,
    ma5: list[float] | None = None,
    ma20: list[float] | None = None,
    volume_ma20: list[float] | None = None,
) -> TimeframeState:
    c = candles or _make_candles()
    return TimeframeState(
        candles=c,
        cci=cci or [0.0],
        cci_signal=cci_signal or [0.0],
        ma5=ma5 or [100.0],
        ma20=ma20 or [95.0],
        volume_ma20=volume_ma20 or [1000.0],
        last_updated=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _make_mtf(
    monthly_cci: float = 100.0,
    weekly_cci: float = 100.0,
    daily_ma5: float = 100.0,
    daily_ma20: float = 95.0,
) -> MultiTimeframeData:
    return MultiTimeframeData(
        symbol="TEST",
        daily=_make_timeframe_state(ma5=[daily_ma5], ma20=[daily_ma20], volume_ma20=[1000.0]),
        weekly=_make_timeframe_state(cci=[weekly_cci]),
        monthly=_make_timeframe_state(cci=[monthly_cci]),
        sixty_min=_make_timeframe_state(),
    )


def _make_tick(
    price: float = 102.0,
    volume: int = 1500,
    symbol: str = "TEST",
    hour: int = 10,
    minute: int = 0,
) -> Tick:
    ts = datetime(2026, 1, 2, hour, minute, 0, tzinfo=_KST)
    return Tick(symbol=symbol, price=price, volume=volume, timestamp=ts, market="domestic")


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
    assert calculate_position_size(7) == pytest.approx(0.30)
    assert calculate_position_size(8) == pytest.approx(0.30)


def test_position_size_conservative():
    """소극매수(4~6점) → 10%."""
    assert calculate_position_size(4) == pytest.approx(0.10)
    assert calculate_position_size(6) == pytest.approx(0.10)


def test_position_size_wait():
    """관망(0~3점) → 0%."""
    assert calculate_position_size(3) == 0.0
    assert calculate_position_size(0) == 0.0


def test_position_size_negative_score():
    """음수 스코어 → 0.0 (음수에서 양수 비율 반환 방지)."""
    assert calculate_position_size(-1) == 0.0
    assert calculate_position_size(-5) == 0.0


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


# ============================================================================
# [H3] on_tick() 통합 테스트
# ============================================================================


def test_on_tick_returns_none_for_different_symbol():
    """다른 종목 틱 → None."""
    strategy = CciBbcStrategy(symbol="TEST", mtf_data=_make_mtf(), qty_per_unit=1)
    strategy.warmup(_make_candles())
    tick = _make_tick(symbol="OTHER")
    ctx = MarketContext(symbol="TEST", recent_candles=tuple(_make_candles()))
    assert strategy.on_tick(tick, ctx) is None


def test_on_tick_returns_none_when_mtf_data_missing():
    """mtf_data=None → 시그널 없음."""
    strategy = CciBbcStrategy(symbol="TEST", mtf_data=None, qty_per_unit=1)
    strategy.warmup(_make_candles())
    tick = _make_tick()
    ctx = MarketContext(symbol="TEST", recent_candles=tuple(_make_candles()))
    assert strategy.on_tick(tick, ctx) is None


def test_on_tick_returns_none_when_daily_candles_empty():
    """일봉 캔들 비어 있으면 → None."""
    mtf = _make_mtf()
    mtf.daily.candles.clear()
    strategy = CciBbcStrategy(symbol="TEST", mtf_data=mtf, qty_per_unit=1)
    strategy.warmup([])
    tick = _make_tick()
    ctx = MarketContext(symbol="TEST", recent_candles=())
    assert strategy.on_tick(tick, ctx) is None


def test_on_tick_monthly_bearish_blocks_trading():
    """월봉 BEARISH(CCI < 0) → 거래 금지 → None."""
    mtf = _make_mtf(monthly_cci=-100.0)
    strategy = CciBbcStrategy(symbol="TEST", mtf_data=mtf, qty_per_unit=1)
    strategy.warmup(_make_candles())
    tick = _make_tick()
    ctx = MarketContext(symbol="TEST", recent_candles=tuple(_make_candles()))
    assert strategy.on_tick(tick, ctx) is None


def test_on_tick_returns_none_when_recent_candles_empty():
    """recent_candles 비어 있으면 → None (ctx 조건 미충족)."""
    mtf = _make_mtf()
    strategy = CciBbcStrategy(symbol="TEST", mtf_data=mtf, qty_per_unit=1)
    strategy.warmup(_make_candles())
    tick = _make_tick()
    ctx = MarketContext(symbol="TEST", recent_candles=())
    assert strategy.on_tick(tick, ctx) is None


# ============================================================================
# [M4] check_principle_2 경계 테스트
# ============================================================================


def test_principle_2_price_exactly_at_ma20():
    """경계값: price == ma20 → 눌림목 허용 (ma20 <= price <= ma5)."""
    from datetime import time
    candles = _make_candles(count=25, base_volume=300)
    # 양봉: open < close
    candles[-1] = _make_candle(open_p=98.0, close=100.0, volume=2000)

    result = check_principle_2(
        current_price=100.0,
        ma5=105.0,
        ma20=100.0,  # price == ma20: 경계 포함 여부 확인
        candles=candles,
        volume_ma20=1000.0,
        current_volume=2000,
        current_time=time(9, 30),
    )
    assert result is not None
    assert result.principle == 2


def test_principle_2_price_above_ma5_excluded():
    """price > ma5 → 제2원칙 미해당."""
    from datetime import time
    candles = _make_candles(count=25)
    result = check_principle_2(
        current_price=110.0,
        ma5=105.0,
        ma20=95.0,
        candles=candles,
        volume_ma20=1000.0,
        current_volume=2000,
        current_time=time(10, 0),
    )
    assert result is None


def test_principle_2_fewer_than_20_candles_fallback():
    """캔들 < 20봉 → 경고 후 가용 캔들로 계산, 조건 충족 시 시그널 반환."""
    from datetime import time
    candles = _make_candles(count=8, base_volume=300)
    candles[-1] = _make_candle(open_p=98.0, close=102.0, volume=2000)

    result = check_principle_2(
        current_price=102.0,
        ma5=105.0,
        ma20=95.0,
        candles=candles,
        volume_ma20=1000.0,
        current_volume=2000,
        current_time=time(9, 30),
    )
    # 8봉밖에 없어도 조건 충족 시 시그널 반환 (신뢰도 낮음 경고만)
    assert result is not None
    assert result.principle == 2
