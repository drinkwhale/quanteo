"""DEMA (Double Exponential Moving Average) 지표 계산 모듈.

DEMA = 2 * EMA(N) - EMA(EMA(N), N)

specs/trade.md 0장·1장 기준 — 추세 방향의 "확인"용 지표(후행지표).
진입/청산의 단독 트리거로 쓰지 않고, 기울기 전환 확인용으로만 사용한다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def calculate_ema(values: list[float], period: int) -> list[float]:
    """지수이동평균(EMA) 계산.

    초기값(seed)은 첫 `period`개의 단순평균(SMA)을 사용한다 (표준 관행).

    Args:
        values: 숫자 리스트 (오래된 것부터 최신 순).
        period: EMA 계산 기간.

    Returns:
        EMA 값 리스트. 길이 = len(values) - period + 1.
        len(values) < period이면 빈 리스트 반환.
    """
    if len(values) < period:
        return []

    multiplier = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    ema_values = [seed]
    for value in values[period:]:
        ema_values.append(value * multiplier + ema_values[-1] * (1 - multiplier))
    return ema_values


def calculate_dema(values: list[float], period: int) -> list[float]:
    """DEMA 계산 (이중 지수이동평균).

    DEMA는 단일 EMA보다 지연(lag)이 적어 추세 전환을 더 빠르게 반영한다.

    Args:
        values: 숫자 리스트 (오래된 것부터 최신 순), 보통 종가.
        period: DEMA 계산 기간.

    Returns:
        DEMA 값 리스트. 데이터가 부족하면 빈 리스트 반환.
    """
    ema1 = calculate_ema(values, period)
    if len(ema1) < period:
        return []

    ema2 = calculate_ema(ema1, period)
    if not ema2:
        return []

    # ema1이 ema2보다 길므로 뒤쪽(최신)을 ema2 길이에 맞춰 정렬
    ema1_aligned = ema1[-len(ema2) :]
    return [2 * e1 - e2 for e1, e2 in zip(ema1_aligned, ema2, strict=True)]


def detect_dema_slope_up(dema: list[float]) -> bool:
    """DEMA 기울기 우상향 전환 감지.

    spec 2장 조건1: `DEMA[t] - DEMA[t-1] > DEMA[t-1] - DEMA[t-2]`
    (직전 구간보다 이번 구간의 상승폭이 더 커짐 = 우상향 강화)

    Args:
        dema: DEMA 값 리스트 (오래된 것부터 최신 순).

    Returns:
        기울기 우상향 전환 시 True. 데이터가 3개 미만이면 False.
    """
    if len(dema) < 3:
        return False
    return (dema[-1] - dema[-2]) > (dema[-2] - dema[-3])


def detect_dema_slope_down(dema: list[float]) -> bool:
    """DEMA 기울기 하향 전환 감지.

    spec 3장 조건1: `DEMA[t] - DEMA[t-1] < DEMA[t-1] - DEMA[t-2]`
    (직전 구간보다 이번 구간의 하락폭이 더 커짐 = 더 가파르게 하락)

    Args:
        dema: DEMA 값 리스트 (오래된 것부터 최신 순).

    Returns:
        기울기 하향 전환 시 True. 데이터가 3개 미만이면 False.
    """
    if len(dema) < 3:
        return False
    return (dema[-1] - dema[-2]) < (dema[-2] - dema[-3])
