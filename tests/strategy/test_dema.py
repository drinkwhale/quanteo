"""DEMA 지표 계산 모듈 테스트."""

from __future__ import annotations

from core.strategy.indicators.dema import (
    calculate_dema,
    calculate_ema,
    detect_dema_slope_down,
    detect_dema_slope_up,
)


class TestCalculateEma:
    def test_반환값_길이는_입력_길이_마이너스_기간_플러스1(self) -> None:
        values = [float(i) for i in range(1, 21)]
        ema = calculate_ema(values, period=10)
        assert len(ema) == len(values) - 10 + 1

    def test_데이터_부족시_빈_리스트(self) -> None:
        assert calculate_ema([1.0, 2.0], period=5) == []

    def test_고정값_시리즈는_EMA도_고정값(self) -> None:
        values = [100.0] * 20
        ema = calculate_ema(values, period=5)
        assert all(abs(v - 100.0) < 1e-9 for v in ema)


class TestCalculateDema:
    def test_데이터_부족시_빈_리스트(self) -> None:
        values = [float(i) for i in range(1, 10)]
        assert calculate_dema(values, period=60) == []

    def test_충분한_데이터에서_값_생성(self) -> None:
        values = [100.0 + i * 0.3 for i in range(200)]
        dema = calculate_dema(values, period=60)
        assert len(dema) > 0

    def test_상승_추세에서_DEMA도_상승(self) -> None:
        values = [100.0 + i * 0.5 for i in range(200)]
        dema = calculate_dema(values, period=60)
        assert dema[-1] > dema[0]


class TestDetectDemaSlopeUp:
    def test_기울기_강화시_True(self) -> None:
        # 상승폭이 점점 커지는 패턴: 이전 구간(1.0) < 최근 구간(2.0)
        dema = [100.0, 101.0, 103.0]
        assert detect_dema_slope_up(dema) is True

    def test_기울기_둔화시_False(self) -> None:
        dema = [100.0, 102.0, 103.0]
        assert detect_dema_slope_up(dema) is False

    def test_데이터_3개_미만이면_False(self) -> None:
        assert detect_dema_slope_up([100.0, 101.0]) is False


class TestDetectDemaSlopeDown:
    def test_하락폭_확대시_True(self) -> None:
        dema = [100.0, 99.0, 97.0]
        assert detect_dema_slope_down(dema) is True

    def test_하락폭_축소시_False(self) -> None:
        dema = [100.0, 97.0, 96.0]
        assert detect_dema_slope_down(dema) is False

    def test_데이터_3개_미만이면_False(self) -> None:
        assert detect_dema_slope_down([100.0, 99.0]) is False
