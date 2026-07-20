"""단일종목 레버리지/인버스 매매 전략 플러그인.

specs/trade.md 전체 로직(2장 진입·4장 청산·8장 상태 전이)을 구현한다.
5분봉 기준 단일종목 2배 레버리지/인버스 상품 스윙 매매.

동작 방식:
    지표(DEMA·CCI·Stochastic)는 기초자산(underlying_symbol)의 캔들로 계산하고,
    실제 주문은 레버리지 상품(long_symbol) 또는 인버스 상품(short_symbol)에 낸다.
    따라서 시세 폴링 대상에 기초자산 심볼도 포함되어 있어야 한다.

포지션 수량 추적:
    Strategy는 체결 확인(fill feedback)을 받지 않는 단방향 흐름이므로(base.py 참고),
    자신이 발행한 BUY/SELL 시그널을 근거로 보유 수량을 낙관적으로 추정한다.
    전량 청산 시에는 내부 추정치를 그대로 사용한다.

research-to-live parity:
    warmup()으로 기초자산의 과거 캔들을 로드해 지표 워밍업 상태를 맞춘 뒤
    on_tick()을 실행하면 백테스트와 라이브가 동일한 경로를 따른다.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, Signal, SignalSide
from core.strategy.indicators.cci import (
    calculate_cci,
    calculate_cci_signal,
    detect_dead_cross,
    detect_golden_cross,
)
from core.strategy.indicators.dema import (
    calculate_dema,
    detect_dema_slope_down,
    detect_dema_slope_up,
)
from core.strategy.indicators.ma import calculate_sma
from core.strategy.indicators.stochastic import calculate_stochastic_d, calculate_stochastic_k
from core.strategy.indicators.swing import recent_swing_high, recent_swing_low
from core.strategy.plugins.leverage_inverse_conditions import (
    LeverageInverseParams,
    assess_low_point,
    evaluate_inverse_entry,
    evaluate_leverage_entry,
)

logger = logging.getLogger(__name__)

# 지표 워밍업에 필요한 최소 캔들 수 (DEMA(60) 이중 EMA 수렴에 필요한 여유분 포함)
_MIN_CANDLES_FOR_INDICATORS = 3


class Phase(StrEnum):
    """포지션 상태 (spec 8장 상태 전이도)."""

    WATCHING = "watching"
    LEVERAGE_HOLDING = "leverage_holding"
    LEVERAGE_PARTIAL = "leverage_partial"
    INVERSE_HOLDING = "inverse_holding"
    INVERSE_PARTIAL = "inverse_partial"


class LeverageInverseStrategy:
    """단일종목 레버리지/인버스 매매 전략.

    Strategy(Protocol) 준수: on_tick(tick, ctx) -> Signal | None.

    Args:
        underlying_symbol: 지표 계산 기준 기초자산 심볼 (예: SK하이닉스 종목코드).
        long_symbol: 레버리지 상품 심볼.
        short_symbol: 인버스 상품 심볼.
        qty_per_unit: 진입 1회당 기본 수량.
        params: 전략 파라미터 (기본값: specs/trade.md 1장 기준값).
        name: 전략 식별자 (기본값 자동 생성).
    """

    def __init__(
        self,
        underlying_symbol: str,
        long_symbol: str,
        short_symbol: str,
        qty_per_unit: int = 10,
        params: LeverageInverseParams | None = None,
        name: str | None = None,
    ) -> None:
        self._underlying_symbol = underlying_symbol
        self._long_symbol = long_symbol
        self._short_symbol = short_symbol
        self._qty_per_unit = qty_per_unit
        self._params = params or LeverageInverseParams()
        self.name = name or f"leverage-inverse-{underlying_symbol}"

        self._phase = Phase.WATCHING
        self._position_qty = 0
        self._leverage_overbought_seen = False
        self._inverse_oversold_seen = False
        self._candle_history: list[Candle] = []

    # -----------------------------------------------------------------------
    # Strategy Protocol 구현
    # -----------------------------------------------------------------------

    def warmup(self, history: list[Candle]) -> None:
        """기초자산 과거 캔들로 내부 이력을 초기화한다."""
        self._candle_history = [c for c in history if c.symbol == self._underlying_symbol]
        logger.debug(
            "warmup: strategy=%s underlying=%s candles=%d",
            self.name,
            self._underlying_symbol,
            len(self._candle_history),
        )

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        """기초자산 틱 수신 시 지표를 계산하고 상태머신을 진행한다."""
        if tick.symbol != self._underlying_symbol:
            return None

        candles = list(ctx.recent_candles)
        if len(candles) < _MIN_CANDLES_FOR_INDICATORS:
            return None

        indicators = self._compute_indicators(candles)
        if indicators is None:
            return None
        dema, cci, cci_signal, stoch_d = indicators

        if self._phase == Phase.WATCHING:
            return self._try_entries(tick, candles, dema, cci, cci_signal, stoch_d)
        if self._phase in (Phase.LEVERAGE_HOLDING, Phase.LEVERAGE_PARTIAL):
            return self._manage_leverage_position(tick, candles, dema, cci, cci_signal, stoch_d)
        if self._phase in (Phase.INVERSE_HOLDING, Phase.INVERSE_PARTIAL):
            return self._manage_inverse_position(tick, candles, dema, cci, cci_signal, stoch_d)
        return None

    @property
    def phase(self) -> Phase:
        """현재 포지션 상태 (진단·테스트용)."""
        return self._phase

    @property
    def position_qty(self) -> int:
        """현재 추정 보유 수량 (진단·테스트용)."""
        return self._position_qty

    # -----------------------------------------------------------------------
    # 지표 계산
    # -----------------------------------------------------------------------

    def _compute_indicators(
        self, candles: list[Candle]
    ) -> tuple[list[float], list[float], list[float], list[float]] | None:
        """DEMA·CCI·CCI시그널·Stochastic %D를 계산한다.

        CCI와 CCI시그널은 동일 길이·동일 끝점으로 정렬해서 반환한다.

        Returns:
            (dema, cci_aligned, cci_signal, stoch_d) 튜플. 데이터 부족 시 None.
        """
        closes = [c.close for c in candles]
        dema = calculate_dema(closes, self._params.dema_period)

        cci_raw = calculate_cci(candles, self._params.cci_period)
        cci_signal = calculate_cci_signal(cci_raw, self._params.cci_signal_period)
        if not cci_signal:
            return None
        cci_aligned = cci_raw[-len(cci_signal) :]

        stoch_k = calculate_stochastic_k(candles, self._params.stochastic_k_period)
        stoch_d = calculate_stochastic_d(stoch_k, self._params.stochastic_d_period)

        if len(dema) < 3 or len(cci_aligned) < 2 or len(cci_signal) < 2 or not stoch_d:
            return None

        return dema, cci_aligned, cci_signal, stoch_d

    # -----------------------------------------------------------------------
    # 진입 (spec 2장·3장)
    # -----------------------------------------------------------------------

    def _try_entries(
        self,
        tick: Tick,
        candles: list[Candle],
        dema: list[float],
        cci: list[float],
        cci_signal: list[float],
        stoch_d: list[float],
    ) -> Signal | None:
        leverage_eval = evaluate_leverage_entry(
            dema, cci, cci_signal, candles, stoch_d, self._params
        )
        if leverage_eval.all_met:
            return self._enter_leverage(tick, leverage_eval.summary())

        inverse_eval = evaluate_inverse_entry(dema, cci, cci_signal, candles, stoch_d, self._params)
        if inverse_eval.all_met:
            return self._enter_inverse(tick, inverse_eval.summary())

        if leverage_eval.core_count == 2 or inverse_eval.core_count == 2:
            logger.debug(
                "on_tick: %s 관망(워치리스트) — 레버리지 2/3=%s 인버스 2/3=%s",
                self.name,
                leverage_eval.core_count == 2,
                inverse_eval.core_count == 2,
            )
        return None

    def _enter_leverage(self, tick: Tick, reason_detail: str) -> Signal:
        self._reset_position_state()
        self._phase = Phase.LEVERAGE_HOLDING
        self._position_qty = self._qty_per_unit
        reason = f"레버리지 진입 3-of-3 충족: {reason_detail}"
        logger.info(
            "BUY 시그널: %s %s qty=%d (%s)",
            self.name,
            self._long_symbol,
            self._position_qty,
            reason,
        )
        return Signal(
            strategy=self.name,
            symbol=self._long_symbol,
            side=SignalSide.BUY,
            qty=self._position_qty,
            price=None,
            reason=reason,
        )

    def _enter_inverse(self, tick: Tick, reason_detail: str) -> Signal:
        self._reset_position_state()
        self._phase = Phase.INVERSE_HOLDING
        self._position_qty = self._qty_per_unit
        reason = f"인버스 진입 3-of-3 충족: {reason_detail}"
        logger.info(
            "BUY 시그널: %s %s qty=%d (%s)",
            self.name,
            self._short_symbol,
            self._position_qty,
            reason,
        )
        return Signal(
            strategy=self.name,
            symbol=self._short_symbol,
            side=SignalSide.BUY,
            qty=self._position_qty,
            price=None,
            reason=reason,
        )

    def _reset_position_state(self) -> None:
        self._leverage_overbought_seen = False
        self._inverse_oversold_seen = False

    # -----------------------------------------------------------------------
    # 레버리지 보유 중 청산 (spec 4-1장)
    # -----------------------------------------------------------------------

    def _manage_leverage_position(
        self,
        tick: Tick,
        candles: list[Candle],
        dema: list[float],
        cci: list[float],
        cci_signal: list[float],
        stoch_d: list[float],
    ) -> Signal | None:
        confirm_count = 0
        reasons: list[str] = []

        if cci[-1] < 0:
            confirm_count += 1
            reasons.append("CCI 0선 이탈")

        if detect_dema_slope_down(dema):
            confirm_count += 1
            reasons.append("DEMA 기울기 하향 전환")

        swing_low = recent_swing_low(candles, self._params.swing_lookback)
        if swing_low is not None and candles[-1].close < dema[-1] and candles[-1].close < swing_low:
            confirm_count += 1
            reasons.append("가격 DEMA 하향돌파+저점이탈")

        if confirm_count >= 2:
            return self._exit_leverage_full(tick, "2차 확정청산(" + ",".join(reasons) + ")")

        if cci[-1] >= self._params.cci_overbought_warning:
            self._leverage_overbought_seen = True

        if (
            self._phase == Phase.LEVERAGE_HOLDING
            and self._leverage_overbought_seen
            and detect_dead_cross(cci, cci_signal)
        ):
            return self._exit_leverage_partial(
                tick, f"1차 경고: CCI 과열({cci[-1]:.1f}) 후 Signal 데드크로스"
            )

        return None

    def _exit_leverage_full(self, tick: Tick, reason: str) -> Signal:
        qty = self._position_qty if self._position_qty > 0 else self._qty_per_unit
        self._phase = Phase.WATCHING
        self._position_qty = 0
        self._leverage_overbought_seen = False
        logger.info("SELL 시그널: %s %s qty=%d (%s)", self.name, self._long_symbol, qty, reason)
        return Signal(
            strategy=self.name,
            symbol=self._long_symbol,
            side=SignalSide.SELL,
            qty=qty,
            price=None,
            reason=reason,
        )

    def _exit_leverage_partial(self, tick: Tick, reason: str) -> Signal:
        sell_qty = min(
            self._position_qty,
            max(1, round(self._position_qty * self._params.partial_exit_ratio)),
        )
        self._position_qty -= sell_qty
        self._phase = Phase.LEVERAGE_PARTIAL
        logger.info(
            "SELL(부분) 시그널: %s %s qty=%d (%s)", self.name, self._long_symbol, sell_qty, reason
        )
        return Signal(
            strategy=self.name,
            symbol=self._long_symbol,
            side=SignalSide.SELL,
            qty=sell_qty,
            price=None,
            reason=reason,
        )

    # -----------------------------------------------------------------------
    # 인버스 보유 중 청산 (spec 4-2장, 대칭)
    # -----------------------------------------------------------------------

    def _manage_inverse_position(
        self,
        tick: Tick,
        candles: list[Candle],
        dema: list[float],
        cci: list[float],
        cci_signal: list[float],
        stoch_d: list[float],
    ) -> Signal | None:
        confirm_count = 0
        reasons: list[str] = []

        if cci[-1] > 0:
            confirm_count += 1
            reasons.append("CCI 0선 상향돌파")

        if detect_dema_slope_up(dema):
            confirm_count += 1
            reasons.append("DEMA 기울기 우상향 전환")

        swing_high = recent_swing_high(candles, self._params.swing_lookback)
        if (
            swing_high is not None
            and candles[-1].close > dema[-1]
            and candles[-1].close > swing_high
        ):
            confirm_count += 1
            reasons.append("가격 DEMA 상향돌파+고점갱신")

        if confirm_count >= 2:
            volumes = [c.volume for c in candles]
            volume_ma = calculate_sma(volumes, 20)
            low_point = assess_low_point(candles, cci, stoch_d, volume_ma)
            reason = (
                "2차 확정청산(" + ",".join(reasons) + f") | 저점신뢰도={low_point.confidence}"
                f"({low_point.summary()})"
            )
            return self._exit_inverse_full(tick, reason)

        if cci[-1] <= self._params.cci_oversold_warning:
            self._inverse_oversold_seen = True

        if (
            self._phase == Phase.INVERSE_HOLDING
            and self._inverse_oversold_seen
            and detect_golden_cross(cci, cci_signal)
        ):
            return self._exit_inverse_partial(
                tick, f"1차 경고: CCI 과매도({cci[-1]:.1f}) 후 Signal 골든크로스"
            )

        return None

    def _exit_inverse_full(self, tick: Tick, reason: str) -> Signal:
        qty = self._position_qty if self._position_qty > 0 else self._qty_per_unit
        self._phase = Phase.WATCHING
        self._position_qty = 0
        self._inverse_oversold_seen = False
        logger.info("SELL 시그널: %s %s qty=%d (%s)", self.name, self._short_symbol, qty, reason)
        return Signal(
            strategy=self.name,
            symbol=self._short_symbol,
            side=SignalSide.SELL,
            qty=qty,
            price=None,
            reason=reason,
        )

    def _exit_inverse_partial(self, tick: Tick, reason: str) -> Signal:
        sell_qty = min(
            self._position_qty,
            max(1, round(self._position_qty * self._params.partial_exit_ratio)),
        )
        self._position_qty -= sell_qty
        self._phase = Phase.INVERSE_PARTIAL
        logger.info(
            "SELL(부분) 시그널: %s %s qty=%d (%s)", self.name, self._short_symbol, sell_qty, reason
        )
        return Signal(
            strategy=self.name,
            symbol=self._short_symbol,
            side=SignalSide.SELL,
            qty=sell_qty,
            price=None,
            reason=reason,
        )
