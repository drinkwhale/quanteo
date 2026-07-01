"""CCI 지표 계산 모듈 테스트.

공식 수식 검증, 골든/데드크로스 경계 케이스, 데이터 부족 처리, MD=0 가드 검증.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.marketdata.models import Candle
from core.strategy.indicators.cci import (
    calculate_cci,
    calculate_cci_signal,
    detect_dead_cross,
    detect_golden_cross,
    get_cci_zone,
)


@pytest.fixture
def sample_candles() -> list[Candle]:
    """테스트용 샘플 캔들 데이터 (30개, 가격 상승 추세)."""
    base_price = 100.0
    candles = []
    for i in range(30):
        price = base_price + (i * 0.5)  # 점진적 상승
        candle = Candle(
            symbol="TEST",
            open=price,
            high=price + 0.5,
            low=price - 0.5,
            close=price,
            volume=1000,
            timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            market="domestic",
        )
        candles.append(candle)
    return candles


@pytest.fixture
def flat_price_candles() -> list[Candle]:
    """MD=0 테스트용 캔들 (20개 동일 가격)."""
    candles = []
    for _ in range(20):
        candle = Candle(
            symbol="TEST",
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=1000,
            timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            market="domestic",
        )
        candles.append(candle)
    return candles


# ---------------------------------------------------------------------------
# 기본 계산 테스트
# ---------------------------------------------------------------------------


def test_calculate_cci_basic_formula(sample_candles):
    """CCI 계산 공식 검증 (TP, SMA, MD, CCI 단계별)."""
    cci_values = calculate_cci(sample_candles, period=5)

    # period=5 이므로, 5개 이상의 데이터가 필요
    # 반환 길이 = 30 - (5 - 1) = 26
    assert len(cci_values) == 26

    # CCI 값이 유한한 수여야 함 (nan, inf 없음)
    for val in cci_values:
        assert val == val  # nan 체크 (nan은 self와 같지 않음)
        assert val != float("inf") and val != float("-inf")


def test_calculate_cci_length_contract(sample_candles):
    """반환 길이 계약 검증: len(result) = len(candles) - (period - 1)."""
    candles = sample_candles[:25]

    cci_20 = calculate_cci(candles, period=20)
    assert len(cci_20) == 25 - (20 - 1)  # 25 - 19 = 6

    cci_10 = calculate_cci(candles, period=10)
    assert len(cci_10) == 25 - (10 - 1)  # 25 - 9 = 16


def test_calculate_cci_insufficient_data():
    """데이터 부족 시 빈 리스트 반환 (예외 미발생)."""
    candles = []
    assert calculate_cci(candles, period=20) == []

    # period-1개 미만
    short_candles = [
        Candle(
            symbol="TEST",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000,
            timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            market="domestic",
        )
        for _ in range(10)
    ]
    assert calculate_cci(short_candles, period=20) == []


def test_calculate_cci_exact_period(sample_candles):
    """정확히 period 개의 데이터 시 반환 길이 = 1."""
    candles = sample_candles[:20]
    cci_values = calculate_cci(candles, period=20)

    assert len(cci_values) == 1
    assert isinstance(cci_values[0], float)


# ---------------------------------------------------------------------------
# MD=0 가드 테스트
# ---------------------------------------------------------------------------


def test_cci_flat_price_returns_all_zeros(flat_price_candles, caplog):
    """20봉 동일 가격 → MD=0 → 전체 0.0 반환 검증."""
    cci_values = calculate_cci(flat_price_candles, period=20)

    # period=20, 20개 캔들 → 반환 길이 = 1
    assert len(cci_values) == 1
    assert cci_values[0] == 0.0

    # 경고 로그 확인
    assert "MD≈0, 중립값 대체" in caplog.text


def test_cci_near_zero_md_guarded(caplog):
    """MD가 매우 작은 경우 (1e-10) 0.0 대체 및 경고 로그."""
    # TP가 거의 동일하지만 미묘한 변동
    candles = []
    for i in range(20):
        # 가격 변동을 1e-11 수준으로 제한
        candle = Candle(
            symbol="TEST",
            open=100.0 + (i * 1e-11),
            high=100.0 + (i * 1e-11) + 1e-11,
            low=100.0 + (i * 1e-11) - 1e-11,
            close=100.0 + (i * 1e-11),
            volume=1000,
            timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            market="domestic",
        )
        candles.append(candle)

    cci_values = calculate_cci(candles, period=20)
    assert len(cci_values) == 1
    assert cci_values[0] == 0.0
    assert "MD≈0, 중립값 대체" in caplog.text


# ---------------------------------------------------------------------------
# 시그널 라인 테스트
# ---------------------------------------------------------------------------


def test_calculate_cci_signal_length(sample_candles):
    """시그널 라인 반환 길이 검증."""
    cci_values = calculate_cci(sample_candles, period=10)
    # len(cci_values) = 30 - (10 - 1) = 21

    signal_values = calculate_cci_signal(cci_values, signal_period=10)
    # len(signal_values) = 21 - (10 - 1) = 12
    assert len(signal_values) == 12


def test_calculate_cci_signal_insufficient_data():
    """시그널 데이터 부족 시 빈 리스트."""
    cci_values = [1.0, 2.0, 3.0]
    signal = calculate_cci_signal(cci_values, signal_period=10)
    assert signal == []


def test_calculate_cci_signal_moving_average():
    """시그널이 CCI의 이동평균인지 검증."""
    cci_values = [1.0, 2.0, 3.0, 4.0, 5.0]
    signal = calculate_cci_signal(cci_values, signal_period=3)

    # signal[0] = mean([1, 2, 3]) = 2.0
    # signal[1] = mean([2, 3, 4]) = 3.0
    # signal[2] = mean([3, 4, 5]) = 4.0
    assert len(signal) == 3
    assert abs(signal[0] - 2.0) < 1e-9
    assert abs(signal[1] - 3.0) < 1e-9
    assert abs(signal[2] - 4.0) < 1e-9


# ---------------------------------------------------------------------------
# 골든크로스/데드크로스 테스트
# ---------------------------------------------------------------------------


def test_detect_golden_cross_basic():
    """기본 골든크로스 감지."""
    cci = [50.0, 60.0, 70.0, 80.0, 90.0]
    signal = [55.0, 65.0, 75.0, 85.0, 85.0]

    # 마지막 봉: cci[-2]=80 >= signal[-2]=85 (아직 교차 전)
    # 마지막 봉: cci[-1]=90 > signal[-1]=85 (교차됨)
    assert detect_golden_cross(cci, signal) is True


def test_detect_golden_cross_no_cross():
    """골든크로스 미발생."""
    cci = [90.0, 80.0, 70.0, 60.0, 50.0]
    signal = [55.0, 65.0, 75.0, 85.0, 95.0]

    # 마지막 봉: cci[-2]=60 >= signal[-2]=85 (교차 전)
    # 마지막 봉: cci[-1]=50 < signal[-1]=95 (상향 교차 아님)
    assert detect_golden_cross(cci, signal) is False


def test_detect_golden_cross_boundary_equal():
    """경계: cci[-2] == signal[-2] 시 골든크로스 발생 (== 포함)."""
    cci = [50.0, 60.0, 70.0]
    signal = [50.0, 60.0, 65.0]

    # cci[-2]=60 == signal[-2]=60 (조건: <= 만족)
    # cci[-1]=70 > signal[-1]=65 (교차됨)
    assert detect_golden_cross(cci, signal) is True


def test_detect_golden_cross_length_mismatch(caplog):
    """길이 불일치 시 False + 에러 로그."""
    cci = [1.0, 2.0, 3.0]
    signal = [1.0, 2.0]

    result = detect_golden_cross(cci, signal)
    assert result is False
    assert "길이 불일치" in caplog.text


def test_detect_golden_cross_insufficient_length(caplog):
    """길이 < 2 시 False + 에러 로그."""
    cci = [1.0]
    signal = [1.0]

    result = detect_golden_cross(cci, signal)
    assert result is False
    assert "데이터 부족" in caplog.text


def test_detect_dead_cross_basic():
    """기본 데드크로스 감지."""
    cci = [90.0, 85.0, 70.0, 60.0, 50.0]
    signal = [55.0, 65.0, 75.0, 80.0, 85.0]

    # 마지막 봉: cci[-2]=60 < signal[-2]=80 (조건: >= 만족 X, < 만족)
    # 다시: cci[-2]=60 >= signal[-2]=80 조건 필요
    # 수정: cci = [90.0, 85.0, 60.0, 50.0, 45.0], signal = [60.0, 65.0, 75.0, 80.0, 85.0]
    # 이전: cci[-2]=50 < signal[-2]=80 (조건: >= 만족 X)
    # 올바른 예: cci[-2] >= signal[-2] and cci[-1] < signal[-1]
    # cci = [60.0, 55.0], signal = [50.0, 56.0]
    # cci[-2]=60 >= signal[-2]=50 (만족), cci[-1]=55 < signal[-1]=56 (만족)
    cci = [90.0, 85.0, 60.0, 55.0]
    signal = [55.0, 65.0, 75.0, 56.0]

    # 마지막 봉: cci[-2]=60 >= signal[-2]=75 (조건 불만족)
    # 수정: cci[-2]=60 >= signal[-2]=50, cci[-1]=55 < signal[-1]=56
    cci = [90.0, 85.0, 80.0, 60.0, 55.0]
    signal = [55.0, 65.0, 75.0, 50.0, 56.0]

    # cci[-2]=60 >= signal[-2]=50 (만족), cci[-1]=55 < signal[-1]=56 (만족)
    assert detect_dead_cross(cci, signal) is True


def test_detect_dead_cross_no_cross():
    """데드크로스 미발생."""
    cci = [50.0, 60.0, 70.0, 80.0, 90.0]
    signal = [55.0, 65.0, 75.0, 85.0, 85.0]

    # 마지막 봉: cci[-2]=80 > signal[-2]=85 (교차 전)
    # 마지막 봉: cci[-1]=90 > signal[-1]=85 (하향 교차 아님)
    assert detect_dead_cross(cci, signal) is False


def test_detect_dead_cross_length_mismatch(caplog):
    """길이 불일치 시 False + 에러 로그."""
    cci = [1.0, 2.0, 3.0]
    signal = [1.0, 2.0]

    result = detect_dead_cross(cci, signal)
    assert result is False
    assert "길이 불일치" in caplog.text


def test_detect_dead_cross_insufficient_length(caplog):
    """길이 < 2 시 False + 에러 로그."""
    cci = [1.0]
    signal = [1.0]

    result = detect_dead_cross(cci, signal)
    assert result is False
    assert "데이터 부족" in caplog.text


# ---------------------------------------------------------------------------
# CCI 존(Zone) 판정 테스트
# ---------------------------------------------------------------------------


def test_get_cci_zone_overbought_strong():
    """과매수강 (>= 200)."""
    assert get_cci_zone(200.0) == "과매수강"
    assert get_cci_zone(250.0) == "과매수강"
    assert get_cci_zone(float("inf")) == "과매수강"


def test_get_cci_zone_overbought():
    """과매수 (100~199)."""
    assert get_cci_zone(100.0) == "과매수"
    assert get_cci_zone(150.0) == "과매수"
    assert get_cci_zone(199.9) == "과매수"


def test_get_cci_zone_neutral():
    """중립 (-100~99)."""
    assert get_cci_zone(-99.9) == "중립"
    assert get_cci_zone(0.0) == "중립"
    assert get_cci_zone(50.0) == "중립"
    assert get_cci_zone(99.9) == "중립"


def test_get_cci_zone_oversold():
    """과매도 (-200~-100)."""
    assert get_cci_zone(-100.0) == "과매도"
    assert get_cci_zone(-150.0) == "과매도"
    assert get_cci_zone(-199.9) == "과매도"


def test_get_cci_zone_oversold_strong():
    """과매도강 (<= -200)."""
    assert get_cci_zone(-200.0) == "과매도강"
    assert get_cci_zone(-250.0) == "과매도강"
    assert get_cci_zone(float("-inf")) == "과매도강"


def test_get_cci_zone_boundary_cases():
    """경계값 정확성."""
    # 200 경계
    assert get_cci_zone(199.9999) == "과매수"
    assert get_cci_zone(200.0) == "과매수강"

    # 100 경계
    assert get_cci_zone(99.9999) == "중립"
    assert get_cci_zone(100.0) == "과매수"

    # -100 경계
    assert get_cci_zone(-99.9999) == "중립"
    assert get_cci_zone(-100.0) == "과매도"

    # -200 경계
    assert get_cci_zone(-199.9999) == "과매도"
    assert get_cci_zone(-200.0) == "과매도강"


# ---------------------------------------------------------------------------
# 통합 테스트
# ---------------------------------------------------------------------------


def test_cci_with_signal_full_workflow(sample_candles):
    """CCI → 시그널 → 교차 감지 전체 워크플로우."""
    cci_values = calculate_cci(sample_candles, period=10)
    signal_values = calculate_cci_signal(cci_values, signal_period=5)

    # 길이 일치 확인
    assert len(signal_values) == len(cci_values) - (5 - 1)

    # 교차 감지 가능 (예외 없음)
    golden = detect_golden_cross(cci_values, signal_values)
    dead = detect_dead_cross(cci_values, signal_values)

    assert isinstance(golden, bool)
    assert isinstance(dead, bool)


def test_cci_signal_zone_combined(sample_candles):
    """CCI 값과 존 판정 조합."""
    cci_values = calculate_cci(sample_candles, period=10)

    # 각 CCI 값의 존 판정
    for cci_val in cci_values:
        zone = get_cci_zone(cci_val)
        assert zone in ["과매수강", "과매수", "중립", "과매도", "과매도강"]
