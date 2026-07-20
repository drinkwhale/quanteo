"""단일종목 레버리지/인버스 매매 — 진입 조건 판정 순수 함수 모음.

specs/trade.md 1장(파라미터)·2장(레버리지 진입)·3장(인버스 진입)·6장(저점 판단)의
판정 로직을 부작용 없는(side-effect free) 함수로 분리한다. 상태(포지션·페이즈)는
leverage_inverse_strategy.py의 LeverageInverseStrategy가 소유한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.marketdata.models import Candle
from core.strategy.indicators.cci import detect_dead_cross, detect_golden_cross
from core.strategy.indicators.dema import detect_dema_slope_down, detect_dema_slope_up
from core.strategy.indicators.stochastic import detect_stochastic_bottom_reversal
from core.strategy.indicators.swing import (
    detect_bullish_divergence,
    detect_capitulation_volume,
    detect_higher_low,
    recent_swing_high,
    recent_swing_low,
)

# ---------------------------------------------------------------------------
# 파라미터 (spec 1장)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeverageInverseParams:
    """단일종목 레버리지/인버스 전략 파라미터.

    기본값은 specs/trade.md 1장 YAML 기준값과 동일하다.

    Attributes:
        dema_period: DEMA 계산 기간.
        cci_period: CCI 계산 기간.
        cci_signal_period: CCI 시그널 라인 기간.
        stochastic_k_period: Stochastic %K 기간 (스펙 미명시 — 업계 표준 14 사용).
        stochastic_d_period: Stochastic %D 기간.
        stochastic_overbought: 레버리지 신규 진입 보류 기준.
        stochastic_oversold: 인버스 신규 진입 보류 기준.
        cci_overbought_warning: 레버리지 1차 경고(부분 익절) CCI 기준.
        cci_overbought_extreme: CCI 참고용 상한.
        cci_oversold_warning: 인버스 1차 경고(부분 익절) CCI 기준.
        cci_oversold_extreme: CCI 참고용 하한.
        swing_lookback: 직전 고점/저점 탐색 구간(N봉).
        partial_exit_ratio: 1차 경고 시 부분 익절 비율 (스펙 1/3~1/2 범위의 중간값).
        max_allocation_pct: 참고용 계좌 대비 최대 비중 — 실제 수량은 Risk Manager가 결정.
    """

    dema_period: int = 60
    cci_period: int = 20
    cci_signal_period: int = 10
    stochastic_k_period: int = 14
    stochastic_d_period: int = 3
    stochastic_overbought: float = 80.0
    stochastic_oversold: float = 20.0
    cci_overbought_warning: float = 150.0
    cci_overbought_extreme: float = 200.0
    cci_oversold_warning: float = -150.0
    cci_oversold_extreme: float = -200.0
    swing_lookback: int = 10
    partial_exit_ratio: float = 0.4
    max_allocation_pct: float = 10.0

    def __post_init__(self) -> None:
        """파라미터 조합 유효성 검증.

        백테스트로 임계값을 재검증하는 과정에서 값이 자주 바뀌므로(spec 9장),
        잘못된 조합이 조용히 통과해 이상 시그널을 내지 않도록 생성 시점에 막는다.
        """
        if self.dema_period < 3:
            raise ValueError(f"dema_period는 3 이상이어야 합니다: {self.dema_period}")
        if self.cci_period < 2:
            raise ValueError(f"cci_period는 2 이상이어야 합니다: {self.cci_period}")
        if self.cci_signal_period < 2:
            raise ValueError(
                f"cci_signal_period는 2 이상이어야 합니다: {self.cci_signal_period}"
            )
        if self.stochastic_k_period < 2:
            raise ValueError(
                f"stochastic_k_period는 2 이상이어야 합니다: {self.stochastic_k_period}"
            )
        if self.stochastic_d_period < 1:
            raise ValueError(
                f"stochastic_d_period는 1 이상이어야 합니다: {self.stochastic_d_period}"
            )
        if self.swing_lookback < 1:
            raise ValueError(f"swing_lookback는 1 이상이어야 합니다: {self.swing_lookback}")
        if not (0.0 < self.partial_exit_ratio < 1.0):
            raise ValueError(
                f"partial_exit_ratio는 0과 1 사이여야 합니다: {self.partial_exit_ratio}"
            )
        if not (0.0 < self.max_allocation_pct <= 100.0):
            raise ValueError(
                f"max_allocation_pct는 0과 100 사이여야 합니다: {self.max_allocation_pct}"
            )
        if not (0.0 < self.stochastic_oversold < self.stochastic_overbought <= 100.0):
            raise ValueError(
                "stochastic_oversold < stochastic_overbought <= 100 이어야 합니다: "
                f"oversold={self.stochastic_oversold}, overbought={self.stochastic_overbought}"
            )
        if not (
            self.cci_oversold_extreme
            < self.cci_oversold_warning
            < 0
            < self.cci_overbought_warning
            < self.cci_overbought_extreme
        ):
            raise ValueError(
                "cci_oversold_extreme < cci_oversold_warning < 0 < "
                "cci_overbought_warning < cci_overbought_extreme 이어야 합니다: "
                f"oversold_extreme={self.cci_oversold_extreme}, "
                f"oversold_warning={self.cci_oversold_warning}, "
                f"overbought_warning={self.cci_overbought_warning}, "
                f"overbought_extreme={self.cci_overbought_extreme}"
            )


# ---------------------------------------------------------------------------
# 진입 조건 평가 결과
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntryEvaluation:
    """3-of-3 진입 조건 평가 결과.

    Attributes:
        dema_slope_ok: DEMA 기울기 전환 조건 충족 여부.
        cci_cross_ok: CCI 0선 돌파/시그널 크로스 조건 충족 여부.
        price_break_ok: 가격 DEMA 돌파 + 고점/저점 갱신 조건 충족 여부.
        stoch_filter_ok: Stochastic 진입 필터(거부 조건 미해당) 통과 여부.
    """

    dema_slope_ok: bool
    cci_cross_ok: bool
    price_break_ok: bool
    stoch_filter_ok: bool

    @property
    def core_count(self) -> int:
        """핵심 3조건(필터 제외) 중 충족 개수 — spec의 "2개만 충족 시 관망" 판정용."""
        return sum([self.dema_slope_ok, self.cci_cross_ok, self.price_break_ok])

    @property
    def all_met(self) -> bool:
        """3-of-3 + 필터 통과 시에만 True (신규 진입 가능)."""
        return self.core_count == 3 and self.stoch_filter_ok

    def summary(self) -> str:
        """진입 근거 요약 (시그널 reason·로그용)."""
        labels = {
            "DEMA기울기전환": self.dema_slope_ok,
            "CCI크로스": self.cci_cross_ok,
            "가격돌파": self.price_break_ok,
        }
        parts = [name for name, ok in labels.items() if ok]
        return "+".join(parts) if parts else "없음"


def evaluate_leverage_entry(
    dema: list[float],
    cci: list[float],
    cci_signal: list[float],
    candles: list[Candle],
    stoch_d: list[float],
    params: LeverageInverseParams,
) -> EntryEvaluation:
    """레버리지(롱) 진입 3-of-3 조건 평가 (spec 2장).

    cci와 cci_signal은 동일 길이·동일 끝점(최신 시점)으로 정렬되어 있어야 한다.

    Args:
        dema: DEMA 값 리스트.
        cci: CCI 값 리스트.
        cci_signal: CCI 시그널 라인 값 리스트.
        candles: Candle 리스트 (오래된 것부터 최신 순).
        stoch_d: Stochastic %D 값 리스트.
        params: 전략 파라미터.

    Returns:
        EntryEvaluation.
    """
    dema_ok = detect_dema_slope_up(dema)

    cci_ok = False
    if len(cci) >= 2 and len(cci_signal) >= 2:
        zero_cross_up = cci[-2] <= 0 and cci[-1] > 0
        signal_golden_cross = detect_golden_cross(cci, cci_signal) and cci[-1] > 0
        cci_ok = zero_cross_up or signal_golden_cross

    price_ok = False
    swing_high = recent_swing_high(candles, params.swing_lookback)
    if swing_high is not None and dema and candles:
        price_ok = candles[-1].close > dema[-1] and candles[-1].close > swing_high

    stoch_ok = bool(stoch_d) and stoch_d[-1] < params.stochastic_overbought

    return EntryEvaluation(dema_ok, cci_ok, price_ok, stoch_ok)


def evaluate_inverse_entry(
    dema: list[float],
    cci: list[float],
    cci_signal: list[float],
    candles: list[Candle],
    stoch_d: list[float],
    params: LeverageInverseParams,
) -> EntryEvaluation:
    """인버스(숏 대체) 진입 3-of-3 조건 평가 (spec 3장, 2장과 대칭).

    Args:
        dema: DEMA 값 리스트.
        cci: CCI 값 리스트.
        cci_signal: CCI 시그널 라인 값 리스트.
        candles: Candle 리스트 (오래된 것부터 최신 순).
        stoch_d: Stochastic %D 값 리스트.
        params: 전략 파라미터.

    Returns:
        EntryEvaluation.
    """
    dema_ok = detect_dema_slope_down(dema)

    cci_ok = False
    if len(cci) >= 2 and len(cci_signal) >= 2:
        zero_cross_down = cci[-2] >= 0 and cci[-1] < 0
        signal_dead_cross = detect_dead_cross(cci, cci_signal) and cci[-1] < 0
        cci_ok = zero_cross_down or signal_dead_cross

    price_ok = False
    swing_low = recent_swing_low(candles, params.swing_lookback)
    if swing_low is not None and dema and candles:
        price_ok = candles[-1].close < dema[-1] and candles[-1].close < swing_low

    stoch_ok = bool(stoch_d) and stoch_d[-1] > params.stochastic_oversold

    return EntryEvaluation(dema_ok, cci_ok, price_ok, stoch_ok)


# ---------------------------------------------------------------------------
# 저점 판단 (spec 6장) — 신뢰도 보강용
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LowPointAssessment:
    """저점(바닥) 신뢰도 평가 (spec 6장).

    단일 신호로 판단하지 않고 최소 2개 이상 동시 충족 시에만 "강한 신호"로 인정한다.

    Attributes:
        higher_low: 스윙 로우 구조 전환(Higher Low) 여부.
        bullish_divergence: 강세 다이버전스 여부.
        stochastic_reversal: Stochastic %D 반등 여부.
        capitulation_volume: 거래량 동반 투매 후 반등 캔들 패턴 여부.
    """

    higher_low: bool
    bullish_divergence: bool
    stochastic_reversal: bool
    capitulation_volume: bool

    @property
    def signal_count(self) -> int:
        return sum(
            [
                self.higher_low,
                self.bullish_divergence,
                self.stochastic_reversal,
                self.capitulation_volume,
            ]
        )

    @property
    def confidence(self) -> Literal["none", "weak", "strong"]:
        """spec 6장: ①+② 또는 ①②③ 조합 등 2개 이상 = 강한 신호, ③만 = 약한 신호."""
        if self.signal_count >= 2:
            return "strong"
        if self.signal_count == 1:
            return "weak"
        return "none"

    def summary(self) -> str:
        labels = {
            "HigherLow": self.higher_low,
            "강세다이버전스": self.bullish_divergence,
            "Stoch반등": self.stochastic_reversal,
            "거래량동반": self.capitulation_volume,
        }
        parts = [name for name, ok in labels.items() if ok]
        return "+".join(parts) if parts else "없음"


def assess_low_point(
    candles: list[Candle],
    oscillator: list[float],
    stoch_d: list[float],
    volume_ma: list[float],
    lookback: int = 10,
) -> LowPointAssessment:
    """저점 신뢰도 종합 평가 (spec 6장).

    Args:
        candles: Candle 리스트 (오래된 것부터 최신 순).
        oscillator: 다이버전스 비교용 오실레이터 값 리스트 (보통 CCI).
        stoch_d: Stochastic %D 값 리스트.
        volume_ma: 거래량 이동평균 리스트.
        lookback: 다이버전스 비교 구간 (기본값: 10).

    Returns:
        LowPointAssessment.
    """
    return LowPointAssessment(
        higher_low=detect_higher_low(candles),
        bullish_divergence=detect_bullish_divergence(candles, oscillator, lookback),
        stochastic_reversal=detect_stochastic_bottom_reversal(stoch_d),
        capitulation_volume=detect_capitulation_volume(candles, volume_ma),
    )
