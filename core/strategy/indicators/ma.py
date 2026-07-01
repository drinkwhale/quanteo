"""이동평균선 & 거래량 지표 모듈.

SMA (Simple Moving Average) 계산 및 캔들 분류(양봉/음봉/십자형),
가격 포지션 판단(5일선 위/사이/아래), 대형 캔들 판별 기능.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from core.marketdata.models import Candle

logger = logging.getLogger(__name__)


class CandleClass(StrEnum):
    """캔들 분류.

    BULLISH: 양봉 (close > open)
    BEARISH: 음봉 (close < open)
    DOJI: 십자형 (둘 다 아님)
    """

    BULLISH = "bullish"
    BEARISH = "bearish"
    DOJI = "doji"


class PricePosition(StrEnum):
    """가격 위치 분류.

    ABOVE: 5일선 위 (가격 > ma5)
    BETWEEN: 5일선과 20일선 사이 (ma20 <= 가격 <= ma5)
    BELOW: 20일선 아래 (가격 < ma20)
    """

    ABOVE = "above"
    BETWEEN = "between"
    BELOW = "below"


def calculate_sma(values: list[float], period: int) -> list[float]:
    """범용 SMA (Simple Moving Average) 계산.

    Args:
        values: 숫자 리스트 (오래된 것부터 최신 순).
        period: SMA 계산 기간.

    Returns:
        SMA 값 리스트. 길이 = len(values) - (period - 1).
        len(values) < period이면 빈 리스트 반환.
    """
    if len(values) < period:
        return []

    sma_values = []
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        sma = sum(window) / period
        sma_values.append(sma)

    return sma_values


def classify_candle(open_price: float, close_price: float, threshold: float = 0.001) -> CandleClass:
    """캔들 분류 (양봉/음봉/십자형).

    양봉 조건: close > open * (1 + threshold)
    음봉 조건: close < open * (1 - threshold)
    그 외: 십자형

    Args:
        open_price: 시가.
        close_price: 종가.
        threshold: 양/음봉 판단 임계값 (기본값: 0.001 = 0.1%).

    Returns:
        CandleClass 열거형 값.
    """
    upper_bound = open_price * (1 + threshold)
    lower_bound = open_price * (1 - threshold)

    if close_price > upper_bound:
        return CandleClass.BULLISH
    elif close_price < lower_bound:
        return CandleClass.BEARISH
    else:
        return CandleClass.DOJI


def is_large_candle(candle: Candle, body_ratio: float = 0.6) -> bool:
    """장대양봉/장대음봉 판별.

    몸통 비율 = |close - open| / (high - low).
    body_ratio를 초과하면 장대 캔들로 판정.
    high == low (십자 또는 도지)이면 False 반환 (제로 분모 방지).

    Args:
        candle: Candle 객체.
        body_ratio: 장대 판정 기준 비율 (기본값: 0.6 = 60%).

    Returns:
        장대 캔들 판정. True = 장대, False = 그 외.
    """
    body_size = abs(candle.close - candle.open)
    total_range = candle.high - candle.low

    # 제로 분모 방지: high == low
    if total_range < 1e-9:
        return False

    ratio = body_size / total_range
    return ratio >= body_ratio


def is_alignment_bullish(ma5: float, ma20: float) -> bool:
    """정배열 판단 (5일선 > 20일선).

    Args:
        ma5: 5일 이동평균선.
        ma20: 20일 이동평균선.

    Returns:
        정배열(강세) 시 True, 그 외 False.
    """
    return ma5 > ma20


def price_position(price: float, ma5: float, ma20: float) -> PricePosition:
    """가격 포지션 분류.

    - ABOVE: price > ma5 (5일선 위)
    - BETWEEN: ma20 <= price <= ma5 (5일선과 20일선 사이, 눌림목)
    - BELOW: price < ma20 (20일선 아래, 급락)

    Args:
        price: 현재 가격.
        ma5: 5일 이동평균선.
        ma20: 20일 이동평균선.

    Returns:
        PricePosition 열거형 값.
    """
    if price > ma5:
        return PricePosition.ABOVE
    elif price >= ma20:
        return PricePosition.BETWEEN
    else:
        return PricePosition.BELOW
