"""core/strategy/engine.py 단위 테스트."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from core.events.bus import EventBus
from core.events.types import Event, EventType
from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, Signal, SignalSide, Strategy
from core.strategy.engine import StrategyEngine


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _tick(symbol: str = "005930", price: float = 75000.0) -> Tick:
    return Tick(
        symbol=symbol,
        price=price,
        volume=100,
        timestamp=datetime.now(timezone.utc),
        market="domestic",
    )


def _candle(symbol: str = "005930", close: float = 75000.0) -> Candle:
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


def _tick_event(tick: Tick) -> Event:
    return Event(type=EventType.TICK, payload=tick)


def _candle_event(candle: Candle) -> Event:
    return Event(type=EventType.CANDLE, payload=candle)


class AlwaysBuyStrategy:
    """매 틱마다 BUY 시그널을 반환하는 테스트용 전략."""

    name = "always-buy"

    def __init__(self):
        self.warmed_up = False
        self.warmup_history: list[Candle] = []

    def warmup(self, history: list[Candle]) -> None:
        self.warmed_up = True
        self.warmup_history = history

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        return Signal(strategy=self.name, symbol=tick.symbol, side=SignalSide.BUY, qty=1)


class NeverSignalStrategy:
    """항상 None을 반환하는 테스트용 전략."""

    name = "never-signal"

    def warmup(self, history: list[Candle]) -> None:
        pass

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        return None


class ErrorOnTickStrategy:
    """on_tick에서 예외를 던지는 테스트용 전략."""

    name = "error-strategy"

    def warmup(self, history: list[Candle]) -> None:
        pass

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        raise RuntimeError("의도적 예외")


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


class TestStrategyEngineRegister:
    def test_register_adds_strategy(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        s = AlwaysBuyStrategy()
        engine.register(s)
        assert "always-buy" in engine.strategy_names

    def test_register_overwrites_same_name(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        engine.register(AlwaysBuyStrategy())
        engine.register(AlwaysBuyStrategy())  # 재등록
        assert engine.strategy_names.count("always-buy") == 1

    def test_unregister_removes_strategy(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        engine.register(AlwaysBuyStrategy())
        engine.unregister("always-buy")
        assert "always-buy" not in engine.strategy_names


class TestStrategyEngineWarmup:
    def test_warmup_calls_strategy_warmup(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        s = AlwaysBuyStrategy()
        engine.register(s)

        history = [_candle() for _ in range(10)]
        engine.warmup(history)

        assert s.warmed_up
        assert len(s.warmup_history) == 10

    def test_warmup_fills_candle_buffer(self):
        bus = EventBus()
        engine = StrategyEngine(bus, candle_buffer_size=5)
        engine.register(NeverSignalStrategy())

        history = [_candle() for _ in range(10)]
        engine.warmup(history)

        # _handle_tick_event → _build_context 로 버퍼 크기 확인
        ctx = engine._build_context("005930")
        assert len(ctx.recent_candles) == 5  # 버퍼 크기로 잘림

    def test_warmup_empty_history_is_noop(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        s = AlwaysBuyStrategy()
        engine.register(s)
        engine.warmup([])  # 예외 없이 통과
        assert not s.warmed_up


@pytest.mark.asyncio
class TestStrategyEngineTickHandling:
    async def test_tick_event_triggers_on_tick_and_publishes_signal(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        engine.register(AlwaysBuyStrategy())

        received_signals: list[Signal] = []

        def capture(event: Event) -> None:
            received_signals.append(event.payload)

        bus.subscribe(EventType.SIGNAL, capture)
        await bus.start()

        tick = _tick()
        engine._handle_tick_event(_tick_event(tick))
        await asyncio.sleep(0.05)  # 큐 디스패치 대기

        await bus.stop()

        assert len(received_signals) == 1
        assert received_signals[0].side == SignalSide.BUY
        assert received_signals[0].symbol == "005930"

    async def test_never_signal_strategy_publishes_nothing(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        engine.register(NeverSignalStrategy())

        received: list[Event] = []
        bus.subscribe(EventType.SIGNAL, lambda e: received.append(e))
        await bus.start()

        engine._handle_tick_event(_tick_event(_tick()))
        await asyncio.sleep(0.05)

        await bus.stop()
        assert received == []

    async def test_error_in_strategy_does_not_crash_engine(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        engine.register(ErrorOnTickStrategy())

        # 예외가 전파되지 않고 내부에서 처리됨
        engine._handle_tick_event(_tick_event(_tick()))

    async def test_multiple_strategies_all_run(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        engine.register(AlwaysBuyStrategy())
        engine.register(NeverSignalStrategy())

        received: list[Event] = []
        bus.subscribe(EventType.SIGNAL, lambda e: received.append(e))
        await bus.start()

        engine._handle_tick_event(_tick_event(_tick()))
        await asyncio.sleep(0.05)

        await bus.stop()
        assert len(received) == 1  # AlwaysBuy만 시그널 발행


class TestStrategyEngineCandleBuffer:
    def test_candle_event_updates_buffer(self):
        bus = EventBus()
        engine = StrategyEngine(bus)

        candle = _candle()
        engine._handle_candle_event(_candle_event(candle))

        ctx = engine._build_context("005930")
        assert len(ctx.recent_candles) == 1
        assert ctx.recent_candles[0].close == 75000.0

    def test_buffer_respects_max_size(self):
        bus = EventBus()
        engine = StrategyEngine(bus, candle_buffer_size=3)

        for i in range(5):
            engine._handle_candle_event(_candle_event(_candle(close=float(i))))

        ctx = engine._build_context("005930")
        assert len(ctx.recent_candles) == 3
        assert ctx.recent_candles[-1].close == 4.0  # 최신

    def test_context_for_unknown_symbol_returns_empty_candles(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        ctx = engine._build_context("UNKNOWN")
        assert ctx.recent_candles == ()


@pytest.mark.asyncio
class TestStrategyEngineLifecycle:
    async def test_run_and_stop(self):
        bus = EventBus()
        engine = StrategyEngine(bus)

        task = asyncio.create_task(engine.run())
        await asyncio.sleep(0.05)
        await engine.stop()
        await asyncio.wait_for(task, timeout=1.0)
        assert not engine._running

    async def test_run_registers_tick_handler(self):
        bus = EventBus()
        engine = StrategyEngine(bus)
        engine.register(AlwaysBuyStrategy())

        received: list[Event] = []
        bus.subscribe(EventType.SIGNAL, lambda e: received.append(e))

        task = asyncio.create_task(engine.run())
        await bus.start()

        # TICK 이벤트 발행
        await bus.publish(_tick_event(_tick()))
        await asyncio.sleep(0.05)

        await engine.stop()
        await bus.stop()
        await asyncio.wait_for(task, timeout=1.0)

        assert len(received) == 1
