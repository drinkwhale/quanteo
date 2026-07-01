"""백테스트 엔진.

일봉 기준 시뮬레이션 루프, 미래참조 방지, 수수료·슬리피지 반영,
분할 매수/매도 포지션 비율 관리를 담당한다.

T077 구현.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, Signal, SignalSide

if TYPE_CHECKING:
    from core.backtest.toss_data_source import BacktestDataSource
    from core.strategy.base import Strategy
    from core.strategy.multi_timeframe import MultiTimeframeData

logger = logging.getLogger(__name__)


# ============================================================================
# Trade: 체결 기록
# ============================================================================


@dataclass(frozen=True)
class Trade:
    """백테스트 중 발생한 체결 기록.

    Attributes:
        symbol: 종목 코드.
        side: 매수(BUY) / 매도(SELL).
        price: 체결 단가 (슬리피지 적용 후).
        qty: 체결 수량.
        commission: 수수료 (원화).
        tax: 증권거래세 (원화, 매도만 발생).
        timestamp: 체결 일자.
        signal: 시그널 발생 일자 (체결일 전일).
    """

    symbol: str
    side: SignalSide
    price: float
    qty: int
    commission: float
    tax: float
    timestamp: datetime
    signal_timestamp: datetime

    @property
    def net_amount(self) -> float:
        """실질 거래금액 (매수: 음수, 매도: 양수)."""
        gross = self.price * self.qty
        if self.side == SignalSide.BUY:
            return -(gross + self.commission)
        return gross - self.commission - self.tax


# ============================================================================
# PerformanceMetrics: 성과 지표 (metrics.py에서 채움)
# ============================================================================


@dataclass
class PerformanceMetrics:
    """백테스트 성과 지표.

    metrics.py가 BacktestResult를 받아 채운다.
    """

    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    mdd: float = 0.0
    sharpe_ratio: float = 0.0
    total_trades: int = 0
    annualized_return: float = 0.0


# ============================================================================
# BacktestResult
# ============================================================================


@dataclass
class BacktestResult:
    """백테스트 결과.

    Attributes:
        trades: 체결 기록 목록.
        equity_curve: 일자별 자산 가치 (원화).
        metrics: 성과 지표 (후처리 후 채움).
        unfilled_signals: 마지막 봉 이후 다음 봉 없어 미체결된 시그널.
        initial_capital: 초기 자본금.
    """

    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    unfilled_signals: list[Signal] = field(default_factory=list)
    initial_capital: float = 10_000_000.0


# ============================================================================
# 포지션 추적
# ============================================================================


@dataclass
class _Position:
    """보유 포지션 내부 추적."""

    symbol: str
    qty: int = 0
    avg_price: float = 0.0

    def update_buy(self, qty: int, price: float) -> None:
        """매수 체결로 평균단가 갱신."""
        total_cost = self.avg_price * self.qty + price * qty
        self.qty += qty
        self.avg_price = total_cost / self.qty if self.qty > 0 else 0.0

    def update_sell(self, qty: int) -> None:
        """매도 체결."""
        self.qty = max(0, self.qty - qty)
        if self.qty == 0:
            self.avg_price = 0.0


# ============================================================================
# BacktestEngine
# ============================================================================


class BacktestEngine:
    """일봉 기반 백테스트 엔진.

    수수료 정책:
    - 매수 수수료: 0.015%
    - 매도 수수료: 0.015% + 증권거래세 0.18% = 0.195%

    미래참조 방지:
    - 당일 캔들 시그널 확정 후, 다음 봉 시가(next_open)에 체결.
    """

    def __init__(
        self,
        strategy: Strategy,
        data_source: BacktestDataSource,
        initial_capital: float = 10_000_000.0,
        commission_rate: float = 0.015 / 100,
        tax_rate: float = 0.18 / 100,
        slippage_bps: float = 2.0,
    ) -> None:
        self._strategy = strategy
        self._data_source = data_source
        self._initial_capital = initial_capital
        self._commission_rate = commission_rate
        self._tax_rate = tax_rate
        self._slippage_rate = slippage_bps / 10_000

    def run(
        self,
        symbol: str,
        candles: list[Candle],
    ) -> BacktestResult:
        """백테스트 실행.

        Args:
            symbol: 종목 코드.
            candles: 일봉 캔들 목록 (오래된 순).

        Returns:
            BacktestResult.
        """
        if len(candles) < 2:
            logger.warning("백테스트 캔들 부족: %d개 (최소 2개 필요)", len(candles))
            result = BacktestResult(initial_capital=self._initial_capital)
            result.equity_curve = [self._initial_capital]
            return result

        result = BacktestResult(initial_capital=self._initial_capital)
        cash = self._initial_capital
        position = _Position(symbol=symbol)

        # 전략 웜업 (첫 봉 이전까지 히스토리 제공)
        self._strategy.warmup(candles[:-1])

        pending_signal: Signal | None = None
        pending_signal_ts: datetime | None = None

        for i, candle in enumerate(candles):
            # ── Step 1: 전일 시그널 체결 (미래참조 방지 핵심) ──
            if pending_signal is not None:
                cash, position = self._fill_signal(
                    pending_signal, pending_signal_ts, candle, cash, position, result
                )
                pending_signal = None
                pending_signal_ts = None

            # ── Step 2: 당일 에쿼티 기록 ──
            price_for_equity = candle.close
            equity = cash + position.qty * price_for_equity
            result.equity_curve.append(equity)

            # ── Step 3: 마지막 봉이면 시그널만 수집 (체결 불가) ──
            if i == len(candles) - 1:
                tick = self._candle_to_tick(candle)
                ctx = MarketContext(
                    symbol=symbol,
                    recent_candles=tuple(candles[max(0, i - 50) : i + 1]),
                )
                signal = self._strategy.on_tick(tick, ctx)
                if signal is not None:
                    result.unfilled_signals.append(signal)
                break

            # ── Step 4: 당일 시그널 생성 (다음 봉에서 체결 예정) ──
            tick = self._candle_to_tick(candle)
            ctx = MarketContext(
                symbol=symbol,
                recent_candles=tuple(candles[max(0, i - 50) : i + 1]),
            )
            signal = self._strategy.on_tick(tick, ctx)
            if signal is not None:
                pending_signal = signal
                pending_signal_ts = candle.timestamp

        result.initial_capital = self._initial_capital
        return result

    def _fill_signal(
        self,
        signal: Signal,
        signal_timestamp: datetime | None,
        next_candle: Candle,
        cash: float,
        position: _Position,
        result: BacktestResult,
    ) -> tuple[float, _Position]:
        """다음 봉 시가에 시그널 체결."""
        raw_price = next_candle.open

        if signal.side == SignalSide.BUY:
            exec_price = raw_price * (1 + self._slippage_rate)
            qty = signal.qty
            cost = exec_price * qty
            commission = cost * self._commission_rate

            if cash < cost + commission:
                # 매수 가능 수량으로 조정
                qty = int(cash / (exec_price * (1 + self._commission_rate)))
                if qty < 1:
                    logger.debug("현금 부족 — 매수 스킵 (symbol=%s)", signal.symbol)
                    return cash, position
                cost = exec_price * qty
                commission = cost * self._commission_rate

            cash -= cost + commission
            position.update_buy(qty, exec_price)

            _sig_ts = signal_timestamp or signal.timestamp
            trade = Trade(
                symbol=signal.symbol,
                side=SignalSide.BUY,
                price=exec_price,
                qty=qty,
                commission=commission,
                tax=0.0,
                timestamp=next_candle.timestamp,
                signal_timestamp=_sig_ts,
            )

        else:  # SELL
            exec_price = raw_price * (1 - self._slippage_rate)
            qty = min(signal.qty, position.qty)
            if qty < 1:
                logger.debug("보유 없음 — 매도 스킵 (symbol=%s)", signal.symbol)
                return cash, position

            gross = exec_price * qty
            commission = gross * self._commission_rate
            tax = gross * self._tax_rate

            cash += gross - commission - tax
            position.update_sell(qty)

            _sig_ts = signal_timestamp or signal.timestamp
            trade = Trade(
                symbol=signal.symbol,
                side=SignalSide.SELL,
                price=exec_price,
                qty=qty,
                commission=commission,
                tax=tax,
                timestamp=next_candle.timestamp,
                signal_timestamp=_sig_ts,
            )

        result.trades.append(trade)
        logger.debug(
            "체결: %s %s %d주 @%.0f (commission=%.0f, tax=%.0f)",
            trade.side,
            trade.symbol,
            trade.qty,
            trade.price,
            trade.commission,
            trade.tax,
        )
        return cash, position

    @staticmethod
    def _candle_to_tick(candle: Candle) -> Tick:
        """Candle → Tick 변환 (백테스트용)."""
        return Tick(
            symbol=candle.symbol,
            price=candle.close,
            volume=candle.volume,
            timestamp=candle.timestamp,
            market=candle.market,
        )
