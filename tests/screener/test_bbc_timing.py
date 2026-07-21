"""screener.pipeline.bbc_timing 단위 테스트.

evaluate_buy() 자체의 3원칙 판정 로직은 tests/strategy/plugins/test_bbc_buy.py에서
이미 충분히 검증한다 — 여기서는 pykrx 일봉 히스토리 → Candle 변환과, 일봉 기준
평가(오후 고정, ma5/ma20/volume_ma20 계산)로 잘 이어지는지만 확인한다.
"""

from __future__ import annotations

import pandas as pd

from screener.pipeline.bbc_timing import assess_buy_principle, candles_from_history


def _history_df(closes: list[float], volumes: list[int]) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "시가": closes,
            "고가": [c * 1.01 for c in closes],
            "저가": [c * 0.99 for c in closes],
            "종가": closes,
            "거래량": volumes,
        },
        index=pd.date_range("2026-06-01", periods=n, freq="B"),
    )


class TestCandlesFromHistory:
    def test_converts_columns_and_symbol(self) -> None:
        df = _history_df([100.0, 101.0], [1000, 1100])

        candles = candles_from_history(df, "005930")

        assert len(candles) == 2
        assert candles[0].symbol == "005930"
        assert candles[0].market == "domestic"
        assert candles[0].close == 100.0
        assert candles[0].volume == 1000
        assert candles[-1].close == 101.0

    def test_empty_df_returns_empty_list(self) -> None:
        assert candles_from_history(pd.DataFrame(), "005930") == []


class TestAssessBuyPrinciple:
    def test_too_few_candles_returns_none(self) -> None:
        df = _history_df([100.0] * 10, [1000] * 10)
        candles = candles_from_history(df, "005930")

        assert assess_buy_principle(candles) is None

    def test_flat_price_and_volume_returns_none(self) -> None:
        df = _history_df([100.0] * 25, [1000] * 25)
        candles = candles_from_history(df, "005930")

        assert assess_buy_principle(candles) is None

    def test_price_above_ma5_with_volume_surge_triggers_principle_1(self) -> None:
        # 24개 평탄한 캔들 + 마지막에 종가·거래량 급등 → 오후 분기 제1원칙 충족
        # (price > ma5, current_volume > volume_ma20 * 1.5).
        closes = [100.0] * 24 + [110.0]
        volumes = [1000] * 24 + [5000]
        df = _history_df(closes, volumes)
        candles = candles_from_history(df, "005930")

        signal = assess_buy_principle(candles)

        assert signal is not None
        assert signal.principle == 1
