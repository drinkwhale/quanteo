"""이동평균선 & 거래량 지표 모듈 테스트.

SMA 계산, 캔들 분류, 가격 포지션, 장대 캔들 판별 등의 경계 케이스 검증.
"""

from __future__ import annotations

from datetime import datetime

from core.marketdata.models import Candle
from core.strategy.indicators.ma import (
    CandleClass,
    PricePosition,
    calculate_sma,
    classify_candle,
    is_alignment_bullish,
    is_large_candle,
    price_position,
)


class TestCalculateSma:
    """SMA 계산 테스트."""

    def test_sma_basic(self) -> None:
        """기본 SMA 계산."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = calculate_sma(values, 3)
        # (1+2+3)/3=2, (2+3+4)/3=3, (3+4+5)/3=4
        assert result == [2.0, 3.0, 4.0]
        assert len(result) == len(values) - (3 - 1)

    def test_sma_period_1(self) -> None:
        """기간 1 — 원본 값 반환."""
        values = [10.0, 20.0, 30.0]
        result = calculate_sma(values, 1)
        assert result == values

    def test_sma_period_equals_length(self) -> None:
        """기간 == 리스트 길이."""
        values = [1.0, 2.0, 3.0]
        result = calculate_sma(values, 3)
        assert result == [2.0]  # 평균만 1개

    def test_sma_insufficient_data(self) -> None:
        """데이터 부족 시 빈 리스트 반환."""
        values = [1.0, 2.0]
        result = calculate_sma(values, 5)
        assert result == []

    def test_sma_period_5(self) -> None:
        """5일선 계산."""
        values = [100.0, 102.0, 101.0, 103.0, 104.0, 105.0]
        result = calculate_sma(values, 5)
        expected_first = sum([100, 102, 101, 103, 104]) / 5
        assert len(result) == 2
        assert result[0] == expected_first

    def test_sma_period_20(self) -> None:
        """20일선 계산."""
        values = list(range(1, 31))  # 1~30
        result = calculate_sma(values, 20)
        # (1+2+...+20)/20 = 210/20 = 10.5
        assert result[0] == 10.5
        # (2+3+...+21)/20 = 230/20 = 11.5
        assert result[1] == 11.5


class TestClassifyCandle:
    """캔들 분류 테스트."""

    def test_bullish_candle(self) -> None:
        """양봉 분류."""
        # close > open * 1.001
        result = classify_candle(100.0, 100.2, threshold=0.001)
        assert result == CandleClass.BULLISH

    def test_bearish_candle(self) -> None:
        """음봉 분류."""
        # close < open * 0.999
        result = classify_candle(100.0, 99.8, threshold=0.001)
        assert result == CandleClass.BEARISH

    def test_doji_candle(self) -> None:
        """십자형 분류."""
        # close 근처 open
        result = classify_candle(100.0, 100.05, threshold=0.001)
        assert result == CandleClass.DOJI

    def test_threshold_boundary_bullish(self) -> None:
        """양봉 경계값 (정확히 임계값)."""
        # close == open * (1 + threshold) → 아직 DOJI (부등호 >, >=아님)
        result = classify_candle(100.0, 100.1, threshold=0.001)
        # 100.1 == 100 * 1.001 → close > upper_bound는 False
        # DOJI
        assert result == CandleClass.DOJI

    def test_threshold_boundary_bearish(self) -> None:
        """음봉 경계값 (정확히 임계값)."""
        # close == open * (1 - threshold) → 아직 DOJI
        result = classify_candle(100.0, 99.9, threshold=0.001)
        # 99.9 == 100 * 0.999 → close < lower_bound는 False
        # DOJI
        assert result == CandleClass.DOJI

    def test_threshold_just_below_lower(self) -> None:
        """음봉 경계값 바로 아래."""
        # close < open * (1 - threshold)
        result = classify_candle(100.0, 99.89, threshold=0.001)
        assert result == CandleClass.BEARISH

    def test_threshold_just_above_upper(self) -> None:
        """양봉 경계값 바로 위."""
        # close > open * (1 + threshold)
        result = classify_candle(100.0, 100.11, threshold=0.001)
        assert result == CandleClass.BULLISH

    def test_zero_open(self) -> None:
        """시가 0 처리 (edge case)."""
        # open=0 → upper bound = 0.0 * 1.001 = 0.0
        # close=0.1 > 0.0 → BULLISH
        result = classify_candle(0.0, 0.1, threshold=0.001)
        assert result == CandleClass.BULLISH

    def test_large_threshold(self) -> None:
        """큰 임계값 (5%)."""
        result = classify_candle(100.0, 110.0, threshold=0.05)
        # 110 > 100 * 1.05 (105) → BULLISH
        assert result == CandleClass.BULLISH

    def test_zero_threshold(self) -> None:
        """임계값 0."""
        # close > open이면 BULLISH
        result = classify_candle(100.0, 100.01, threshold=0.0)
        assert result == CandleClass.BULLISH

        result = classify_candle(100.0, 99.99, threshold=0.0)
        assert result == CandleClass.BEARISH


class TestIsLargeCandle:
    """장대 캔들 판별 테스트."""

    def create_candle(self, open_: float, high: float, low: float, close: float) -> Candle:
        """테스트용 Candle 생성."""
        return Candle(
            symbol="TEST",
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=1000,
            timestamp=datetime(2024, 1, 1, 9, 0, 0),
            market="domestic",
        )

    def test_large_candle(self) -> None:
        """장대 캔들 판정."""
        # open=100, close=105, high=110, low=95
        # body = |105-100| = 5, range = 110-95 = 15
        # ratio = 5/15 = 0.333... < 0.6 → False
        # 이를 위해 ratio >= 0.6인 경우 필요
        # open=100, close=110, high=112, low=95
        # body = |110-100| = 10, range = 112-95 = 17
        # ratio = 10/17 ≈ 0.588 < 0.6 → False
        # open=100, close=110, high=111, low=95
        # body = |110-100| = 10, range = 111-95 = 16
        # ratio = 10/16 = 0.625 >= 0.6 → True
        candle = self.create_candle(100.0, 111.0, 95.0, 110.0)
        assert is_large_candle(candle, body_ratio=0.6) is True

    def test_small_candle(self) -> None:
        """소형 캔들."""
        # open=100, close=101, high=102, low=99
        # body = 1, range = 3, ratio = 1/3 ≈ 0.333 < 0.6
        candle = self.create_candle(100.0, 102.0, 99.0, 101.0)
        assert is_large_candle(candle, body_ratio=0.6) is False

    def test_zero_range(self) -> None:
        """high == low (제로 분모)."""
        # high=low=100, open=100, close=100
        candle = self.create_candle(100.0, 100.0, 100.0, 100.0)
        assert is_large_candle(candle, body_ratio=0.6) is False

    def test_near_zero_range(self) -> None:
        """거의 0에 가까운 range."""
        # high=100.0000001, low=100.0, body=0.00000001
        # ratio ≈ 0 < 0.6
        candle = self.create_candle(100.0, 100.0000001, 100.0, 100.00000001)
        assert is_large_candle(candle, body_ratio=0.6) is False

    def test_boundary_exactly_ratio(self) -> None:
        """정확히 기준 비율."""
        # body = 6, range = 10, ratio = 0.6
        # open=100, close=106, high=105, low=95
        # range = 105-95 = 10
        candle = self.create_candle(100.0, 105.0, 95.0, 106.0)
        assert is_large_candle(candle, body_ratio=0.6) is True

    def test_custom_body_ratio(self) -> None:
        """커스텀 body_ratio."""
        # open=100, close=110, high=111, low=95
        # body=10, range=16, ratio=0.625
        candle = self.create_candle(100.0, 111.0, 95.0, 110.0)
        # ratio=0.625 > 0.5 → True
        assert is_large_candle(candle, body_ratio=0.5) is True
        # ratio=0.625 < 0.7 → False
        assert is_large_candle(candle, body_ratio=0.7) is False


class TestIsAlignmentBullish:
    """정배열 판단 테스트."""

    def test_bullish_alignment(self) -> None:
        """정배열 (5일선 > 20일선)."""
        assert is_alignment_bullish(100.0, 95.0) is True

    def test_bearish_alignment(self) -> None:
        """약세 배열 (5일선 <= 20일선)."""
        assert is_alignment_bullish(95.0, 100.0) is False

    def test_equal_alignment(self) -> None:
        """같음."""
        assert is_alignment_bullish(100.0, 100.0) is False


class TestPricePosition:
    """가격 포지션 분류 테스트."""

    def test_above_ma5(self) -> None:
        """5일선 위."""
        # ma5=100, ma20=80, price=110
        result = price_position(110.0, 100.0, 80.0)
        assert result == PricePosition.ABOVE

    def test_between_ma5_ma20(self) -> None:
        """5일선과 20일선 사이."""
        # ma5=100, ma20=80, price=90
        result = price_position(90.0, 100.0, 80.0)
        assert result == PricePosition.BETWEEN

    def test_below_ma20(self) -> None:
        """20일선 아래."""
        # ma5=100, ma20=80, price=70
        result = price_position(70.0, 100.0, 80.0)
        assert result == PricePosition.BELOW

    def test_exactly_ma5(self) -> None:
        """정확히 ma5 (경계값)."""
        # price == ma5 → price > ma5는 False → BETWEEN
        result = price_position(100.0, 100.0, 80.0)
        assert result == PricePosition.BETWEEN

    def test_exactly_ma20(self) -> None:
        """정확히 ma20 (경계값)."""
        # price == ma20 → price >= ma20 → BETWEEN
        result = price_position(80.0, 100.0, 80.0)
        assert result == PricePosition.BETWEEN

    def test_ma5_equals_ma20(self) -> None:
        """ma5 == ma20인 경우."""
        # ma5=100, ma20=100, price=105
        result = price_position(105.0, 100.0, 100.0)
        assert result == PricePosition.ABOVE

        # price=100 (== ma5 == ma20)
        result = price_position(100.0, 100.0, 100.0)
        assert result == PricePosition.BETWEEN

        # price=95 (< ma5 == ma20)
        result = price_position(95.0, 100.0, 100.0)
        assert result == PricePosition.BELOW

    def test_negative_prices(self) -> None:
        """음수 가격 (edge case)."""
        # 실제로는 불가능하지만 로직 검증
        # price=-10, ma5=0, ma20=-20
        # price > ma5? -10 > 0? False
        # price >= ma20? -10 >= -20? True → BETWEEN
        result = price_position(-10.0, 0.0, -20.0)
        assert result == PricePosition.BETWEEN

    def test_zero_prices(self) -> None:
        """0 가격."""
        result = price_position(0.0, 0.0, 0.0)
        assert result == PricePosition.BETWEEN


class TestEnumValues:
    """Enum 값 검증."""

    def test_candle_class_values(self) -> None:
        """CandleClass 열거형 값."""
        assert CandleClass.BULLISH.value == "bullish"
        assert CandleClass.BEARISH.value == "bearish"
        assert CandleClass.DOJI.value == "doji"

    def test_price_position_values(self) -> None:
        """PricePosition 열거형 값."""
        assert PricePosition.ABOVE.value == "above"
        assert PricePosition.BETWEEN.value == "between"
        assert PricePosition.BELOW.value == "below"

    def test_candle_class_is_str_enum(self) -> None:
        """CandleClass는 StrEnum."""
        # StrEnum이므로 문자열 비교 가능
        assert CandleClass.BULLISH == "bullish"
        assert CandleClass.BEARISH == "bearish"
        assert CandleClass.DOJI == "doji"

    def test_price_position_is_str_enum(self) -> None:
        """PricePosition은 StrEnum."""
        assert PricePosition.ABOVE == "above"
        assert PricePosition.BETWEEN == "between"
        assert PricePosition.BELOW == "below"
