"""레버리지/인버스 진입 조건 판정 모듈 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.marketdata.models import Candle
from core.strategy.plugins.leverage_inverse_conditions import (
    EntryEvaluation,
    LeverageInverseParams,
    assess_low_point,
    evaluate_inverse_entry,
    evaluate_leverage_entry,
)


def _candle(close: float, high: float | None = None, low: float | None = None) -> Candle:
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


class TestLeverageInverseParams:
    def test_기본값은_spec_1장_기준값과_일치(self) -> None:
        params = LeverageInverseParams()
        assert params.dema_period == 60
        assert params.cci_period == 20
        assert params.cci_signal_period == 10
        assert params.stochastic_overbought == 80.0
        assert params.stochastic_oversold == 20.0
        assert params.cci_overbought_warning == 150.0
        assert params.cci_oversold_warning == -150.0

    def test_partial_exit_ratio_범위_밖이면_예외(self) -> None:
        with pytest.raises(ValueError):
            LeverageInverseParams(partial_exit_ratio=1.5)

    def test_dema_period_3미만이면_예외(self) -> None:
        with pytest.raises(ValueError):
            LeverageInverseParams(dema_period=2)


class TestEntryEvaluation:
    def test_3개_모두_충족_필터_통과시_all_met_True(self) -> None:
        ev = EntryEvaluation(True, True, True, True)
        assert ev.all_met is True
        assert ev.core_count == 3

    def test_필터_미통과시_all_met_False(self) -> None:
        ev = EntryEvaluation(True, True, True, False)
        assert ev.all_met is False

    def test_2개만_충족시_core_count_2(self) -> None:
        ev = EntryEvaluation(True, True, False, True)
        assert ev.core_count == 2
        assert ev.all_met is False


class TestEvaluateLeverageEntry:
    def test_3조건_모두_충족(self) -> None:
        dema = [100.0, 101.0, 103.0]  # 기울기 강화 (우상향 전환)
        cci = [-5.0, 5.0]  # 0선 상향 돌파
        cci_signal = [0.0, 0.0]
        candles = [
            _candle(90.0),
            _candle(95.0),
            _candle(104.0),
        ]  # 마지막 봉 종가가 직전 고점(95)·DEMA(103) 모두 상회
        stoch_d = [50.0]  # 80 미만 → 필터 통과

        result = evaluate_leverage_entry(
            dema, cci, cci_signal, candles, stoch_d, LeverageInverseParams()
        )
        assert result.dema_slope_ok is True
        assert result.cci_cross_ok is True
        assert result.price_break_ok is True
        assert result.stoch_filter_ok is True
        assert result.all_met is True

    def test_stochastic_과열시_필터_거부(self) -> None:
        dema = [100.0, 101.0, 103.0]
        cci = [-5.0, 5.0]
        cci_signal = [0.0, 0.0]
        candles = [_candle(90.0), _candle(95.0), _candle(104.0)]
        stoch_d = [85.0]  # 80 이상 → 필터 거부

        result = evaluate_leverage_entry(
            dema, cci, cci_signal, candles, stoch_d, LeverageInverseParams()
        )
        assert result.stoch_filter_ok is False
        assert result.all_met is False

    def test_고점_갱신_실패시_가격조건_False(self) -> None:
        dema = [100.0, 101.0, 103.0]
        cci = [-5.0, 5.0]
        cci_signal = [0.0, 0.0]
        candles = [_candle(90.0), _candle(95.0), _candle(92.0)]  # 마지막 종가가 직전 고점(95) 미달
        stoch_d = [50.0]

        result = evaluate_leverage_entry(
            dema, cci, cci_signal, candles, stoch_d, LeverageInverseParams()
        )
        assert result.price_break_ok is False


class TestEvaluateInverseEntry:
    def test_3조건_모두_충족(self) -> None:
        dema = [100.0, 99.0, 97.0]  # 기울기 강화 (하향 전환)
        cci = [5.0, -5.0]  # 0선 하향 이탈
        cci_signal = [0.0, 0.0]
        candles = [
            _candle(110.0),
            _candle(105.0),
            _candle(96.0),
        ]  # 신저가(96 < 105)·DEMA(97) 모두 하회
        stoch_d = [50.0]  # 20 초과 → 필터 통과

        result = evaluate_inverse_entry(
            dema, cci, cci_signal, candles, stoch_d, LeverageInverseParams()
        )
        assert result.all_met is True

    def test_stochastic_과매도시_필터_거부(self) -> None:
        dema = [100.0, 99.0, 97.0]
        cci = [5.0, -5.0]
        cci_signal = [0.0, 0.0]
        candles = [_candle(110.0), _candle(105.0), _candle(96.0)]
        stoch_d = [15.0]  # 20 이하 → 필터 거부

        result = evaluate_inverse_entry(
            dema, cci, cci_signal, candles, stoch_d, LeverageInverseParams()
        )
        assert result.stoch_filter_ok is False
        assert result.all_met is False


class TestAssessLowPoint:
    def test_신호_2개_이상이면_strong(self) -> None:
        # capitulation volume + stochastic reversal 조합
        candles = [_candle(100.0, high=101.0, low=99.0) for _ in range(19)]
        candles.append(_candle(98.0, high=100.0, low=85.0))
        volume_ma = [1000.0] * 20
        candles[-1] = Candle(
            symbol="TEST",
            open=99.0,
            high=100.0,
            low=85.0,
            close=98.0,
            volume=5000,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            market="domestic",
        )
        stoch_d = [15.0, 10.0, 25.0]
        cci = [0.0] * 20

        result = assess_low_point(candles, cci, stoch_d, volume_ma)
        assert result.capitulation_volume is True
        assert result.stochastic_reversal is True
        assert result.confidence == "strong"

    def test_신호_없으면_none(self) -> None:
        candles = [_candle(100.0, high=101.0, low=99.0) for _ in range(20)]
        volume_ma = [1000.0] * 20
        stoch_d = [50.0, 55.0, 60.0]
        cci = [0.0] * 20

        result = assess_low_point(candles, cci, stoch_d, volume_ma)
        assert result.confidence == "none"
