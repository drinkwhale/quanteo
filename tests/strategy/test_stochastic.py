"""Stochastic %K/%D 지표 계산 모듈 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.marketdata.models import Candle
from core.strategy.indicators.stochastic import (
    calculate_stochastic_d,
    calculate_stochastic_k,
    detect_stochastic_bottom_reversal,
    detect_stochastic_top_reversal,
)


def _make_candle(close: float, high: float | None = None, low: float | None = None) -> Candle:
    return Candle(
        symbol="TEST",
        open=close,
        high=high if high is not None else close + 1.0,
        low=low if low is not None else close - 1.0,
        close=close,
        volume=1000,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        market="domestic",
    )


class TestCalculateStochasticK:
    def test_데이터_부족시_빈_리스트(self) -> None:
        candles = [_make_candle(100.0) for _ in range(5)]
        assert calculate_stochastic_k(candles, k_period=14) == []

    def test_종가가_최고가일때_K는_100(self) -> None:
        candles = [_make_candle(95.0, high=101.0, low=90.0) for _ in range(13)]
        candles.append(_make_candle(101.0, high=101.0, low=90.0))
        k = calculate_stochastic_k(candles, k_period=14)
        assert k[-1] == pytest.approx(100.0)

    def test_고가_저가_동일하면_50_대체(self) -> None:
        candles = [_make_candle(100.0, high=100.0, low=100.0) for _ in range(14)]
        k = calculate_stochastic_k(candles, k_period=14)
        assert k[-1] == 50.0


class TestCalculateStochasticD:
    def test_K값의_이동평균(self) -> None:
        k_values = [10.0, 20.0, 30.0, 40.0]
        d_values = calculate_stochastic_d(k_values, d_period=3)
        assert d_values[-1] == pytest.approx((20.0 + 30.0 + 40.0) / 3)


class TestDetectStochasticBottomReversal:
    def test_과매도_구간에서_반등시_True(self) -> None:
        d_values = [15.0, 10.0, 18.0]
        assert detect_stochastic_bottom_reversal(d_values, oversold=20.0) is True

    def test_과매도_아니면_False(self) -> None:
        d_values = [50.0, 40.0, 60.0]
        assert detect_stochastic_bottom_reversal(d_values, oversold=20.0) is False

    def test_반등하지_않으면_False(self) -> None:
        d_values = [15.0, 10.0, 5.0]
        assert detect_stochastic_bottom_reversal(d_values, oversold=20.0) is False


class TestDetectStochasticTopReversal:
    def test_과매수_구간에서_반락시_True(self) -> None:
        d_values = [85.0, 90.0, 82.0]
        assert detect_stochastic_top_reversal(d_values, overbought=80.0) is True

    def test_데이터_부족시_False(self) -> None:
        assert detect_stochastic_top_reversal([90.0], overbought=80.0) is False
