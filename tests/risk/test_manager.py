"""core/risk/manager.py 단위 테스트."""

from __future__ import annotations

import asyncio

from core.config.settings import Market
from core.risk.manager import RiskConfig, RiskManager
from core.risk.models import (
    HaltLevel,
    Order,
    OrderSide,
    Portfolio,
    Position,
    Rejection,
)
from core.strategy.base import Signal, SignalSide

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _signal(
    side: SignalSide = SignalSide.BUY,
    qty: int = 10,
    price: float | None = 50000.0,
    symbol: str = "005930",
) -> Signal:
    return Signal(strategy="test", symbol=symbol, side=side, qty=qty, price=price)


def _empty_portfolio(deposit: float = 10_000_000.0) -> Portfolio:
    return Portfolio(positions={}, deposit=deposit)


def _portfolio_with(
    symbol: str,
    qty: int,
    avg_price: float,
    deposit: float = 10_000_000.0,
) -> Portfolio:
    pos = Position(symbol=symbol, market=Market.DOMESTIC, qty=qty, avg_price=avg_price)
    return Portfolio(positions={symbol: pos}, deposit=deposit)


# ---------------------------------------------------------------------------
# T015: 한도 가드
# ---------------------------------------------------------------------------


class TestRiskLimits:
    def test_valid_signal_returns_order(self):
        rm = RiskManager()
        result = rm.evaluate(_signal(qty=5, price=10000.0), _empty_portfolio())
        assert isinstance(result, Order)

    def test_daily_order_limit_blocks_excess(self):
        config = RiskConfig(max_daily_orders=2)
        rm = RiskManager(config)
        portfolio = _empty_portfolio()

        rm.evaluate(_signal(qty=1, price=1.0), portfolio)
        rm.evaluate(_signal(qty=1, price=1.0), portfolio)
        result = rm.evaluate(_signal(qty=1, price=1.0), portfolio)

        assert isinstance(result, Rejection)
        assert "일일 주문 한도" in result.reason

    def test_total_exposure_limit_blocks_buy(self):
        config = RiskConfig(max_total_exposure=100_000.0)
        rm = RiskManager(config)
        # 기존 포지션으로 한도 이미 초과
        portfolio = _portfolio_with("005930", qty=10, avg_price=9_000.0, deposit=1_000_000.0)
        # 기존 노출: 90,000원. 신규 100주 × 1,000원 = 100,000원 → 합계 190,000원 > 100,000원
        result = rm.evaluate(_signal(qty=100, price=1_000.0), portfolio)
        assert isinstance(result, Rejection)
        assert "총 노출 한도" in result.reason

    def test_position_value_limit_blocks_buy(self):
        config = RiskConfig(max_position_value=100_000.0)
        rm = RiskManager(config)
        # 이미 90,000원 보유
        portfolio = _portfolio_with("005930", qty=9, avg_price=10_000.0)
        # 신규 5주 × 10,000원 = 50,000원 → 합계 140,000원 > 100,000원
        result = rm.evaluate(_signal(qty=5, price=10_000.0), portfolio)
        assert isinstance(result, Rejection)
        assert "종목 한도" in result.reason

    def test_sell_bypasses_buy_limits(self):
        """SELL 시그널은 총 노출·종목 한도 검사를 통과한다."""
        config = RiskConfig(max_total_exposure=1.0, max_position_value=1.0)
        rm = RiskManager(config)
        result = rm.evaluate(_signal(side=SignalSide.SELL, qty=10, price=100.0), _empty_portfolio())
        assert isinstance(result, Order)
        assert result.side == OrderSide.SELL

    def test_market_buy_without_price_is_rejected(self):
        """시장가 BUY(price=None)는 노출 한도 계산 불가로 거부된다. (C1)"""
        rm = RiskManager()
        result = rm.evaluate(_signal(side=SignalSide.BUY, qty=10, price=None), _empty_portfolio())
        assert isinstance(result, Rejection)
        assert "시장가" in result.reason

    def test_market_sell_without_price_is_allowed(self):
        """시장가 SELL(price=None)은 청산 목적이므로 허용된다. (C1 예외)"""
        rm = RiskManager()
        result = rm.evaluate(_signal(side=SignalSide.SELL, qty=5, price=None), _empty_portfolio())
        assert isinstance(result, Order)
        assert result.order_type.value == "market"

    def test_order_has_correct_fields(self):
        rm = RiskManager()
        sig = _signal(side=SignalSide.BUY, qty=3, price=75000.0)
        result = rm.evaluate(sig, _empty_portfolio())
        assert isinstance(result, Order)
        assert result.symbol == "005930"
        assert result.qty == 3
        assert result.price == 75000.0
        assert result.side == OrderSide.BUY
        assert result.source_signal is sig


# ---------------------------------------------------------------------------
# T016: 손절/익절
# ---------------------------------------------------------------------------


