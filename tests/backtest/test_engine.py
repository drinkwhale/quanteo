"""백테스트 엔진 테스트.

미래참조 방지, 매수·매도 수수료 계산 정확도, 포지션 관리,
마지막 봉 미체결 시그널 검증.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol
from unittest.mock import MagicMock

import pytest

from core.backtest.engine import BacktestEngine, BacktestResult, Trade
from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, Signal, SignalSide


# ============================================================================
# 픽스처
# ============================================================================


def _make_candle(i: int, close: float, volume: int = 1000) -> Candle:
    base_date = datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)
    ts = base_date + timedelta(days=i)
    return Candle(
        symbol="000660",
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        volume=volume,
        timestamp=ts,
        market="domestic",
    )


def _make_candles(prices: list[float]) -> list[Candle]:
    return [_make_candle(i, p) for i, p in enumerate(prices)]


class _BuyOnFirstStrategy:
    """첫 번째 on_tick 호출 시 매수 시그널을 반환하는 테스트용 전략."""

    name = "buy_on_first"
    _called = 0

    def warmup(self, history: list[Candle]) -> None:
        self._called = 0

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        self._called += 1
        if self._called == 1:
            return Signal(
                strategy=self.name,
                symbol=tick.symbol,
                side=SignalSide.BUY,
                qty=10,
                price=tick.price,
                reason="첫 봉 매수",
            )
        return None


class _BuyThenSellStrategy:
    """첫 봉 매수, 세 번째 봉 매도하는 전략."""

    name = "buy_then_sell"
    _called = 0

    def warmup(self, history: list[Candle]) -> None:
        self._called = 0

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        self._called += 1
        if self._called == 1:
            return Signal(strategy=self.name, symbol=tick.symbol, side=SignalSide.BUY, qty=10)
        if self._called == 3:
            return Signal(strategy=self.name, symbol=tick.symbol, side=SignalSide.SELL, qty=10)
        return None


class _LastCandleSignalStrategy:
    """마지막 봉에서 시그널을 반환하는 전략."""

    name = "last_candle"
    _idx = 0
    _total = 0

    def warmup(self, history: list[Candle]) -> None:
        self._total = 0
        self._idx = 0

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        self._idx += 1
        # 항상 시그널 반환 (마지막 봉 포함)
        return Signal(strategy=self.name, symbol=tick.symbol, side=SignalSide.BUY, qty=5)


class _NoSignalStrategy:
    """항상 None 반환하는 전략."""

    name = "no_signal"

    def warmup(self, history: list[Candle]) -> None:
        pass

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        return None


@pytest.fixture
def mock_data_source():
    return MagicMock()


# ============================================================================
# 미래참조 방지 테스트
# ============================================================================


def test_no_lookahead_bias(mock_data_source):
    """시그널 발생 봉의 다음 봉 시가로 체결되어야 한다."""
    strategy = _BuyOnFirstStrategy()
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=1_000_000)

    prices = [100.0, 110.0, 120.0, 130.0]
    candles = _make_candles(prices)

    result = engine.run("000660", candles)

    # 첫 봉(close=100)에서 시그널 → 둘째 봉(open=110*0.99≈108.9) 시가에 체결
    assert len(result.trades) == 1
    trade = result.trades[0]
    # 둘째 봉 시가는 110 * 0.99 = 108.9, 슬리피지 2bps 적용
    expected_price = 110 * 0.99 * (1 + 0.0002)
    assert abs(trade.price - expected_price) < 0.01
    # 체결 타임스탬프는 둘째 봉
    assert trade.timestamp == candles[1].timestamp


def test_signal_timestamp_is_signal_day(mock_data_source):
    """Trade.signal_timestamp는 시그널 발생 봉의 타임스탬프여야 한다."""
    strategy = _BuyOnFirstStrategy()
    engine = BacktestEngine(strategy, mock_data_source)

    candles = _make_candles([100.0, 110.0, 120.0])
    result = engine.run("000660", candles)

    assert result.trades[0].signal_timestamp == candles[0].timestamp


# ============================================================================
# 수수료·세금 계산 정확도
# ============================================================================


def test_buy_commission_only(mock_data_source):
    """매수 시 수수료만 부과, 세금 없음."""
    strategy = _BuyOnFirstStrategy()
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=10_000_000)

    candles = _make_candles([100_000.0, 100_000.0, 100_000.0])
    result = engine.run("000660", candles)

    trade = result.trades[0]
    assert trade.side == SignalSide.BUY
    assert trade.tax == 0.0
    # commission = price * qty * 0.00015
    expected_commission = trade.price * trade.qty * 0.00015
    assert abs(trade.commission - expected_commission) < 1.0


def test_sell_commission_and_tax(mock_data_source):
    """매도 시 수수료 + 증권거래세 부과."""
    strategy = _BuyThenSellStrategy()
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=10_000_000)

    candles = _make_candles([100_000.0, 100_000.0, 100_000.0, 100_000.0])
    result = engine.run("000660", candles)

    sell_trades = [t for t in result.trades if t.side == SignalSide.SELL]
    assert len(sell_trades) == 1

    sell = sell_trades[0]
    gross = sell.price * sell.qty
    expected_commission = gross * 0.00015
    expected_tax = gross * 0.0018

    assert abs(sell.commission - expected_commission) < 1.0
    assert abs(sell.tax - expected_tax) < 1.0


def test_net_amount_buy_negative(mock_data_source):
    """매수의 net_amount는 음수 (현금 유출)."""
    strategy = _BuyOnFirstStrategy()
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=10_000_000)

    candles = _make_candles([100_000.0, 100_000.0, 100_000.0])
    result = engine.run("000660", candles)

    assert result.trades[0].net_amount < 0


def test_net_amount_sell_positive(mock_data_source):
    """매도의 net_amount는 양수 (현금 유입)."""
    strategy = _BuyThenSellStrategy()
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=10_000_000)

    candles = _make_candles([100_000.0, 100_000.0, 100_000.0, 100_000.0])
    result = engine.run("000660", candles)

    sell = [t for t in result.trades if t.side == SignalSide.SELL][0]
    assert sell.net_amount > 0


# ============================================================================
# 포지션 비율 관리
# ============================================================================


def test_equity_curve_length_equals_candles(mock_data_source):
    """에쿼티 커브 길이 = 캔들 수."""
    strategy = _NoSignalStrategy()
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=1_000_000)

    candles = _make_candles([100.0, 110.0, 120.0, 130.0, 140.0])
    result = engine.run("000660", candles)

    assert len(result.equity_curve) == len(candles)


def test_equity_unchanged_without_trades(mock_data_source):
    """거래 없으면 에쿼티 = 초기 자본 유지."""
    strategy = _NoSignalStrategy()
    capital = 5_000_000.0
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=capital)

    candles = _make_candles([100.0, 100.0, 100.0])
    result = engine.run("000660", candles)

    for eq in result.equity_curve:
        assert eq == capital


def test_buy_increases_equity_on_price_rise(mock_data_source):
    """매수 후 가격 상승 시 에쿼티 증가."""
    strategy = _BuyOnFirstStrategy()
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=10_000_000)

    # 100 → 200 두 배 상승
    candles = _make_candles([100_000.0, 100_000.0, 200_000.0])
    result = engine.run("000660", candles)

    assert result.equity_curve[-1] > result.equity_curve[0]


# ============================================================================
# 마지막 봉 미체결 시그널
# ============================================================================


def test_unfilled_signals_on_last_candle(mock_data_source):
    """마지막 봉에서 발생한 시그널은 unfilled_signals에 포함."""
    strategy = _LastCandleSignalStrategy()
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=10_000_000)

    candles = _make_candles([100.0, 110.0, 120.0])
    result = engine.run("000660", candles)

    # 마지막 봉 시그널은 미체결
    assert len(result.unfilled_signals) == 1
    assert result.unfilled_signals[0].side == SignalSide.BUY


def test_no_unfilled_when_no_last_signal(mock_data_source):
    """마지막 봉에 시그널 없으면 unfilled_signals 비어있음."""
    strategy = _BuyOnFirstStrategy()  # 첫 봉만 시그널
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=10_000_000)

    candles = _make_candles([100.0, 110.0, 120.0])
    result = engine.run("000660", candles)

    assert len(result.unfilled_signals) == 0


# ============================================================================
# 엣지 케이스
# ============================================================================


def test_insufficient_candles(mock_data_source):
    """캔들 1개이면 빈 결과 반환."""
    strategy = _BuyOnFirstStrategy()
    engine = BacktestEngine(strategy, mock_data_source)

    result = engine.run("000660", [_make_candle(0, 100.0)])

    assert result.trades == []
    assert len(result.equity_curve) == 1


def test_cash_insufficient_skip_buy(mock_data_source):
    """현금 부족 시 매수 스킵."""
    strategy = _BuyOnFirstStrategy()
    # 매우 적은 초기 자본
    engine = BacktestEngine(strategy, mock_data_source, initial_capital=100.0)

    # 가격은 100,000 — qty=10이면 1,000,000 필요
    candles = _make_candles([100_000.0, 100_000.0, 100_000.0])
    result = engine.run("000660", candles)

    # 현금 부족 → 스킵
    assert result.trades == []
