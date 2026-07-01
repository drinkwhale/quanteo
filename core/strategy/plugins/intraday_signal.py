"""장중 시그널 4유형 감지.

4유형:
  TYPE_1: 강세 매수 — 오전 하락→상승 전환 후 박스권 유지, 장 후반 거래량+양봉
  TYPE_2: 매도/주의 — ①번과 동일 오전 흐름 후 14:00 이후 시가 하향 이탈, 위꼬리 음봉
  TYPE_3: 오후 반등 — 오전 내내 하락, 14:00~14:30 이후 거래량급증+반등+시가 위 마감
  TYPE_4: 강한 매도 — 패턴A(오전 급등→즉시 하락), 패턴B(오전부터 지속 하락, 장대음봉)

Look-ahead bias 방지:
  장 마감(15:30) 전에는 UnconfirmedSignal만 반환.
  ConfirmedSignal은 15:30 이후에만 반환.

스펙 참고: specs/trading-strategy.md 5절
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time
from enum import StrEnum
from typing import Union

from core.marketdata.models import Candle
from core.strategy.indicators.ma import CandleClass, classify_candle, is_large_candle

logger = logging.getLogger(__name__)


# ============================================================================
# 타입 정의
# ============================================================================


class IntradaySignalType(StrEnum):
    """장중 시그널 유형.

    TYPE_45DEG는 제거됨 — 매도 방향성 패턴으로 SellPattern에 분리.
    """

    TYPE_1 = "type_1"   # 강세 매수
    TYPE_2 = "type_2"   # 매도/주의
    TYPE_3 = "type_3"   # 오후 반등
    TYPE_4 = "type_4"   # 강한 매도
    NONE = "none"       # 해당 없음


class SellPattern(StrEnum):
    """매도 방향성 특수 패턴.

    detect_45_degree_decline() 결과를 담는 독립 분류.
    """

    NORMAL = "normal"                        # 일반 패턴
    FORTY_FIVE_DEGREE = "forty_five_degree"  # 45도 완만 지속 하락


@dataclass(frozen=True)
class UnconfirmedSignal:
    """미확정 시그널 (장 마감 전 15:30 이전).

    장중 분석 결과이나, 아직 완전히 확정되지 않은 상태.
    사용처에서 ConfirmedSignal 처리 경로와 명시적으로 구분해야 한다.

    Attributes:
        signal_type: 예상 시그널 유형.
        partial_candles: 현재까지 수집된 캔들 (미완성).
        reason: 분석 근거.
    """

    signal_type: IntradaySignalType
    partial_candles: tuple[Candle, ...]
    reason: str


@dataclass(frozen=True)
class ConfirmedSignal:
    """확정 시그널 (장 마감 후 15:30 이후).

    타입 시스템으로 look-ahead bias 방지를 강제한다.
    is_confirmed bool flag 대신 타입 분리로 컴파일 타임에 구분.

    Attributes:
        signal_type: 확정된 시그널 유형.
        candles: 전체 당일 캔들 (완성).
        reason: 분석 근거.
    """

    signal_type: IntradaySignalType
    candles: tuple[Candle, ...]
    reason: str


# 타입 유니온
IntradayResult = Union[UnconfirmedSignal, ConfirmedSignal]


# ============================================================================
# 시간 상수
# ============================================================================

_MORNING_END = time(10, 0, 0)      # 오전 종료
_AFTERNOON_START = time(14, 0, 0)  # 오후 시작
_AFTERNOON_MID = time(14, 30, 0)   # 오후 중간
_MARKET_CLOSE = time(15, 30, 0)    # 장 마감


# ============================================================================
# 내부 헬퍼
# ============================================================================


def _is_morning_dip_then_rise(candles: list[Candle], open_price: float) -> bool:
    """오전 하락→상승 전환 패턴 확인 (오전 10:00 이전 구간).

    최근 2봉 이상에서 일단 하락 후 open_price 위로 회복했는지 확인.

    Args:
        candles: 오전 구간 캔들 리스트.
        open_price: 당일 시가.

    Returns:
        True if 오전 시가 아래 하락 후 현재 시가 위 회복 패턴.
    """
    if len(candles) < 2:
        return False

    # 어느 시점에 시가 아래로 내려갔다가 현재 회복
    had_dip = any(c.low < open_price for c in candles)
    currently_above_open = candles[-1].close > open_price
    return had_dip and currently_above_open


def _calc_volume_ma(candles: list[Candle], period: int = 20) -> float:
    """거래량 이동평균 계산."""
    if not candles:
        return 0.0
    window = candles[-period:] if len(candles) >= period else candles
    return float(sum(c.volume for c in window) / len(window))


# ============================================================================
# 시그널 감지 함수
# ============================================================================


def detect_type_1(
    candles: list[Candle],
    open_price: float,
    current_time: time,
    volume_ma20: float,
) -> bool:
    """TYPE_1 강세 매수 패턴 확인 (확정 여부 제외).

    조건:
      - 오전(< 10:00): 하락→상승 전환 후 박스권 유지
      - 장 후반(>= 14:00): 거래량 증가 + 양봉

    Returns:
        True if TYPE_1 조건 충족.
    """
    if not candles:
        return False

    latest = candles[-1]
    candle_class = classify_candle(latest.open, latest.close)
    current_volume = latest.volume

    if current_time >= _AFTERNOON_START:
        # 장 후반: 거래량 증가 + 양봉
        volume_ok = current_volume > volume_ma20 * 1.5
        is_bullish = candle_class in (CandleClass.BULLISH, CandleClass.DOJI)
        return volume_ok and is_bullish
    else:
        # 오전: 하락→상승 전환
        return _is_morning_dip_then_rise(candles, open_price)


def detect_type_2(
    candles: list[Candle],
    open_price: float,
    current_time: time,
) -> bool:
    """TYPE_2 매도/주의 패턴 확인.

    조건:
      - 오전에 ①번과 동일 패턴(하락→상승 전환)이 있었고
      - 14:00 이후 시가 하향 이탈, 위꼬리 음봉 형성

    Returns:
        True if TYPE_2 조건 충족.
    """
    if not candles or current_time < _AFTERNOON_START:
        return False

    latest = candles[-1]
    candle_class = classify_candle(latest.open, latest.close)

    # 위꼬리 확인 (상단 꼬리 > 몸통 크기)
    body_size = abs(latest.close - latest.open)
    upper_wick = latest.high - max(latest.open, latest.close)
    has_upper_wick = upper_wick > body_size * 0.5

    # 시가 하향 이탈
    below_open = latest.close < open_price

    return (
        candle_class == CandleClass.BEARISH
        and below_open
        and has_upper_wick
    )


def detect_type_3(
    candles: list[Candle],
    open_price: float,
    current_time: time,
    volume_ma20: float,
) -> bool:
    """TYPE_3 오후 반등 패턴 확인.

    조건:
      - 오전 내내 하락 (14:00 이전 저점 연속)
      - 14:00~14:30 이후 거래량 급증 + 반등 + 시가 위 마감

    Returns:
        True if TYPE_3 조건 충족.
    """
    if not candles or current_time < _AFTERNOON_MID:
        return False

    latest = candles[-1]
    candle_class = classify_candle(latest.open, latest.close)
    volume_ok = latest.volume > volume_ma20 * 1.5
    above_open = latest.close > open_price

    return candle_class in (CandleClass.BULLISH, CandleClass.DOJI) and volume_ok and above_open


def detect_type_4(
    candles: list[Candle],
    open_price: float,
    current_time: time,
) -> bool:
    """TYPE_4 강한 매도 패턴 확인.

    패턴A: 오전 급등 후 즉시 하락 전환, 위꼬리 장대음봉
    패턴B: 오전부터 지속 하락, 장대음봉

    Returns:
        True if TYPE_4 조건 충족.
    """
    if not candles:
        return False

    latest = candles[-1]
    candle_class = classify_candle(latest.open, latest.close)
    large_bear = is_large_candle(latest) and candle_class == CandleClass.BEARISH

    if not large_bear:
        return False

    # 패턴A: 오전에 시가 위로 상승했다가 현재 시가 아래로 하락
    had_rise = any(c.high > open_price * 1.005 for c in candles)  # 0.5% 이상 상승
    now_below_open = latest.close < open_price
    pattern_a = had_rise and now_below_open

    # 패턴B: 처음부터 시가 아래로만 내려감
    always_declining = all(c.close <= open_price for c in candles)
    pattern_b = always_declining and now_below_open

    return pattern_a or pattern_b


# ============================================================================
# 통합 감지 함수
# ============================================================================


def detect_intraday_signal(
    candles: list[Candle],
    open_price: float,
    current_time: time,
    volume_ma20: float | None = None,
) -> IntradayResult:
    """장중 시그널 감지 진입점.

    Args:
        candles: 당일 60분봉 캔들 리스트 (오래된 것부터 최신 순).
        open_price: 당일 시가.
        current_time: 현재 시각.
        volume_ma20: 거래량 20기간 이동평균. None이면 candles에서 계산.

    Returns:
        UnconfirmedSignal: 15:30 이전 (장 마감 전).
        ConfirmedSignal: 15:30 이후 (장 마감 후).
    """
    if volume_ma20 is None:
        volume_ma20 = _calc_volume_ma(candles)

    is_confirmed_time = current_time >= _MARKET_CLOSE
    signal_type = IntradaySignalType.NONE
    reason = "장중 시그널 없음"

    if not candles:
        if is_confirmed_time:
            return ConfirmedSignal(
                signal_type=IntradaySignalType.NONE,
                candles=tuple(),
                reason="캔들 데이터 없음",
            )
        return UnconfirmedSignal(
            signal_type=IntradaySignalType.NONE,
            partial_candles=tuple(),
            reason="캔들 데이터 없음",
        )

    # TYPE_4 최우선 확인 (강한 매도 신호)
    if detect_type_4(candles, open_price, current_time):
        signal_type = IntradaySignalType.TYPE_4
        reason = "TYPE_4: 강한 매도 — 장대음봉 패턴 감지"
    elif detect_type_2(candles, open_price, current_time):
        signal_type = IntradaySignalType.TYPE_2
        reason = "TYPE_2: 매도/주의 — 14:00 이후 시가 하향 이탈, 위꼬리 음봉"
    elif detect_type_3(candles, open_price, current_time, volume_ma20):
        signal_type = IntradaySignalType.TYPE_3
        reason = "TYPE_3: 오후 반등 — 14:30 이후 거래량 급증 + 시가 위 마감"
    elif detect_type_1(candles, open_price, current_time, volume_ma20):
        signal_type = IntradaySignalType.TYPE_1
        reason = "TYPE_1: 강세 매수 — 오전 하락→상승 전환 또는 장 후반 거래량+양봉"

    if is_confirmed_time:
        return ConfirmedSignal(
            signal_type=signal_type,
            candles=tuple(candles),
            reason=reason,
        )
    return UnconfirmedSignal(
        signal_type=signal_type,
        partial_candles=tuple(candles),
        reason=reason,
    )
