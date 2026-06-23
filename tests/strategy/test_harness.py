"""core/strategy/harness.py 단위 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, Signal, SignalSide
from core.strategy.harness import HarnessResult, run_backtest
from core.strategy.plugins.ma_cross import MACrossStrategy


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _make_candles(
    prices: list[float],
    symbol: str = "005930",
    start: datetime | None = None,
) -> list[Candle]:
    """가격 목록으로 캔들 시퀀스를 생성한다."""
    if start is None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(
            symbol=symbol,
            open=p,
            high=p,
            low=p,
            close=p,
            volume=1000,
            timestamp=start + timedelta(days=i),
            market="domestic",
        )
        for i, p in enumerate(prices)
    ]


class AlwaysBuyStrategy:
    """매 틱 BUY 시그널 (하니스 기본 동작 검증용)."""

    name = "always-buy"

    def warmup(self, history: list[Candle]) -> None:
        pass

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        return Signal(strategy=self.name, symbol=tick.symbol, side=SignalSide.BUY, qty=1)


class ErrorStrategy:
    """on_tick에서 예외를 던지는 전략."""

    name = "error-strategy"

    def warmup(self, history: list[Candle]) -> None:
        pass

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        raise RuntimeError("의도적 예외")


# ---------------------------------------------------------------------------
# HarnessResult 테스트
# ---------------------------------------------------------------------------


class TestHarnessResult:
    def test_buy_sell_counts(self):
        signals = [
            Signal(strategy="t", symbol="005930", side=SignalSide.BUY, qty=1),
            Signal(strategy="t", symbol="005930", side=SignalSide.BUY, qty=1),
            Signal(strategy="t", symbol="005930", side=SignalSide.SELL, qty=1),
        ]
        result = HarnessResult(signals=signals)
        assert result.buy_count == 2
        assert result.sell_count == 1

    def test_empty_signals(self):
        result = HarnessResult()
        assert result.buy_count == 0
        assert result.sell_count == 0


# ---------------------------------------------------------------------------
# run_backtest 기본 동작
# ---------------------------------------------------------------------------


class TestRunBacktestBasic:
    def test_empty_candles_returns_empty_result(self):
        s = AlwaysBuyStrategy()
        result = run_backtest(s, [])
        assert result.signals == []
        assert result.total_ticks == 0

    def test_returns_harness_result(self):
        candles = _make_candles([100.0] * 10)
        s = AlwaysBuyStrategy()
        result = run_backtest(s, candles)
        assert isinstance(result, HarnessResult)

    def test_strategy_name_in_result(self):
        candles = _make_candles([100.0] * 10)
        result = run_backtest(AlwaysBuyStrategy(), candles)
        assert result.strategy_name == "always-buy"

    def test_symbol_in_result(self):
        candles = _make_candles([100.0] * 10, symbol="000660")
        result = run_backtest(AlwaysBuyStrategy(), candles)
        assert result.symbol == "000660"

    def test_timestamps_in_result(self):
        candles = _make_candles([100.0] * 10)
        result = run_backtest(AlwaysBuyStrategy(), candles, warmup_size=3)
        assert result.start_at == candles[3].timestamp
        assert result.end_at == candles[-1].timestamp


# ---------------------------------------------------------------------------
# warmup_size 옵션 검증
# ---------------------------------------------------------------------------


class TestRunBacktestWarmupSize:
    def test_default_warmup_size_is_half(self):
        """기본값: 10개 중 5개 warmup → 5개 재생."""
        candles = _make_candles([100.0] * 10)
        result = run_backtest(AlwaysBuyStrategy(), candles)
        assert result.total_ticks == 5

    def test_custom_warmup_size(self):
        candles = _make_candles([100.0] * 10)
        result = run_backtest(AlwaysBuyStrategy(), candles, warmup_size=2)
        assert result.total_ticks == 8

    def test_warmup_size_zero_replays_all(self):
        candles = _make_candles([100.0] * 10)
        result = run_backtest(AlwaysBuyStrategy(), candles, warmup_size=0)
        assert result.total_ticks == 10

    def test_warmup_size_equals_total_replays_nothing(self):
        candles = _make_candles([100.0] * 10)
        result = run_backtest(AlwaysBuyStrategy(), candles, warmup_size=10)
        assert result.total_ticks == 0
        assert result.signals == []

    def test_warmup_size_larger_than_candles_is_clamped(self):
        candles = _make_candles([100.0] * 5)
        result = run_backtest(AlwaysBuyStrategy(), candles, warmup_size=100)
        assert result.total_ticks == 0


# ---------------------------------------------------------------------------
# 에러 처리
# ---------------------------------------------------------------------------


class TestRunBacktestErrorHandling:
    def test_strategy_exception_does_not_abort_harness(self):
        candles = _make_candles([100.0] * 10)
        result = run_backtest(ErrorStrategy(), candles, warmup_size=0)
        # 예외가 발생해도 total_ticks는 정상 집계
        assert result.total_ticks == 10
        # 시그널은 없어야 함 (예외로 인해 None 반환)
        assert result.signals == []
        # 모든 틱에서 예외가 발생했으므로 error_count == total_ticks
        assert result.error_count == 10


# ---------------------------------------------------------------------------
# MACrossStrategy 통합 검증
# ---------------------------------------------------------------------------


class TestRunBacktestWithMACross:
    def test_golden_cross_detected(self):
        """하락 후 급등 → 골든 크로스 BUY 시그널 검출."""
        fast, slow = 3, 5

        # 하락 추세 40개 + 급등 10개
        downtrend = list(range(100, 60, -1))  # 100→61 (40개)
        uptrend = [200.0] * 10

        candles = _make_candles(downtrend + uptrend)
        strategy = MACrossStrategy(symbol="005930", fast_period=fast, slow_period=slow)

        result = run_backtest(strategy, candles, warmup_size=30)

        # 적어도 하나의 BUY 시그널이 있어야 함
        assert result.buy_count >= 1
        assert all(s.symbol == "005930" for s in result.signals)

    def test_dead_cross_detected(self):
        """상승 후 급락 → 데드 크로스 SELL 시그널 검출."""
        fast, slow = 3, 5

        uptrend = list(range(60, 100))  # 40개
        downtrend = [1.0] * 10

        candles = _make_candles(uptrend + downtrend)
        strategy = MACrossStrategy(symbol="005930", fast_period=fast, slow_period=slow)

        result = run_backtest(strategy, candles, warmup_size=30)

        assert result.sell_count >= 1

    def test_flat_market_no_signals(self):
        """횡보 시장에서는 시그널 없음."""
        candles = _make_candles([100.0] * 50)
        strategy = MACrossStrategy(symbol="005930", fast_period=3, slow_period=5)

        result = run_backtest(strategy, candles, warmup_size=20)

        assert result.signals == []

    def test_context_candles_grow_during_replay(self):
        """재생 중 MarketContext의 캔들 수가 늘어나는지 검증."""
        received_ctx_sizes: list[int] = []

        class CtxCapture:
            name = "ctx-capture"

            def warmup(self, history: list[Candle]) -> None:
                pass

            def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
                received_ctx_sizes.append(len(ctx.recent_candles))
                return None

        candles = _make_candles([100.0] * 10)
        run_backtest(CtxCapture(), candles, warmup_size=3)

        # 재생 시작 시 warmup 캔들 3개, 이후 1개씩 늘어남
        assert received_ctx_sizes[0] == 3
        assert received_ctx_sizes[-1] == 3 + len(candles[3:]) - 1
