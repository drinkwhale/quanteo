"""스윙 고점/저점 + 다이버전스 모듈 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

from core.marketdata.models import Candle
from core.strategy.indicators.swing import (
    detect_bullish_divergence,
    detect_capitulation_volume,
    detect_higher_low,
    find_pivot_lows,
    recent_swing_high,
    recent_swing_low,
)


def _candle(
    high: float,
    low: float,
    close: float | None = None,
    open_: float | None = None,
    volume: int = 1000,
) -> Candle:
    c = close if close is not None else (high + low) / 2
    o = open_ if open_ is not None else c
    return Candle(
        symbol="TEST",
        open=o,
        high=high,
        low=low,
        close=c,
        volume=volume,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        market="domestic",
    )


class TestRecentSwingHigh:
    def test_현재_봉_제외한_최고가_반환(self) -> None:
        candles = [_candle(100, 90), _candle(110, 95), _candle(105, 92)]
        # 마지막 봉(105) 제외 → 직전 구간 최고가는 110
        assert recent_swing_high(candles, n=10) == 110

    def test_봉이_1개면_None(self) -> None:
        assert recent_swing_high([_candle(100, 90)], n=10) is None


class TestRecentSwingLow:
    def test_현재_봉_제외한_최저가_반환(self) -> None:
        candles = [_candle(100, 90), _candle(110, 85), _candle(105, 92)]
        assert recent_swing_low(candles, n=10) == 85

    def test_봉이_1개면_None(self) -> None:
        assert recent_swing_low([_candle(100, 90)], n=10) is None


class TestFindPivotLows:
    def test_명확한_피봇_저점_탐지(self) -> None:
        lows = [100, 90, 80, 90, 100, 90, 70, 90, 100]
        candles = [_candle(low + 10, low) for low in lows]
        pivots = find_pivot_lows(candles, left=2, right=2)
        pivot_indices = [idx for idx, _ in pivots]
        # 인덱스 2(low=80)와 인덱스 6(low=70)이 피봇 저점이어야 함
        assert 2 in pivot_indices
        assert 6 in pivot_indices


class TestDetectHigherLow:
    def test_higher_low_구조_감지(self) -> None:
        # 저점 시퀀스: 100 → 80(prev_prev) → 60(prev, 더 낮음) → 70(last, prev보다 높음)
        lows = [100, 90, 80, 90, 100, 90, 60, 90, 100, 90, 70, 90, 100]
        candles = [_candle(low + 10, low) for low in lows]
        assert detect_higher_low(candles, left=2, right=2) is True

    def test_피봇_부족시_False(self) -> None:
        candles = [_candle(100, 90) for _ in range(3)]
        assert detect_higher_low(candles) is False


class TestDetectBullishDivergence:
    def test_가격_신저가_오실레이터_저점_상승시_True(self) -> None:
        candles = [_candle(100, 95, close=97) for _ in range(11)]
        candles[0] = _candle(100, 90, close=92)  # t-10 저점
        candles[-1] = _candle(100, 85, close=87)  # t 신저가 (85 < 90)
        oscillator = [50.0] * 11
        oscillator[0] = -50.0  # t-10 오실레이터 낮음
        oscillator[-1] = -30.0  # t 오실레이터 더 높음 (다이버전스)
        assert detect_bullish_divergence(candles, oscillator, lookback=10) is True

    def test_데이터_부족시_False(self) -> None:
        candles = [_candle(100, 90) for _ in range(5)]
        oscillator = [1.0] * 5
        assert detect_bullish_divergence(candles, oscillator, lookback=10) is False


class TestDetectCapitulationVolume:
    def test_거래량_급증_및_아래꼬리_긴_캔들시_True(self) -> None:
        candles = [_candle(100, 95, close=98, volume=1000) for _ in range(19)]
        # 아래꼬리 긴 캔들: open/close는 위쪽, low는 훨씬 아래
        candles.append(_candle(100, 80, close=98, open_=97, volume=5000))
        volume_ma = [1000.0] * 20
        assert detect_capitulation_volume(candles, volume_ma, surge_multiplier=2.0) is True

    def test_거래량_급증_없으면_False(self) -> None:
        candles = [_candle(100, 95, close=98, volume=1000) for _ in range(20)]
        volume_ma = [1000.0] * 20
        assert detect_capitulation_volume(candles, volume_ma) is False