class TestCheckExit:
    def _make_position(self, qty: int, avg_price: float, symbol: str = "005930") -> Position:
        return Position(symbol=symbol, market=Market.DOMESTIC, qty=qty, avg_price=avg_price)

    def test_stop_loss_triggers_sell(self):
        config = RiskConfig(stop_loss_pct=-0.05)
        rm = RiskManager(config)
        pos = self._make_position(10, avg_price=10_000.0)
        # 현재가 9,400원 → -6% < -5%
        result = rm.check_exit(pos, current_price=9_400.0)
        assert result is not None
        assert result.side == OrderSide.SELL
        assert result.qty == 10
        assert "손절" in result.source_signal.reason

    def test_take_profit_triggers_sell(self):
        config = RiskConfig(take_profit_pct=0.15)
        rm = RiskManager(config)
        pos = self._make_position(5, avg_price=10_000.0)
        # 현재가 11,600원 → +16% > +15%
        result = rm.check_exit(pos, current_price=11_600.0)
        assert result is not None
        assert result.side == OrderSide.SELL
        assert "익절" in result.source_signal.reason

    def test_within_range_returns_none(self):
        config = RiskConfig(stop_loss_pct=-0.05, take_profit_pct=0.15)
        rm = RiskManager(config)
        pos = self._make_position(10, avg_price=10_000.0)
        # 현재가 10,200원 → +2% (범위 내)
        assert rm.check_exit(pos, current_price=10_200.0) is None

    def test_zero_qty_position_returns_none(self):
        rm = RiskManager()
        pos = self._make_position(0, avg_price=10_000.0)
        assert rm.check_exit(pos, current_price=1.0) is None

    def test_stop_loss_exactly_at_threshold(self):
        """경계값: 손절률 정확히 = 임계값이면 트리거."""
        config = RiskConfig(stop_loss_pct=-0.05)
        rm = RiskManager(config)
        pos = self._make_position(1, avg_price=10_000.0)
        # 현재가 9,500원 → -5% = 임계값
        result = rm.check_exit(pos, current_price=9_500.0)
        assert result is not None  # <= 이면 트리거

    def test_take_profit_exactly_at_threshold(self):
        """경계값: 익절률 정확히 = 임계값이면 트리거."""
        config = RiskConfig(take_profit_pct=0.15)
        rm = RiskManager(config)
        pos = self._make_position(1, avg_price=10_000.0)
        # 현재가 11,500원 → +15% = 임계값
        result = rm.check_exit(pos, current_price=11_500.0)
        assert result is not None  # >= 이면 트리거


# ---------------------------------------------------------------------------
# T017: 킬스위치
# ---------------------------------------------------------------------------


class TestKillSwitch:
    def test_initial_halt_level_is_none(self):
        rm = RiskManager()
        assert rm.halt_level == HaltLevel.NONE

    def test_kill_blocks_new_buy(self):
        rm = RiskManager()
        asyncio.run(rm.graduated_halt(HaltLevel.KILL))
        result = rm.evaluate(_signal(side=SignalSide.BUY), _empty_portfolio())
        assert isinstance(result, Rejection)
        assert "킬스위치" in result.reason

    def test_kill_allows_sell(self):
        """KILL 상태에서도 SELL(손절)은 허용."""
        rm = RiskManager()
        asyncio.run(rm.graduated_halt(HaltLevel.KILL))
        result = rm.evaluate(_signal(side=SignalSide.SELL, qty=5, price=100.0), _empty_portfolio())
        assert isinstance(result, Order)

    def test_pause_blocks_new_buy(self):
        rm = RiskManager()
        asyncio.run(rm.graduated_halt(HaltLevel.PAUSE))
        result = rm.evaluate(_signal(side=SignalSide.BUY), _empty_portfolio())
        assert isinstance(result, Rejection)
        assert "일시정지" in result.reason

    def test_reduce_halves_buy_qty(self):
        """REDUCE 수준에서 BUY 수량이 절반으로 줄어든다. (C3)"""
        config = RiskConfig(reduce_ratio=0.5)
        rm = RiskManager(config)
        asyncio.run(rm.graduated_halt(HaltLevel.REDUCE))
        result = rm.evaluate(_signal(side=SignalSide.BUY, qty=10, price=1.0), _empty_portfolio())
        assert isinstance(result, Order)
        assert result.qty == 5

    def test_reduce_does_not_scale_sell_qty(self):
        """REDUCE 수준에서 SELL 청산 수량은 줄어들지 않는다. (C3)"""
        config = RiskConfig(reduce_ratio=0.5)
        rm = RiskManager(config)
        asyncio.run(rm.graduated_halt(HaltLevel.REDUCE))
        result = rm.evaluate(_signal(side=SignalSide.SELL, qty=10, price=1.0), _empty_portfolio())
        assert isinstance(result, Order)
        assert result.qty == 10  # 전량 청산

    def test_halt_level_monotonically_increases(self):
        """킬스위치 수준은 단조 증가만 허용 (강등 불가)."""
        rm = RiskManager()
        asyncio.run(rm.graduated_halt(HaltLevel.KILL))
        asyncio.run(rm.graduated_halt(HaltLevel.PAUSE))  # 강등 시도 → 무시
        assert rm.halt_level == HaltLevel.KILL

    def test_reset_halt_restores_none(self):
        rm = RiskManager()
        asyncio.run(rm.graduated_halt(HaltLevel.PAUSE))
        rm.reset_halt()
        assert rm.halt_level == HaltLevel.NONE

    def test_bus_event_published_on_kill(self):
        from core.events.bus import EventBus
        from core.events.types import EventType

        bus = EventBus()
        rm = RiskManager(bus=bus)

        received = []
        bus.subscribe(EventType.KILL_SWITCH, lambda e: received.append(e))

        async def _run():
            await bus.start()
            await rm.graduated_halt(HaltLevel.KILL)
            await asyncio.sleep(0.05)
            await bus.stop()

        asyncio.run(_run())
        assert len(received) == 1

    def test_daily_order_count_resets(self):
        """일자 변경 시 카운터 리셋 (내부 날짜 직접 조작)."""
        from datetime import date

        config = RiskConfig(max_daily_orders=1)
        rm = RiskManager(config)
        portfolio = _empty_portfolio()

        rm.evaluate(_signal(qty=1, price=1.0), portfolio)
        assert rm.daily_order_count == 1

        # 내부 리셋 날짜를 어제로 조작 → 다음 호출 시 카운터 초기화
        rm._daily_reset_date = date(2000, 1, 1)
        rm._refresh_daily_counter()
        assert rm._daily_order_count == 0
