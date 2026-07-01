"""박병창 매도 2원칙 구현.

2원칙:
  1원칙: 5일선 위에 있을 때
    - 거래량 급증 + 음봉       → 40% 분할 매도
    - 거래량 폭증 + 십자형     → 30% 분할 매도
    - price < ma5 AND ma5 < ma20 → 전량 매도

  2원칙: 5일선과 20일선 사이에 있을 때
    - 거래량 증가 + 음봉       → 50% 분할 매도
    - 20일선 바로 위 거래량 급증 + 장대음봉 → 전량 매도

  특수 패턴:
    - detect_45_degree_decline() — 장중 완만 지속 하락 감지

스펙 참고: specs/trading-strategy.md 4절, 5절(특수 패턴)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import numpy as np

from core.marketdata.models import Candle
from core.strategy.indicators.ma import CandleClass, classify_candle, is_large_candle

logger = logging.getLogger(__name__)


# ============================================================================
# 타입 정의
# ============================================================================


class SellAction(StrEnum):
    """매도 액션 분류.

    단일 StrEnum으로 유효하지 않은 조합 불가 강제.
    """

    FULL_EXIT = "full_exit"          # 전량 매도
    PARTIAL_30PCT = "partial_30pct"  # 30% 분할 매도
    PARTIAL_40PCT = "partial_40pct"  # 40% 분할 매도
    PARTIAL_50PCT = "partial_50pct"  # 50% 분할 매도


@dataclass(frozen=True)
class BbcSellSignal:
    """박병창 매도 시그널.

    Attributes:
        principle: 매도 원칙 번호 (1 또는 2).
        action: 매도 비율 액션 (SellAction enum).
        reason: 시그널 근거 설명.
    """

    principle: Literal[1, 2]
    action: SellAction
    reason: str


# ============================================================================
# 특수 패턴: 45도 각도 지속 하락 감지
# ============================================================================


def detect_45_degree_decline(candles: list[Candle], window: int = 12) -> bool:
    """장중 완만 지속 하락 패턴 감지.

    선형회귀 기울기 + 거래량 분산으로 판단:
      - 기울기 < 0 (하락 추세)
      - 거래량 분산이 낮음 (꾸준한 매도, 급등급락 없음)

    Args:
        candles: 캔들 리스트 (오래된 것부터 최신 순). 최근 window개 사용.
        window: 분석 창 크기 (기본값: 12봉).

    Returns:
        True if 45도 완만 하락 패턴 감지, False otherwise.
        len(candles) < window이면 False + logger.warning.
    """
    if len(candles) < window:
        logger.warning(
            "detect_45_degree_decline: 캔들 수(%d) < window(%d), 조기 판단 방지 — False 반환",
            len(candles),
            window,
        )
        return False

    recent = candles[-window:]
    closes = np.array([c.close for c in recent], dtype=float)
    volumes = np.array([c.volume for c in recent], dtype=float)
    x = np.arange(len(closes), dtype=float)

    # 선형회귀 기울기
    if len(x) < 2:
        return False

    cov_matrix = np.cov(x, closes)
    if cov_matrix.shape != (2, 2):
        return False
    var_x = cov_matrix[0, 0]
    cov_xy = cov_matrix[0, 1]
    slope = cov_xy / var_x if var_x > 1e-9 else 0.0

    # 정규화 기울기 (시가 대비 비율로 스케일링)
    base_price = closes[0] if closes[0] > 0 else 1.0
    normalized_slope = slope / base_price

    # 거래량 분산 (낮을수록 꾸준한 매도)
    vol_mean = float(np.mean(volumes)) if len(volumes) > 0 else 0.0
    vol_cv = float(np.std(volumes) / vol_mean) if vol_mean > 1e-9 else 1.0

    # 판단:
    # - 하락 추세: 정규화 기울기 < -0.001 (봉당 0.1% 이상 하락)
    # - 꾸준한 매도: 거래량 변동계수 < 0.8 (비교적 균등한 거래량)
    is_declining = normalized_slope < -0.001
    is_steady_volume = vol_cv < 0.8

    return is_declining and is_steady_volume


# ============================================================================
# 매도 원칙 판단 함수
# ============================================================================


def check_sell_principle_1(
    current_price: float,
    ma5: float,
    ma20: float,
    candles: list[Candle],
    current_volume: int,
    volume_ma20: float,
) -> BbcSellSignal | None:
    """매도 제1원칙: 5일선 위에 있을 때.

    신호:
      1. 거래량 급증(> volume_ma20 * 2.0) + 음봉   → PARTIAL_40PCT
      2. 거래량 폭증(> volume_ma20 * 2.0) + 십자형 → PARTIAL_30PCT
      3. price < ma5 AND ma5 < ma20                 → FULL_EXIT (역배열 전환)

    Args:
        current_price: 현재가.
        ma5: 5일 이동평균.
        ma20: 20일 이동평균.
        candles: 캔들 리스트.
        current_volume: 현재 거래량.
        volume_ma20: 거래량 20기간 이동평균.

    Returns:
        BbcSellSignal or None.
    """
    # 역배열 전환 전량 매도 (price < ma5 AND ma5 < ma20)
    if current_price < ma5 and ma5 < ma20:
        return BbcSellSignal(
            principle=1,
            action=SellAction.FULL_EXIT,
            reason=f"제1원칙 역배열 전환: price({current_price}) < ma5({ma5:.1f}) < ma20({ma20:.1f}) — 전량 매도",
        )

    # 5일선 위에 없으면 제1원칙 미해당
    if current_price <= ma5:
        return None

    if not candles:
        return None

    latest = candles[-1]
    candle_class = classify_candle(latest.open, latest.close)
    volume_surge = current_volume > volume_ma20 * 2.0

    if volume_surge and candle_class == CandleClass.BEARISH:
        return BbcSellSignal(
            principle=1,
            action=SellAction.PARTIAL_40PCT,
            reason=(
                f"제1원칙: price({current_price}) > ma5({ma5:.1f}), "
                f"거래량 급증({current_volume:.0f} > {volume_ma20 * 2.0:.0f}) + 음봉 — 40% 매도"
            ),
        )

    if volume_surge and candle_class == CandleClass.DOJI:
        return BbcSellSignal(
            principle=1,
            action=SellAction.PARTIAL_30PCT,
            reason=(
                f"제1원칙: price({current_price}) > ma5({ma5:.1f}), "
                f"거래량 폭증({current_volume:.0f} > {volume_ma20 * 2.0:.0f}) + 십자형 — 30% 매도"
            ),
        )

    return None


def check_sell_principle_2(
    current_price: float,
    ma5: float,
    ma20: float,
    candles: list[Candle],
    current_volume: int,
    volume_ma20: float,
) -> BbcSellSignal | None:
    """매도 제2원칙: 5일선과 20일선 사이에 있을 때.

    조건:
      - 일반: ma20 < price <= ma5 AND 거래량 증가(> volume_ma20 * 1.5) + 음봉 → PARTIAL_50PCT
      - 특별: 20일선 바로 위(price <= ma20 * 1.05) + 거래량 급증(> volume_ma20 * 2.0)
              + 장대음봉 → FULL_EXIT

    Args:
        current_price: 현재가.
        ma5: 5일 이동평균.
        ma20: 20일 이동평균.
        candles: 캔들 리스트.
        current_volume: 현재 거래량.
        volume_ma20: 거래량 20기간 이동평균.

    Returns:
        BbcSellSignal or None.
    """
    # 5~20일선 사이 구간 확인
    if not (ma20 < current_price <= ma5):
        return None

    if not candles:
        return None

    latest = candles[-1]
    candle_class = classify_candle(latest.open, latest.close)

    # 특별 규칙: 20일선 바로 위 + 거래량 급증 + 장대음봉 → 전량 매도
    near_ma20 = current_price <= ma20 * 1.05  # 20일선 5% 이내
    if (
        near_ma20
        and current_volume > volume_ma20 * 2.0
        and candle_class == CandleClass.BEARISH
        and is_large_candle(latest)
    ):
        return BbcSellSignal(
            principle=2,
            action=SellAction.FULL_EXIT,
            reason=(
                f"제2원칙 특별규칙: 20일선 바로 위({current_price:.0f} ≤ ma20*1.05={ma20 * 1.05:.0f}), "
                f"거래량 폭증({current_volume:.0f}) + 장대음봉 — 전량 매도"
            ),
        )

    # 일반: 거래량 증가 + 음봉
    if current_volume > volume_ma20 * 1.5 and candle_class == CandleClass.BEARISH:
        return BbcSellSignal(
            principle=2,
            action=SellAction.PARTIAL_50PCT,
            reason=(
                f"제2원칙: ma20({ma20:.1f}) < price({current_price}) ≤ ma5({ma5:.1f}), "
                f"거래량 증가({current_volume:.0f} > {volume_ma20 * 1.5:.0f}) + 음봉 — 50% 매도"
            ),
        )

    return None


def evaluate_sell(
    current_price: float,
    ma5: float,
    ma20: float,
    candles: list[Candle],
    current_volume: int,
    volume_ma20: float,
) -> BbcSellSignal | None:
    """매도 원칙 순서대로 평가하여 첫 번째 충족 원칙 반환.

    1원칙 → 2원칙 순서로 확인.

    Args:
        current_price: 현재가.
        ma5: 5일 이동평균.
        ma20: 20일 이동평균.
        candles: 캔들 리스트.
        current_volume: 현재 거래량.
        volume_ma20: 거래량 20기간 이동평균.

    Returns:
        가장 먼저 충족된 BbcSellSignal or None.
    """
    signal = check_sell_principle_1(
        current_price=current_price,
        ma5=ma5,
        ma20=ma20,
        candles=candles,
        current_volume=current_volume,
        volume_ma20=volume_ma20,
    )
    if signal:
        return signal

    return check_sell_principle_2(
        current_price=current_price,
        ma5=ma5,
        ma20=ma20,
        candles=candles,
        current_volume=current_volume,
        volume_ma20=volume_ma20,
    )
