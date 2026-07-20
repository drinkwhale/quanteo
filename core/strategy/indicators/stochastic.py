"""Stochastic %K/%D 지표 계산 모듈.

specs/trade.md 0장 기준 — 과열/과매도 보조 필터(entry_filter_and_secondary_confirmation).
단독 트리거로 쓰지 않고, DEMA·CCI와 조합해서만 사용한다.

NOTE: 스펙에는 %D(3) 기간만 명시되어 있고 %K 기간은 명시되지 않았다.
업계 표준값인 14를 기본값으로 사용하며, 실제 백테스트로 재검증이 필요하다
(specs/trade.md 9장 "임계값 재검증" 참고).
"""

from __future__ import annotations

import logging

from core.marketdata.models import Candle
from core.strategy.indicators.ma import calculate_sma

logger = logging.getLogger(__name__)

_FLAT_MARKET_FALLBACK = 50.0


def calculate_stochastic_k(candles: list[Candle], k_period: int = 14) -> list[float]:
    """Stochastic %K 계산.

    %K = (종가 - 최근 k_period 최저가) / (최근 k_period 최고가 - 최저가) * 100

    Args:
        candles: Candle 리스트 (오래된 것부터 최신 순).
        k_period: %K 계산 기간 (기본값: 14).

    Returns:
        %K 값 리스트. 길이 = len(candles) - k_period + 1.
        len(candles) < k_period이면 빈 리스트 반환.
        고가==저가(횡보/데이터 이상)이면 50.0(중립)으로 대체.
    """
    if len(candles) < k_period:
        return []

    k_values = []
    for i in range(k_period - 1, len(candles)):
        window = candles[i - k_period + 1 : i + 1]
        highest = max(c.high for c in window)
        lowest = min(c.low for c in window)
        price_range = highest - lowest

        if price_range < 1e-9:
            k = _FLAT_MARKET_FALLBACK
            logger.warning("Stochastic %%K: 고가==저가, 중립값(50.0) 대체")
        else:
            k = (candles[i].close - lowest) / price_range * 100.0

        k_values.append(k)

    return k_values


def calculate_stochastic_d(k_values: list[float], d_period: int = 3) -> list[float]:
    """Stochastic %D 계산 (%K의 이동평균).

    Args:
        k_values: %K 값 리스트.
        d_period: %D 계산 기간 (기본값: 3).

    Returns:
        %D 값 리스트. len(k_values) < d_period이면 빈 리스트 반환.
    """
    return calculate_sma(k_values, d_period)


def detect_stochastic_bottom_reversal(d_values: list[float], oversold: float = 20.0) -> bool:
    """%D 과매도 구간 반등(골든크로스 근사) 감지.

    표준 스토캐스틱은 %K/%D 교차로 판단하지만, specs/trade.md 6장은 %D 단일
    계열만 정의한다. 따라서 직전 봉이 과매도 구간(<=oversold)이었고 이번 봉에서
    %D가 상승 전환한 것을 "반등"으로 근사한다.

    Args:
        d_values: %D 값 리스트 (오래된 것부터 최신 순).
        oversold: 과매도 기준선 (기본값: 20.0).

    Returns:
        반등 감지 시 True. 데이터 2개 미만이면 False.
    """
    if len(d_values) < 2:
        return False
    return d_values[-2] <= oversold and d_values[-1] > d_values[-2]


def detect_stochastic_top_reversal(d_values: list[float], overbought: float = 80.0) -> bool:
    """%D 과매수 구간 반락(데드크로스 근사) 감지.

    Args:
        d_values: %D 값 리스트 (오래된 것부터 최신 순).
        overbought: 과매수 기준선 (기본값: 80.0).

    Returns:
        반락 감지 시 True. 데이터 2개 미만이면 False.
    """
    if len(d_values) < 2:
        return False
    return d_values[-2] >= overbought and d_values[-1] < d_values[-2]
