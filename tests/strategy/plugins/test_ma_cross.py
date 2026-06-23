"""core/strategy/plugins/ma_cross.py 단위 테스트."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, SignalSide, Strategy
from core.strategy.plugins.ma_cross import MACrossStrategy


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _candle(close: float, symbol: str = "005930") -> Candle:
    return Candle(
        symbol=symbol,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        timestamp=datetime.now(timezone.utc),
        market="domestic",
    )


def _tick(price: float, symbol: str = "005930") -> Tick:
    return Tick(
        symbol=symbol,
        price=price,
        volume=100,
        timestamp=datetime.now(timezone.utc),
        market="domestic",
    )


def _ctx(symbol: str = "005930") -> MarketContext:
    return MarketContext(symbol=symbol)


def _feed_ticks(strategy: MACrossStrategy, prices: list[float]) -> list:
    """틱 시퀀스를 순차 전달하고 비None 시그널 목록을 반환한다."""
    signals = []
    for p in prices:
        sig = strategy.on_tick(_tick(p), _ctx())
        if sig is not None:
            signals.append(sig)
    return signals


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


class TestMACrossInit:
    def test_default_name_generated(self):
        s = MACrossStrategy(symbol="005930")
        assert s.name == "ma-cross-5-20"

    def test_custom_name(self):
        s = MACrossStrategy(symbol="005930", name="my-ma")
        assert s.name == "my-ma"

    def test_fast_ge_slow_raises(self):
        with pytest.raises(ValueError):
            MACrossStrategy(symbol="005930", fast_period=20, slow_period=5)

    def test_fast_equal_slow_raises(self):
        with pytest.raises(ValueError):
            MACrossStrategy(symbol="005930", fast_period=10, slow_period=10)

    def test_conforms_to_strategy_protocol(self):
        s = MACrossStrategy(symbol="005930")
        assert isinstance(s, Strategy)


class TestMACrossWarmup:
    def test_warmup_fills_price_buffer(self):
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        history = [_candle(float(i)) for i in range(1, 11)]
        s.warmup(history)
        assert s.price_count == 5  # maxlen=slow_period

    def test_warmup_sets_initial_crossover_state(self):
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        # 상승 추세 → fast > slow → prev_fast_above=True
        history = [_candle(float(i)) for i in range(1, 11)]
        s.warmup(history)
        assert s._prev_fast_above is True

    def test_warmup_ignores_other_symbols(self):
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        history = [_candle(float(i), symbol="000660") for i in range(10)]
        s.warmup(history)
        assert s.price_count == 0

    def test_warmup_clears_previous_state(self):
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        s.warmup([_candle(100.0) for _ in range(10)])
        s.warmup([])  # 재초기화
        assert s.price_count == 0
        assert s._prev_fast_above is None


class TestMACrossNoSignalBeforeEnoughData:
    def test_no_signal_before_slow_period_filled(self):
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        # slow_period-1 개 미만이면 시그널 없음
        signals = _feed_ticks(s, [100.0] * 4)
        assert signals == []

    def test_no_signal_on_first_valid_tick(self):
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        # slow_period 개 채워도 첫 번째 유효 틱은 기준점이라 시그널 없음
        signals = _feed_ticks(s, [100.0] * 5)
        assert signals == []


class TestMACrossGoldenCross:
    def test_golden_cross_generates_buy(self):
        """하락 후 상승 전환 시 BUY 시그널."""
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5, qty=10)

        # 하락 추세 (fast < slow) 초기화
        s.warmup([_candle(100.0 - i) for i in range(10)])
        assert s._prev_fast_above is False

        # 급등으로 골든 크로스 유발
        sig = s.on_tick(_tick(200.0), _ctx())

        assert sig is not None
        assert sig.side == SignalSide.BUY
        assert sig.qty == 10
        assert sig.symbol == "005930"
        assert "골든크로스" in sig.reason

    def test_no_duplicate_buy_on_sustained_uptrend(self):
        """골든 크로스 이후 상승 유지 시 추가 BUY 시그널 없음."""
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        s.warmup([_candle(100.0 - i) for i in range(10)])

        # 첫 번째 교차
        s.on_tick(_tick(200.0), _ctx())

        # 이후 계속 상승 → 추가 시그널 없음
        signals = _feed_ticks(s, [210.0, 220.0, 230.0])
        assert signals == []


class TestMACrossDeadCross:
    def test_dead_cross_generates_sell(self):
        """상승 후 하락 전환 시 SELL 시그널."""
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5, qty=5)

        # 상승 추세 (fast > slow) 초기화
        s.warmup([_candle(float(i)) for i in range(1, 11)])
        assert s._prev_fast_above is True

        # 급락으로 데드 크로스 유발
        sig = s.on_tick(_tick(1.0), _ctx())

        assert sig is not None
        assert sig.side == SignalSide.SELL
        assert sig.qty == 5
        assert "데드크로스" in sig.reason

    def test_no_duplicate_sell_on_sustained_downtrend(self):
        """데드 크로스 이후 하락 유지 시 추가 SELL 시그널 없음."""
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        s.warmup([_candle(float(i)) for i in range(1, 11)])

        s.on_tick(_tick(1.0), _ctx())

        signals = _feed_ticks(s, [0.9, 0.8, 0.7])
        assert signals == []


class TestMACrossSymbolFilter:
    def test_ignores_ticks_for_other_symbols(self):
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        s.warmup([_candle(float(i)) for i in range(1, 11)])

        sig = s.on_tick(_tick(1.0, symbol="000660"), _ctx("000660"))
        assert sig is None


class TestMACrossMultipleCrossovers:
    def test_alternating_crossovers(self):
        """골든 → 데드 → 골든 교차가 순차적으로 발생하는지 검증."""
        s = MACrossStrategy(symbol="005930", fast_period=2, slow_period=4, qty=1)

        # 하락 추세로 초기화
        s.warmup([_candle(100.0 - i * 2) for i in range(8)])

        collected = []

        def feed(price: float) -> None:
            sig = s.on_tick(_tick(price), _ctx())
            if sig:
                collected.append(sig.side)

        # 골든 크로스
        feed(200.0)
        # 상승 유지
        feed(210.0)
        feed(220.0)
        # 데드 크로스
        feed(1.0)

        assert collected == [SignalSide.BUY, SignalSide.SELL]


class TestMACrossDiagnostics:
    def test_fast_ma_slow_ma_properties(self):
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        for p in prices:
            s.on_tick(_tick(p), _ctx())

        assert s.fast_ma == pytest.approx((30.0 + 40.0 + 50.0) / 3)
        assert s.slow_ma == pytest.approx((10.0 + 20.0 + 30.0 + 40.0 + 50.0) / 5)

    def test_ma_none_before_enough_data(self):
        s = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)
        s.on_tick(_tick(100.0), _ctx())
        assert s.slow_ma is None
