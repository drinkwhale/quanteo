"""core/strategy/base.py 단위 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, Signal, SignalSide, Strategy


def _candle(close: float, ts: datetime | None = None) -> Candle:
    ts = ts or datetime.now(UTC)
    return Candle(
        symbol="005930",
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        timestamp=ts,
        market="domestic",
    )


def _tick(price: float) -> Tick:
    return Tick(
        symbol="005930",
        price=price,
        volume=100,
        timestamp=datetime.now(UTC),
        market="domestic",
    )


class TestSignal:
    def test_signal_fields(self):
        sig = Signal(strategy="test", symbol="005930", side=SignalSide.BUY, qty=5)
        assert sig.strategy == "test"
        assert sig.symbol == "005930"
        assert sig.side == SignalSide.BUY
        assert sig.qty == 5
        assert sig.price is None
        assert sig.timestamp is not None

    def test_signal_is_frozen(self):
        sig = Signal(strategy="test", symbol="005930", side=SignalSide.SELL, qty=3)
        with pytest.raises((AttributeError, TypeError)):
            sig.qty = 10  # type: ignore[misc]

    def test_signal_with_price(self):
        sig = Signal(
            strategy="ma", symbol="005930", side=SignalSide.BUY, qty=10, price=75000.0
        )
        assert sig.price == 75000.0

    def test_signal_side_enum_values(self):
        assert SignalSide.BUY == "BUY"
        assert SignalSide.SELL == "SELL"

    # C1 — qty 유효성 검증
    def test_signal_qty_zero_raises(self):
        with pytest.raises(ValueError, match="qty는 1 이상"):
            Signal(strategy="t", symbol="005930", side=SignalSide.BUY, qty=0)

    def test_signal_qty_negative_raises(self):
        with pytest.raises(ValueError, match="qty는 1 이상"):
            Signal(strategy="t", symbol="005930", side=SignalSide.BUY, qty=-5)

    def test_signal_price_zero_raises(self):
        with pytest.raises(ValueError, match="price는 0보다"):
            Signal(strategy="t", symbol="005930", side=SignalSide.BUY, qty=1, price=0.0)

    def test_signal_price_negative_raises(self):
        with pytest.raises(ValueError, match="price는 0보다"):
            Signal(strategy="t", symbol="005930", side=SignalSide.BUY, qty=1, price=-100.0)

    def test_signal_price_none_is_valid(self):
        # 시장가 주문은 price=None 허용
        sig = Signal(strategy="t", symbol="005930", side=SignalSide.BUY, qty=1, price=None)
        assert sig.price is None


class TestMarketContext:
    def test_default_values(self):
        ctx = MarketContext(symbol="005930")
        assert ctx.symbol == "005930"
        assert ctx.recent_candles == ()

    def test_candles_accessible(self):
        candles = (_candle(75000.0), _candle(75500.0))
        ctx = MarketContext(symbol="005930", recent_candles=candles)
        assert len(ctx.recent_candles) == 2
        assert ctx.recent_candles[-1].close == 75500.0

    def test_context_is_frozen(self):
        ctx = MarketContext(symbol="005930")
        with pytest.raises((AttributeError, TypeError)):
            ctx.symbol = "000660"  # type: ignore[misc]

    def test_recent_candles_is_tuple(self):
        ctx = MarketContext(symbol="005930", recent_candles=(_candle(100.0),))
        assert isinstance(ctx.recent_candles, tuple)


class TestStrategyProtocol:
    """Strategy Protocol 구조적 타이핑 검증."""

    def test_conforming_class_passes_isinstance(self):
        class DummyStrategy:
            name = "dummy"

            def warmup(self, history: list[Candle]) -> None:
                pass

            def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
                return None

        s = DummyStrategy()
        assert isinstance(s, Strategy)

    def test_missing_on_tick_fails(self):
        class IncompleteStrategy:
            name = "incomplete"

            def warmup(self, history: list[Candle]) -> None:
                pass

        assert not isinstance(IncompleteStrategy(), Strategy)

    def test_on_tick_returns_none_when_no_signal(self):
        class NoSignalStrategy:
            name = "no-signal"

            def warmup(self, history: list[Candle]) -> None:
                pass

            def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
                return None

        s = NoSignalStrategy()
        result = s.on_tick(_tick(75000.0), MarketContext(symbol="005930"))
        assert result is None
