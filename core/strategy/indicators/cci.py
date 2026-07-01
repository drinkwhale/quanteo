"""CCI (Commodity Channel Index) 지표 계산 모듈.

CCI 지표 계산: TP = (high + low + close) / 3
              SMA(20) = TP의 20기간 이동평균
              MD(20) = TP의 20기간 평균편차
              CCI = (TP - SMA) / (0.015 * MD)

골든크로스/데드크로스 감지 및 과매수/과매도 구간 판정 기능 포함.
"""

from __future__ import annotations

import logging
from typing import Literal

from core.marketdata.models import Candle

logger = logging.getLogger(__name__)


def calculate_cci(candles: list[Candle], period: int = 20) -> list[float]:
    """CCI 지표 계산.

    Args:
        candles: Candle 객체 리스트 (오래된 것부터 최신 순).
        period: CCI 계산 기간 (기본값: 20).

    Returns:
        CCI 값 리스트. 길이 = len(candles) - (period - 1).
        len(candles) < period이면 빈 리스트 반환.
        MD ≈ 0일 때는 0.0 대체 (inf/nan 전파 방지).
    """
    if len(candles) < period:
        return []

    # TP (Typical Price) 계산
    tp_values = [(c.high + c.low + c.close) / 3.0 for c in candles]

    # SMA(period) 계산
    sma_values = []
    for i in range(period - 1, len(tp_values)):
        window = tp_values[i - period + 1 : i + 1]
        sma = sum(window) / period
        sma_values.append(sma)

    # MD (Mean Deviation) 계산 및 CCI 계산
    cci_values = []
    for i in range(period - 1, len(tp_values)):
        window = tp_values[i - period + 1 : i + 1]
        sma = sma_values[i - (period - 1)]

        # MD = 평균편차
        md = sum(abs(val - sma) for val in window) / period

        # CCI = (TP - SMA) / (0.015 * MD)
        # 0.015는 Lambert(1980) 원 논문의 정규화 상수.
        # ±100 존 경계가 일반적인 추세 이탈 구간에 해당하도록 스케일링된 값.
        if md < 1e-9:
            cci = 0.0
            logger.warning("CCI: MD≈0, 중립값 대체")
        else:
            cci = (tp_values[i] - sma) / (0.015 * md)

        cci_values.append(cci)

    return cci_values


def calculate_cci_signal(cci_values: list[float], signal_period: int = 20) -> list[float]:
    """CCI의 시그널 라인 계산 (CCI의 이동평균).

    Args:
        cci_values: CCI 값 리스트.
        signal_period: 시그널 라인 기간 (기본값: 20).

    Returns:
        시그널 라인 값 리스트. 길이 = len(cci_values) - (signal_period - 1).
        len(cci_values) < signal_period이면 빈 리스트 반환.
    """
    if len(cci_values) < signal_period:
        return []

    signal_values = []
    for i in range(signal_period - 1, len(cci_values)):
        window = cci_values[i - signal_period + 1 : i + 1]
        signal = sum(window) / signal_period
        signal_values.append(signal)

    return signal_values


def detect_golden_cross(cci: list[float], signal: list[float]) -> bool:
    """CCI와 시그널 라인의 골든크로스 감지 (최신 봉 기준).

    골든크로스: 이전 봉에서 CCI ≤ 시그널, 현재 봉에서 CCI > 시그널.

    Args:
        cci: CCI 값 리스트.
        signal: 시그널 라인 값 리스트.

    Returns:
        골든크로스 발생 시 True, 아니면 False.
        길이 불일치 또는 길이 < 2일 때 False + logger.error.
    """
    if len(cci) != len(signal):
        logger.error(
            f"detect_golden_cross: CCI와 시그널 길이 불일치 "
            f"(cci={len(cci)}, signal={len(signal)})"
        )
        return False

    if len(cci) < 2:
        logger.error(f"detect_golden_cross: 데이터 부족 (길이={len(cci)}), 최소 2개 필요")
        return False

    return cci[-2] <= signal[-2] and cci[-1] > signal[-1]


def detect_dead_cross(cci: list[float], signal: list[float]) -> bool:
    """CCI와 시그널 라인의 데드크로스 감지 (최신 봉 기준).

    데드크로스: 이전 봉에서 CCI ≥ 시그널, 현재 봉에서 CCI < 시그널.

    Args:
        cci: CCI 값 리스트.
        signal: 시그널 라인 값 리스트.

    Returns:
        데드크로스 발생 시 True, 아니면 False.
        길이 불일치 또는 길이 < 2일 때 False + logger.error.
    """
    if len(cci) != len(signal):
        logger.error(
            f"detect_dead_cross: CCI와 시그널 길이 불일치 "
            f"(cci={len(cci)}, signal={len(signal)})"
        )
        return False

    if len(cci) < 2:
        logger.error(f"detect_dead_cross: 데이터 부족 (길이={len(cci)}), 최소 2개 필요")
        return False

    return cci[-2] >= signal[-2] and cci[-1] < signal[-1]


def get_cci_zone(
    cci_value: float,
) -> Literal["과매수강", "과매수", "중립", "과매도", "과매도강"]:
    """CCI 값에 해당하는 존(Zone) 판정.

    경계값:
    - ±200: 극단 경계
    - ±100: 과매수/과매도 경계

    Args:
        cci_value: CCI 값.

    Returns:
        존 구분 문자열.
    """
    if cci_value >= 200:
        return "과매수강"
    elif cci_value >= 100:
        return "과매수"
    elif cci_value > -100:
        return "중립"
    elif cci_value > -200:
        return "과매도"
    else:
        return "과매도강"
