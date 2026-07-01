"""박병창 매수 3원칙 구현.

3원칙:
  1원칙: 5일선 위 (급등주 매수) — price > ma5
  2원칙: 눌림목 (5일선과 20일선 사이) — ma20 <= price <= ma5
  3원칙: 20일선 아래 (급락 저점) — price < ma20

스펙 참고: specs/trading-strategy.md 3절
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time
from enum import StrEnum
from typing import Literal

from core.marketdata.models import Candle
from core.strategy.indicators.ma import CandleClass, classify_candle

logger = logging.getLogger(__name__)


# ============================================================================
# 타입 정의
# ============================================================================


class EntryTime(StrEnum):
    """매수 타이밍 구분."""

    MORNING = "morning"      # 오전 10:00 이전
    AFTERNOON = "afternoon"  # 오후 14:00 이후


@dataclass(frozen=True)
class BbcBuySignal:
    """박병창 매수 시그널.

    Attributes:
        principle: 매수 원칙 번호 (1, 2, 3).
        entry_time: 진입 타이밍 (morning / afternoon).
        reason: 시그널 근거 설명.
    """

    principle: Literal[1, 2, 3]
    entry_time: EntryTime
    reason: str

    def __post_init__(self) -> None:
        if self.principle not in (1, 2, 3):
            raise ValueError(f"principle must be 1, 2, or 3; got {self.principle}")


# ============================================================================
# 내부 헬퍼
# ============================================================================


def _get_peak_volume(candles: list[Candle]) -> float:
    """직전 상승 국면 최고 거래량 계산.

    최근 20봉 내 최고 거래량을 반환한다.
    20봉 미만이면 fallback으로 전체 캔들 내 최고 거래량 사용.

    Args:
        candles: 캔들 리스트 (오래된 것부터 최신 순).

    Returns:
        최고 거래량 (float). 캔들이 없으면 0.0.
    """
    if not candles:
        return 0.0

    window = candles[-20:] if len(candles) >= 20 else candles
    if len(candles) < 20:
        logger.warning(
            "bbc_buy: 캔들 수(%d) < 20, peak_volume fallback — 전체 캔들 내 최대 거래량 사용",
            len(candles),
        )
    return float(max(c.volume for c in window))


# ============================================================================
# 매수 원칙 판단 함수
# ============================================================================


def check_principle_1(
    current_price: float,
    ma5: float,
    current_time: time,
    prev_high: float,
    current_volume: int,
    volume_ma20: float,
    current_open: float,
) -> BbcBuySignal | None:
    """매수 제1원칙: 5일선 위 (급등주 매수).

    조건: price > ma5 (5일선 위에서 상승 중)

    오전 진입 (10:00 이전):
      - 시가 아래로 일시 하락 후 거래량 증가하며 시가 재돌파
      - 즉, current_price > current_open AND current_volume 증가

    오후 진입 (14:00 이후):
      - 장중 조정 마무리 후 거래량 증가하며 재상승
      - 즉, current_price > ma5 AND current_volume > volume_ma20 * 1.5

    제외 조건:
      - 오전 강세 → 10:00 이후 하락 전환 시 매수 제외 (10:00~14:00 구간)

    Args:
        current_price: 현재가.
        ma5: 5일 이동평균.
        current_time: 현재 시각.
        prev_high: 직전 봉 고가 (시가 재돌파 확인용).
        current_volume: 현재 거래량.
        volume_ma20: 거래량 20기간 이동평균.
        current_open: 당일 시가.

    Returns:
        BbcBuySignal or None.
    """
    if current_price <= ma5:
        return None

    morning_cutoff = time(10, 0, 0)
    afternoon_start = time(14, 0, 0)

    if current_time < morning_cutoff:
        # 오전: 시가 아래 하락 후 거래량 증가하며 재돌파
        volume_ok = current_volume > volume_ma20 * 1.5
        # 시가 재돌파 확인 (현재가 > 시가)
        retrace_and_recover = current_price > current_open
        if retrace_and_recover and volume_ok:
            return BbcBuySignal(
                principle=1,
                entry_time=EntryTime.MORNING,
                reason=f"제1원칙 오전: price({current_price}) > ma5({ma5:.1f}), 시가 재돌파 + 거래량 급증",
            )
        return None

    elif current_time >= afternoon_start:
        # 오후: 거래량 증가하며 재상승
        volume_ok = current_volume > volume_ma20 * 1.5
        if volume_ok:
            return BbcBuySignal(
                principle=1,
                entry_time=EntryTime.AFTERNOON,
                reason=f"제1원칙 오후: price({current_price}) > ma5({ma5:.1f}), 거래량 급증 재상승",
            )
        return None

    else:
        # 10:00~14:00: 오전 강세→하락 전환 구간 — 매수 제외
        logger.debug("bbc_buy: 10:00~14:00 구간, 제1원칙 매수 제외")
        return None


def check_principle_2(
    current_price: float,
    ma5: float,
    ma20: float,
    candles: list[Candle],
    volume_ma20: float,
    current_volume: int,
    current_time: time,
) -> BbcBuySignal | None:
    """매수 제2원칙: 눌림목 (5일선과 20일선 사이).

    조건 (모두 충족):
      1. ma20 <= price <= ma5 (눌림목 구간)
      2. 조정 구간 거래량 < peak_volume * 0.4 (거래량 급감)
      3. 하락폭이 직전 상승폭의 50% 이내
      4. 재상승일 거래량 급증(> volume_ma20 * 1.5) + 양봉

    금지: 거래량 증가 음봉

    Args:
        current_price: 현재가.
        ma5: 5일 이동평균.
        ma20: 20일 이동평균.
        candles: 캔들 리스트 (오래된 것부터 최신 순).
        volume_ma20: 거래량 20기간 이동평균.
        current_volume: 현재 거래량.
        current_time: 현재 시각.

    Returns:
        BbcBuySignal or None.
    """
    # 가격 위치 확인: 눌림목 구간 (20일선 위 포함, 5일선 아래)
    # ma20 == price 인 경우도 20일선 지지 눌림목으로 허용 (C1 경계값 버그 수정)
    if not (ma20 <= current_price <= ma5):
        return None

    if not candles or len(candles) < 2:
        return None

    latest = candles[-1]
    candle_class = classify_candle(latest.open, latest.close)

    # 금지 조건: 거래량 증가 음봉
    if candle_class == CandleClass.BEARISH and current_volume > volume_ma20 * 1.0:
        logger.debug("bbc_buy: 제2원칙 금지 — 거래량 증가 음봉")
        return None

    # 조정 구간 거래량 확인 (최근 3봉 평균 vs peak_volume)
    peak_vol = _get_peak_volume(candles)
    recent_avg_volume = (
        sum(c.volume for c in candles[-3:]) / min(3, len(candles))
        if candles
        else 0.0
    )
    volume_declined = recent_avg_volume < peak_vol * 0.4 if peak_vol > 0 else False

    # 재상승 거래량 급증 + 양봉
    volume_surge = current_volume > volume_ma20 * 1.5
    is_bullish = candle_class in (CandleClass.BULLISH, CandleClass.DOJI)

    if not (volume_surge and is_bullish):
        return None

    # 하락폭 50% 이내 확인 (최근 10봉 고점 대비)
    # 10봉 미만 시 로그 경고 후 가용 캔들로 계산 (신뢰도 감소)
    if len(candles) < 10:
        logger.warning(
            "bbc_buy: 제2원칙 캔들 수(%d) < 10, recent_high 신뢰도 낮음",
            len(candles),
        )
    recent_high = max(c.high for c in candles[-10:]) if candles else latest.high
    if recent_high <= 0:
        logger.error("bbc_buy: recent_high <= 0, 데이터 오류 — 제2원칙 거부")
        return None
    decline_ratio = (recent_high - current_price) / recent_high
    within_50pct = decline_ratio <= 0.5

    if not within_50pct:
        return None

    entry_time = EntryTime.MORNING if current_time < time(10, 0, 0) else EntryTime.AFTERNOON

    return BbcBuySignal(
        principle=2,
        entry_time=entry_time,
        reason=(
            f"제2원칙 눌림목: price({current_price}) between ma20({ma20:.1f})~ma5({ma5:.1f}), "
            f"거래량 급증({current_volume:.0f} > {volume_ma20 * 1.5:.0f}), 양봉/십자, "
            f"하락폭 {decline_ratio * 100:.1f}% (50% 이내)"
        ),
    )


def check_principle_3(
    current_price: float,
    ma20: float,
    candles: list[Candle],
    volume_ma20: float,
    current_volume: int,
) -> BbcBuySignal | None:
    """매수 제3원칙: 20일선 아래 (급락 후 저점 매수).

    조건:
      1. price < ma20
      2. 거래량이 최저 후 급증 (> volume_ma20 * 2.0)
      3. 양봉 또는 십자형

    금지:
      - 거래량 증가하며 하락하는 종목

    Args:
        current_price: 현재가.
        ma20: 20일 이동평균.
        candles: 캔들 리스트 (오래된 것부터 최신 순).
        volume_ma20: 거래량 20기간 이동평균.
        current_volume: 현재 거래량.

    Returns:
        BbcBuySignal or None.
    """
    if current_price >= ma20:
        return None

    if not candles:
        return None

    latest = candles[-1]
    candle_class = classify_candle(latest.open, latest.close)

    # 금지: 거래량 증가 하락
    if candle_class == CandleClass.BEARISH and current_volume > volume_ma20 * 1.0:
        logger.debug("bbc_buy: 제3원칙 금지 — 거래량 증가 하락")
        return None

    # 거래량 급증 (volume_ma20 * 2.0 초과) + 양봉/십자형
    volume_surge = current_volume > volume_ma20 * 2.0
    is_bullish_or_doji = candle_class in (CandleClass.BULLISH, CandleClass.DOJI)

    if not (volume_surge and is_bullish_or_doji):
        return None

    return BbcBuySignal(
        principle=3,
        entry_time=EntryTime.MORNING,  # 시간 무관, 거래량+캔들 조건 우선
        reason=(
            f"제3원칙 급락저점: price({current_price}) < ma20({ma20:.1f}), "
            f"거래량 폭증({current_volume:.0f} > {volume_ma20 * 2.0:.0f}), "
            f"{'양봉' if candle_class == CandleClass.BULLISH else '십자형'}"
        ),
    )


def evaluate_buy(
    current_price: float,
    ma5: float,
    ma20: float,
    current_volume: int,
    volume_ma20: float,
    candles: list[Candle],
    current_time: time,
    current_open: float,
) -> BbcBuySignal | None:
    """매수 원칙 순서대로 평가하여 첫 번째 충족 원칙 반환.

    1원칙 → 2원칙 → 3원칙 순서로 확인.

    Args:
        current_price: 현재가.
        ma5: 5일 이동평균.
        ma20: 20일 이동평균.
        current_volume: 현재 거래량.
        volume_ma20: 거래량 20기간 이동평균.
        candles: 캔들 리스트 (오래된 것부터 최신 순).
        current_time: 현재 시각.
        current_open: 당일 시가.

    Returns:
        가장 먼저 충족된 BbcBuySignal or None.
    """
    prev_high = candles[-1].high if candles else current_price

    signal = check_principle_1(
        current_price=current_price,
        ma5=ma5,
        current_time=current_time,
        prev_high=prev_high,
        current_volume=current_volume,
        volume_ma20=volume_ma20,
        current_open=current_open,
    )
    if signal:
        return signal

    signal = check_principle_2(
        current_price=current_price,
        ma5=ma5,
        ma20=ma20,
        candles=candles,
        volume_ma20=volume_ma20,
        current_volume=current_volume,
        current_time=current_time,
    )
    if signal:
        return signal

    return check_principle_3(
        current_price=current_price,
        ma20=ma20,
        candles=candles,
        volume_ma20=volume_ma20,
        current_volume=current_volume,
    )
