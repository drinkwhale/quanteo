"""CCI + 박병창 통합 전략 플러그인.

신뢰도 스코어링:
  +1: 월봉 CCI 골든크로스
  +1: 주봉 CCI 골든크로스
  +2: 일봉 CCI 골든크로스 (가중치 2배)
  +1: 60분봉 CCI 골든크로스
  +1: 거래량 volume_ma20 대비 1.5배 이상
  +1: 장중 유형 ① 또는 ③번
  +1: 이동평균선 정배열 (ma5 > ma20)
  -2: 일봉 CCI 데드크로스
  -1: 45도 각도 하락 패턴
  -2: ④번 유형 발생
  → 7점 이상 적극매수 / 4~6 소극매수 / 0~3 관망 / 음수 매도검토

4단계 매수 의사결정 트리:
  1단계(월봉 CCI) → 2단계(주봉 CCI) → 3단계(일봉+BBC) → 4단계(60분봉+장중유형+거래량)

Strategy(Protocol) 준수:
  on_tick(tick: Tick, ctx: MarketContext) -> Signal | None

스펙 참고: specs/trading-strategy.md 8절
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import time, timedelta, timezone
from typing import Literal

_KST = timezone(timedelta(hours=9))  # 한국 표준시

from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, Signal, SignalSide
from core.strategy.indicators.cci import (
    detect_dead_cross,
    detect_golden_cross,
)
from core.strategy.indicators.ma import (
    CandleClass,
    classify_candle,
    is_alignment_bullish,
    price_position,
)
from core.strategy.indicators.ma import PricePosition
from core.strategy.multi_timeframe import MultiTimeframeData
from core.strategy.plugins.bbc_buy import BbcBuySignal, evaluate_buy
from core.strategy.plugins.bbc_sell import SellAction, detect_45_degree_decline, evaluate_sell
from core.strategy.plugins.intraday_signal import (
    ConfirmedSignal,
    IntradaySignalType,
    UnconfirmedSignal,
    detect_intraday_signal,
)
from core.strategy.timeframe_judge import MarketDirection, TimeframeJudge

logger = logging.getLogger(__name__)


# ============================================================================
# 신뢰도 스코어
# ============================================================================

_ACTION_MAP: dict[str, Literal["적극매수", "소극매수", "관망", "매도검토"]] = {
    "aggressive": "적극매수",
    "conservative": "소극매수",
    "wait": "관망",
    "sell": "매도검토",
}


@dataclass(frozen=True)
class ReliabilityScore:
    """신뢰도 스코어.

    Attributes:
        score: 총 점수 (음수 가능).
        breakdown: 항목별 점수 내역.
        action: 점수 기반 행동 지침 (from_breakdown으로 생성 시 score와 일관성 보장).
    """

    score: int
    breakdown: dict[str, int]
    action: Literal["적극매수", "소극매수", "관망", "매도검토"]

    def __post_init__(self) -> None:
        """action이 score와 일관된지 검증한다 (직접 생성 시 모순 방지)."""
        expected = self._compute_action(self.score)
        if self.action != expected:
            raise ValueError(
                f"action={self.action!r}이 score={self.score}와 불일치; "
                f"expected {expected!r}"
            )

    @staticmethod
    def _compute_action(score: int) -> Literal["적극매수", "소극매수", "관망", "매도검토"]:
        if score >= 7:
            return "적극매수"
        elif score >= 4:
            return "소극매수"
        elif score >= 0:
            return "관망"
        else:
            return "매도검토"

    @classmethod
    def from_breakdown(cls, breakdown: dict[str, int]) -> "ReliabilityScore":
        """breakdown dict에서 ReliabilityScore 생성."""
        score = sum(breakdown.values())
        action = cls._compute_action(score)
        return cls(score=score, breakdown=breakdown, action=action)


# ============================================================================
# 포지션 크기 계산
# ============================================================================


def calculate_position_size(score: int) -> float:
    """신뢰도 스코어 기반 포지션 크기 비율 계산.

    Args:
        score: 신뢰도 점수.

    Returns:
        포지션 비율 (0.0 ~ 1.0). score < 0 또는 관망(0~3점)이면 0.0 반환.
    """
    if score < 0:
        return 0.0
    if score >= 7:
        return 0.30   # 적극매수: 30%
    elif score >= 4:
        return 0.10   # 소극매수: 10%
    else:
        return 0.0    # 관망


# ============================================================================
# 신뢰도 스코어링 계산
# ============================================================================


def compute_reliability_score(
    mtf_directions: dict[str, MarketDirection],
    daily_cci: list[float],
    daily_signal: list[float],
    current_volume: int,
    volume_ma20: float,
    ma5: float,
    ma20: float,
    intraday_type: IntradaySignalType,
    has_45deg_decline: bool,
) -> ReliabilityScore:
    """신뢰도 스코어 계산.

    스펙 8.3절 기준 양성 최대 8점.

    Args:
        mtf_directions: TimeframeJudge.assess() 반환값.
        daily_cci: 일봉 CCI 값 리스트.
        daily_signal: 일봉 CCI 시그널 리스트.
        current_volume: 현재 거래량.
        volume_ma20: 거래량 20기간 이동평균.
        ma5: 5일 이동평균.
        ma20: 20일 이동평균.
        intraday_type: 장중 시그널 유형.
        has_45deg_decline: 45도 하락 패턴 여부.

    Returns:
        ReliabilityScore.
    """
    breakdown: dict[str, int] = {}

    # +1: 월봉 CCI 골든크로스
    if mtf_directions.get("monthly") == MarketDirection.BULLISH:
        breakdown["monthly_gc"] = 1

    # +1: 주봉 CCI 골든크로스
    if mtf_directions.get("weekly") == MarketDirection.BULLISH:
        breakdown["weekly_gc"] = 1

    # +2/-2: 일봉 CCI 골든크로스/데드크로스 (상호 배타적)
    if len(daily_cci) >= 2 and len(daily_signal) >= 2:
        if detect_golden_cross(daily_cci, daily_signal):
            breakdown["daily_gc"] = 2
        elif detect_dead_cross(daily_cci, daily_signal):
            breakdown["daily_dc"] = -2

    # +1: 60분봉 CCI 골든크로스
    if mtf_directions.get("sixty_min") == MarketDirection.BULLISH:
        breakdown["sixty_min_gc"] = 1

    # +1: 거래량 volume_ma20 대비 1.5배 이상
    if volume_ma20 > 0 and current_volume > volume_ma20 * 1.5:
        breakdown["volume_surge"] = 1

    # +1: 장중 유형 ① 또는 ③번
    if intraday_type in (IntradaySignalType.TYPE_1, IntradaySignalType.TYPE_3):
        breakdown["intraday_positive"] = 1

    # +1: 정배열 (ma5 > ma20)
    if is_alignment_bullish(ma5, ma20):
        breakdown["alignment"] = 1

    # -1: 45도 각도 하락 패턴
    if has_45deg_decline:
        breakdown["decline_45deg"] = -1

    # -2: ④번 유형
    if intraday_type == IntradaySignalType.TYPE_4:
        breakdown["intraday_type4"] = -2

    return ReliabilityScore.from_breakdown(breakdown)


# ============================================================================
# BBC 통합 전략 플러그인
# ============================================================================


class CciBbcStrategy:
    """CCI + 박병창 통합 전략 플러그인.

    T011 Strategy(Protocol) 인터페이스를 준수한다.

    Args:
        symbol: 대상 종목 코드.
        mtf_data: MultiTimeframeData (4개 타임프레임 상태). None이면 지표 계산 생략.
        qty_per_unit: 기본 매매 단위 (주문 수량 계산 기준).
        name: 전략 식별자.
    """

    def __init__(
        self,
        symbol: str,
        mtf_data: MultiTimeframeData | None = None,
        qty_per_unit: int = 1,
        name: str | None = None,
    ) -> None:
        self._symbol = symbol
        self._mtf_data = mtf_data
        self._qty_per_unit = qty_per_unit
        self.name = name or f"cci-bbc-{symbol}"
        self._judge = TimeframeJudge()
        self._candle_history: list[Candle] = []
        self._available_capital: float = 0.0

    # -----------------------------------------------------------------------
    # Strategy Protocol 구현
    # -----------------------------------------------------------------------

    def warmup(self, history: list[Candle]) -> None:
        """과거 캔들로 내부 상태를 초기화한다."""
        self._candle_history = [c for c in history if c.symbol == self._symbol]
        logger.debug(
            "warmup: strategy=%s candles=%d",
            self.name,
            len(self._candle_history),
        )

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        """틱 수신 시 매매 조건을 평가하여 시그널을 생성한다.

        1단계(월봉) → 2단계(주봉) → 3단계(일봉+BBC) → 4단계(60분봉+장중) 순서.

        Args:
            tick: 수신된 틱.
            ctx: 최근 캔들 컨텍스트.

        Returns:
            Signal or None.
        """
        if tick.symbol != self._symbol:
            return None

        candles = list(ctx.recent_candles)
        if not candles:
            return None

        # ── 헤드앤숄더 하락전환 override (스코어 무관 즉시 전량 매도) ──
        from core.strategy.indicators.head_shoulders import detect_head_shoulders
        hs_result = detect_head_shoulders(candles)
        if hs_result is not None and hs_result.pattern_type == "하락전환" and hs_result.volume_confirms:
            logger.info(
                "헤드앤숄더 하락전환 감지 — 즉시 전량 매도 override (symbol=%s, neckline=%.0f)",
                tick.symbol, hs_result.neckline,
            )
            return Signal(
                strategy=self.name,
                symbol=tick.symbol,
                side=SignalSide.SELL,
                qty=9999,  # Risk Manager가 보유 수량으로 조정
                price=tick.price,
                reason=f"헤드앤숄더 하락전환 override (넥라인={hs_result.neckline:.0f})",
            )

        # 타임프레임 방향 판단
        if self._mtf_data is None:
            logger.debug("on_tick: MTF 데이터 없음, 시그널 생략")
            return None

        directions = self._judge.assess(self._mtf_data)

        # 1단계: 월봉 BULLISH 여부 (거래 가능 조건)
        if not self._judge.is_trade_allowed(directions):
            logger.debug("on_tick: 월봉 BEARISH/NEUTRAL — 거래 금지")
            return None

        # 지표 추출
        daily_state = self._mtf_data.daily
        if not daily_state.candles:
            return None

        ma5_val = daily_state.ma5[-1] if daily_state.ma5 else 0.0
        ma20_val = daily_state.ma20[-1] if daily_state.ma20 else 0.0
        volume_ma20 = daily_state.volume_ma20[-1] if daily_state.volume_ma20 else 0.0
        current_volume = tick.volume

        # 틱 타임스탬프를 KST로 변환하여 장중 시각 판단 (look-ahead bias 방지)
        current_time = tick.timestamp.astimezone(_KST).time()

        # 장중 시그널 감지 (실제 틱 시각 기준)
        intraday_result = detect_intraday_signal(
            candles=candles,
            open_price=candles[0].open if candles else tick.price,
            current_time=current_time,
            volume_ma20=volume_ma20,
        )
        intraday_type = intraday_result.signal_type

        # 45도 하락 패턴 감지 (12봉 이상일 때만 — 적은 데이터에서 오탐 방지)
        if len(candles) >= 12:
            has_45deg = detect_45_degree_decline(candles, window=12)
        else:
            logger.debug("on_tick: 캔들 수(%d) < 12, 45도 하락 감지 생략", len(candles))
            has_45deg = False

        # 신뢰도 스코어 계산
        score_obj = compute_reliability_score(
            mtf_directions=directions,
            daily_cci=daily_state.cci,
            daily_signal=daily_state.cci_signal,
            current_volume=current_volume,
            volume_ma20=volume_ma20,
            ma5=ma5_val,
            ma20=ma20_val,
            intraday_type=intraday_type,
            has_45deg_decline=has_45deg,
        )

        # 즉시 전량 매도 조건 확인
        sell_signal = self._check_immediate_sell(
            tick=tick,
            candles=candles,
            ma5=ma5_val,
            ma20=ma20_val,
            volume_ma20=volume_ma20,
            current_volume=current_volume,
            intraday_type=intraday_type,
            has_45deg=has_45deg,
            daily_cci=daily_state.cci,
            daily_signal_vals=daily_state.cci_signal,
        )
        if sell_signal:
            return sell_signal

        # 매도 검토 (score < 0 또는 BBC 매도 원칙)
        if score_obj.score < 0:
            bbc_sell = evaluate_sell(
                current_price=tick.price,
                ma5=ma5_val,
                ma20=ma20_val,
                candles=candles,
                current_volume=current_volume,
                volume_ma20=volume_ma20,
            )
            if bbc_sell:
                qty = self._qty_from_action(bbc_sell.action)
                return self._to_sell_signal(tick, bbc_sell.reason, qty)

        # 4단계: 매수 조건 평가
        if score_obj.score < 0:
            return None

        position_ratio = calculate_position_size(score_obj.score)
        if position_ratio <= 0:
            return None

        # 2단계: 주봉 확인
        if directions.get("weekly") != MarketDirection.BULLISH:
            logger.debug("on_tick: 주봉 비강세 — 소극 매수만 허용")

        # 3단계: 일봉 CCI + BBC 매수 원칙 (실제 시각 전달)
        bbc_buy = self._check_bbc_buy(tick, candles, ma5_val, ma20_val, volume_ma20, current_volume, current_time)
        if bbc_buy is None:
            return None

        # 4단계: 60분봉 + 장중유형 + 거래량 (스코어로 이미 반영)
        if intraday_type == IntradaySignalType.TYPE_4:
            logger.debug("on_tick: TYPE_4 발생 — 매수 금지")
            return None

        qty = max(1, round(self._qty_per_unit * position_ratio * 10))
        return self._to_buy_signal(tick, bbc_buy, qty, score_obj)

    # -----------------------------------------------------------------------
    # 내부 헬퍼
    # -----------------------------------------------------------------------

    def _check_immediate_sell(
        self,
        tick: Tick,
        candles: list[Candle],
        ma5: float,
        ma20: float,
        volume_ma20: float,
        current_volume: int,
        intraday_type: IntradaySignalType,
        has_45deg: bool,
        daily_cci: list[float],
        daily_signal_vals: list[float],
    ) -> Signal | None:
        """즉시 전량 매도 조건 확인 (OR 조건).

        즉시 전량 매도:
          - 45도 각도 점진적 하락 패턴
          - price < ma5 AND price < ma20
          - 20일선 근처에서 ④번 유형
          - 일봉 CCI가 +100 이상에서 데드크로스 + ②번 유형 동시 발생

        Args:
            tick: 수신된 틱.
            candles: 최근 캔들.
            ma5, ma20, volume_ma20, current_volume: 지표값.
            intraday_type: 장중 시그널 유형.
            has_45deg: 45도 하락 패턴 여부.
            daily_cci, daily_signal_vals: 일봉 CCI 및 시그널.

        Returns:
            SELL Signal or None.
        """
        price = tick.price

        if has_45deg:
            return self._to_sell_signal(tick, "즉시전량매도: 45도 완만 지속 하락 패턴", self._qty_per_unit)

        if price < ma5 and price < ma20:
            return self._to_sell_signal(tick, f"즉시전량매도: price({price}) < ma5({ma5:.0f}) AND ma20({ma20:.0f})", self._qty_per_unit)

        if intraday_type == IntradaySignalType.TYPE_4 and price < ma20 * 1.02:
            return self._to_sell_signal(tick, "즉시전량매도: 20일선 근처 ④번 유형", self._qty_per_unit)

        if (
            len(daily_cci) >= 2
            and len(daily_signal_vals) >= 2
            and detect_dead_cross(daily_cci, daily_signal_vals)
            and daily_cci[-1] >= 100
            and intraday_type == IntradaySignalType.TYPE_2
        ):
            return self._to_sell_signal(tick, "즉시전량매도: 일봉 CCI +100 이상 데드크로스 + ②번 유형", self._qty_per_unit)

        return None

    def _check_bbc_buy(
        self,
        tick: Tick,
        candles: list[Candle],
        ma5: float,
        ma20: float,
        volume_ma20: float,
        current_volume: int,
        current_time: time,
    ) -> BbcBuySignal | None:
        """일봉 CCI 조건 + BBC 매수 원칙 통합 확인."""
        return evaluate_buy(
            current_price=tick.price,
            ma5=ma5,
            ma20=ma20,
            current_volume=current_volume,
            volume_ma20=volume_ma20,
            candles=candles,
            current_time=current_time,
            current_open=candles[0].open if candles else tick.price,
        )

    def _qty_from_action(self, action: SellAction) -> int:
        """SellAction → 수량 변환 (비율은 Risk Manager가 처리)."""
        return self._qty_per_unit

    def _to_buy_signal(
        self,
        tick: Tick,
        bbc_buy: BbcBuySignal,
        qty: int,
        score: ReliabilityScore,
    ) -> Signal:
        """BBC 매수 시그널 → Strategy Signal 변환."""
        reason = f"[BBC 매수 제{bbc_buy.principle}원칙] {bbc_buy.reason} | 스코어={score.score} ({score.action})"
        logger.info("BUY 시그널: %s %s qty=%d (%s)", self.name, tick.symbol, qty, reason)
        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=SignalSide.BUY,
            qty=qty,
            price=tick.price,
            reason=reason,
        )

    def _to_sell_signal(self, tick: Tick, reason: str, qty: int) -> Signal:
        """매도 시그널 생성."""
        logger.info("SELL 시그널: %s %s qty=%d (%s)", self.name, tick.symbol, qty, reason)
        return Signal(
            strategy=self.name,
            symbol=tick.symbol,
            side=SignalSide.SELL,
            qty=qty,
            price=tick.price,
            reason=reason,
        )
