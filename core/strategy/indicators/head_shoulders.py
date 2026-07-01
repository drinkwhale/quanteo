"""헤드앤숄더 패턴 감지.

주봉 기준 헤드앤숄더(하락전환) 및 역헤드앤숄더(상승전환) 패턴을 감지한다.
하락전환 감지 시 CcibbcStrategy.on_tick()에서 신뢰도 스코어 무관하게
즉시 전량 매도 override가 적용된다.

T081 구현.
스펙 참고: specs/trading-strategy.md 7절
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from core.marketdata.models import Candle

logger = logging.getLogger(__name__)

# 헤드앤숄더 감지에 필요한 최소 캔들 수 (어깨 2개 + 머리 1개 + 여유)
_MIN_CANDLES = 10


@dataclass(frozen=True)
class HeadShouldersResult:
    """헤드앤숄더 패턴 감지 결과.

    Attributes:
        pattern_type: 패턴 유형 (하락전환 / 상승전환).
        right_shoulder_idx: 오른쪽 어깨의 캔들 인덱스.
        neckline: 넥라인 가격 (두 저점의 평균).
        volume_confirms: 거래량 조건 충족 여부.
    """

    pattern_type: Literal["하락전환", "상승전환"]
    right_shoulder_idx: int
    neckline: float
    volume_confirms: bool


def _find_local_peaks(values: list[float], window: int = 1) -> list[int]:
    """국소 고점 인덱스 목록 반환."""
    peaks = []
    n = len(values)
    for i in range(window, n - window):
        if all(values[i] > values[i - j] for j in range(1, window + 1)) and all(
            values[i] > values[i + j] for j in range(1, window + 1)
        ):
            peaks.append(i)
    return peaks


def _find_local_troughs(values: list[float], window: int = 1) -> list[int]:
    """국소 저점 인덱스 목록 반환."""
    troughs = []
    n = len(values)
    for i in range(window, n - window):
        if all(values[i] < values[i - j] for j in range(1, window + 1)) and all(
            values[i] < values[i + j] for j in range(1, window + 1)
        ):
            troughs.append(i)
    return troughs


def detect_head_shoulders(candles: list[Candle]) -> HeadShouldersResult | None:
    """헤드앤숄더(하락전환) 또는 역헤드앤숄더(상승전환) 패턴 감지.

    하락전환(헤드앤숄더):
    - 왼쪽 어깨(고점) → 머리(더 높은 고점) → 오른쪽 어깨(낮은 고점) 구조
    - 오른쪽 어깨 거래량 < 머리 거래량 (감소)
    - 오른쪽 어깨 고점이 왼쪽 어깨 대비 50% 미달 상승 (약한 반등)

    상승전환(역헤드앤숄더):
    - 왼쪽 어깨(저점) → 머리(더 낮은 저점) → 오른쪽 어깨(높은 저점) 구조
    - 거래량 급증 + 장대양봉으로 왼쪽 고점 돌파

    Args:
        candles: 주봉 캔들 리스트 (오래된 순).

    Returns:
        HeadShouldersResult 또는 None (패턴 미감지).
    """
    if len(candles) < _MIN_CANDLES:
        logger.warning(
            "헤드앤숄더 감지 불가 — 캔들 부족 (필요: %d, 현재: %d)", _MIN_CANDLES, len(candles)
        )
        return None

    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    n = len(candles)

    # ── 하락전환: 헤드앤숄더 감지 ──
    result = _detect_bearish(closes, volumes, candles, n)
    if result is not None:
        return result

    # ── 상승전환: 역헤드앤숄더 감지 ──
    return _detect_bullish(closes, volumes, candles, n)


def _detect_bearish(
    closes: list[float],
    volumes: list[int],
    candles: list[Candle],
    n: int,
) -> HeadShouldersResult | None:
    """하락전환 헤드앤숄더 감지."""
    peaks = _find_local_peaks(closes)
    if len(peaks) < 3:
        return None

    # 최근 3개 고점 사용
    p1, p2, p3 = peaks[-3], peaks[-2], peaks[-1]  # 왼어깨, 머리, 오른어깨

    left_shoulder_close = closes[p1]
    head_close = closes[p2]
    right_shoulder_close = closes[p3]

    # 머리가 양 어깨보다 높아야 함
    if not (head_close > left_shoulder_close and head_close > right_shoulder_close):
        return None

    # 오른쪽 어깨 < 왼쪽 어깨 (약한 반등)
    if right_shoulder_close >= left_shoulder_close:
        return None

    # 직전 하락폭 50% 미달 조건: 오른쪽 어깨가 머리에서의 반등 폭 < 50%
    # 절댓값 높이 기반으로 계산해 부호 의존 제거.
    # head_height = 머리가 왼쪽어깨보다 높은 폭 (항상 양수여야 함)
    head_height = head_close - left_shoulder_close
    if head_height <= 0:
        # 머리가 왼쪽어깨보다 반드시 높아야 함 (퇴화 패턴 방지)
        return None
    # rebound = 오른쪽어깨가 머리보다 얼마나 반등했는지 (최소 0)
    rebound = max(right_shoulder_close - head_close, 0.0)
    if rebound / head_height >= 0.5:
        # 50% 이상 반등 → 전형적인 헤드앤숄더 아님
        return None

    # 거래량 감소 확인 (오른쪽 어깨 거래량 < 머리 거래량)
    right_vol = volumes[p3]
    head_vol = volumes[p2]
    volume_confirms = right_vol < head_vol

    # 넥라인: p1~p2 사이 저점과 p2~p3 사이 저점의 평균
    trough_left = min(closes[p1 : p2 + 1])
    trough_right = min(closes[p2 : p3 + 1])
    neckline = (trough_left + trough_right) / 2

    return HeadShouldersResult(
        pattern_type="하락전환",
        right_shoulder_idx=p3,
        neckline=neckline,
        volume_confirms=volume_confirms,
    )


def _detect_bullish(
    closes: list[float],
    volumes: list[int],
    candles: list[Candle],
    n: int,
) -> HeadShouldersResult | None:
    """상승전환 역헤드앤숄더 감지."""
    troughs = _find_local_troughs(closes)
    if len(troughs) < 3:
        return None

    t1, t2, t3 = troughs[-3], troughs[-2], troughs[-1]  # 왼어깨, 머리, 오른어깨

    left_trough = closes[t1]
    head_trough = closes[t2]
    right_trough = closes[t3]

    # 머리가 양 어깨 저점보다 낮아야 함
    if not (head_trough < left_trough and head_trough < right_trough):
        return None

    # 오른쪽 어깨 저점 > 왼쪽 어깨 저점 (회복)
    if right_trough <= left_trough:
        return None

    # 거래량 급증 + 최근 봉이 왼쪽 고점 돌파 확인
    # 왼쪽 어깨 이후 최고점 (저항선)
    if t3 >= n - 1:
        return None

    # 최근 캔들(오른쪽 어깨 이후)에서 거래량 급증 + 장대양봉 확인
    post_right = candles[t3 + 1 :]
    if not post_right:
        return None

    last = post_right[-1]
    volume_avg = sum(volumes[t1:t3]) / max(t3 - t1, 1)
    volume_surge = last.volume > volume_avg * 1.5
    large_bullish = (last.close - last.open) / max(last.open, 1) > 0.01  # 1% 이상 양봉

    # 왼쪽 어깨 이전 고점 돌파 확인
    left_peak = max(closes[: t1 + 1]) if t1 > 0 else closes[t1]
    breaks_resistance = last.close > left_peak

    volume_confirms = volume_surge and large_bullish

    if not breaks_resistance:
        return None

    neckline = (closes[t1] + closes[t3]) / 2

    return HeadShouldersResult(
        pattern_type="상승전환",
        right_shoulder_idx=t3,
        neckline=neckline,
        volume_confirms=volume_confirms,
    )
