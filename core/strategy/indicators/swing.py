"""스윙 고점/저점 탐지 및 다이버전스 판정 모듈.

specs/trade.md 2·3장(진입 시 직전 고점/저점 갱신 판정)과 6장(저점 판단 —
Higher Low 구조·강세 다이버전스·거래량 동반)에서 사용하는 구조 분석 유틸리티.
"""

from __future__ import annotations

import logging

from core.marketdata.models import Candle

logger = logging.getLogger(__name__)

_DEFAULT_PIVOT_WING = 2
_DEFAULT_LOWER_WICK_RATIO = 0.4
_DEFAULT_VOLUME_SURGE_MULTIPLIER = 2.0


def recent_swing_high(candles: list[Candle], n: int = 10) -> float | None:
    """직전 N봉(현재 봉 제외)의 최고가.

    spec 2장 조건3: `max(High[t-N:t-1])`.

    Args:
        candles: Candle 리스트 (오래된 것부터 최신 순).
        n: 탐색 구간 봉 수 (기본값: 10).

    Returns:
        최고가. 비교 가능한 과거 봉이 없으면 None.
    """
    if len(candles) < 2:
        return None
    window = candles[-(n + 1) : -1] if len(candles) > n else candles[:-1]
    if not window:
        return None
    return max(c.high for c in window)


def recent_swing_low(candles: list[Candle], n: int = 10) -> float | None:
    """직전 N봉(현재 봉 제외)의 최저가.

    spec 3장 조건3: `min(Low[t-N:t-1])`.

    Args:
        candles: Candle 리스트 (오래된 것부터 최신 순).
        n: 탐색 구간 봉 수 (기본값: 10).

    Returns:
        최저가. 비교 가능한 과거 봉이 없으면 None.
    """
    if len(candles) < 2:
        return None
    window = candles[-(n + 1) : -1] if len(candles) > n else candles[:-1]
    if not window:
        return None
    return min(c.low for c in window)


def find_pivot_lows(
    candles: list[Candle], left: int = _DEFAULT_PIVOT_WING, right: int = _DEFAULT_PIVOT_WING
) -> list[tuple[int, float]]:
    """피봇 저점(스윙 로우) 탐지.

    바 i가 좌우 각각 `left`/`right`개 봉의 저가보다 같거나 낮으면 피봇 저점으로 인정.
    가장 최근 `right`개 봉은 아직 확정되지 않았으므로 탐색 대상에서 제외한다
    (look-ahead bias 방지).

    Args:
        candles: Candle 리스트 (오래된 것부터 최신 순).
        left: 좌측 비교 봉 수.
        right: 우측 비교 봉 수.

    Returns:
        (인덱스, low) 튜플 리스트, 오래된 것부터 최신 순.
    """
    pivots: list[tuple[int, float]] = []
    n = len(candles)
    for i in range(left, n - right):
        pivot_low = candles[i].low
        is_pivot = all(
            candles[j].low >= pivot_low for j in range(i - left, i + right + 1) if j != i
        )
        if is_pivot:
            pivots.append((i, pivot_low))
    return pivots


def detect_higher_low(
    candles: list[Candle], left: int = _DEFAULT_PIVOT_WING, right: int = _DEFAULT_PIVOT_WING
) -> bool:
    """스윙 로우 구조 전환(Higher Low) 감지.

    spec 6장 항목1: 직전 저점을 하회하다가, 다음 저점이 이전 저점보다 높게 형성
    (`Low[prev_swing_low] < Low[prev_prev_swing_low]` 이면서
    `Low[last_swing_low] > Low[prev_swing_low]`).

    Args:
        candles: Candle 리스트 (오래된 것부터 최신 순).
        left: 피봇 탐지 좌측 비교 봉 수.
        right: 피봇 탐지 우측 비교 봉 수.

    Returns:
        Higher Low 구조 감지 시 True. 피봇이 3개 미만이면 False.
    """
    pivots = find_pivot_lows(candles, left=left, right=right)
    if len(pivots) < 3:
        return False
    low_prev_prev = pivots[-3][1]
    low_prev = pivots[-2][1]
    low_last = pivots[-1][1]
    return low_prev < low_prev_prev and low_last > low_prev


def detect_bullish_divergence(
    candles: list[Candle],
    oscillator: list[float],
    lookback: int = 10,
) -> bool:
    """가격 신저가 + 오실레이터 저점 상승(강세 다이버전스) 감지.

    spec 6장 항목2: `Price`는 신저가 갱신(`Low[t] < Low[t-k]`)하는데
    오실레이터(CCI 또는 Stochastic %D)는 저점이 높아짐(`osc[t] > osc[t-k]`).

    candles와 oscillator는 각각 별도 워밍업 길이를 가질 수 있으나, 둘 다
    "가장 최근 시점"에서 끝나는 시계열이라고 가정한다 (뒤에서부터 인덱싱).

    Args:
        candles: Candle 리스트 (오래된 것부터 최신 순).
        oscillator: CCI 또는 Stochastic %D 등 오실레이터 값 리스트.
        lookback: 비교할 과거 시점 k (기본값: 10).

    Returns:
        강세 다이버전스 감지 시 True. 데이터가 부족하면 False.
    """
    if len(candles) <= lookback or len(oscillator) <= lookback:
        return False

    price_now = candles[-1].low
    price_prev = candles[-1 - lookback].low
    osc_now = oscillator[-1]
    osc_prev = oscillator[-1 - lookback]

    return price_now < price_prev and osc_now > osc_prev


def detect_capitulation_volume(
    candles: list[Candle],
    volume_ma: list[float],
    surge_multiplier: float = _DEFAULT_VOLUME_SURGE_MULTIPLIER,
    lower_wick_ratio: float = _DEFAULT_LOWER_WICK_RATIO,
) -> bool:
    """투매 후 매수세 유입 패턴(거래량 급증 + 아래꼬리 긴 캔들) 감지.

    spec 6장 항목4: 하락 막바지 구간에서 거래량이 직전 N봉 평균 대비 급증 +
    아래꼬리 긴 캔들.

    Args:
        candles: Candle 리스트 (오래된 것부터 최신 순).
        volume_ma: 거래량 이동평균 리스트 (candles와 동일 끝점 기준 정렬).
        surge_multiplier: 거래량 급증 판정 배수 (기본값: 2.0).
        lower_wick_ratio: 아래꼬리 비율 임계값 (기본값: 0.4 = 전체 range의 40%).

    Returns:
        패턴 감지 시 True. 데이터가 부족하거나 평균 거래량이 0이면 False.
    """
    if not candles or not volume_ma:
        return False

    last = candles[-1]
    avg_volume = volume_ma[-1]
    if avg_volume <= 0:
        return False

    volume_surge = last.volume > avg_volume * surge_multiplier

    total_range = last.high - last.low
    if total_range < 1e-9:
        return False

    body_low = min(last.open, last.close)
    lower_wick = body_low - last.low
    has_long_lower_wick = (lower_wick / total_range) >= lower_wick_ratio

    return volume_surge and has_long_lower_wick
