"""
T020: 통합 테스트 — 시그널 → Risk Manager → Order Executor 파이프라인.

vps(모의투자) 환경에서 전체 흐름을 검증한다.
KIS API는 mock으로 대체하여 외부 의존성 없이 실행 가능하다.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config.settings import Env, Market
from core.events.bus import EventBus
from core.events.types import EventType
from core.execution.executor import OrderAck, OrderExecutor
from core.risk.manager import RiskConfig, RiskManager
from core.risk.models import (
    HaltLevel,
    Order,
    OrderSide,
    Portfolio,
    Position,
    Rejection,
)
from core.store.db import StateStore
from core.strategy.base import Signal, SignalSide

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _buy_signal(symbol: str = "005930", qty: int = 5, price: float = 50_000.0) -> Signal:
    return Signal(strategy="ma-cross", symbol=symbol, side=SignalSide.BUY, qty=qty, price=price)


def _sell_signal(symbol: str = "005930", qty: int = 5, price: float = 55_000.0) -> Signal:
    return Signal(strategy="ma-cross", symbol=symbol, side=SignalSide.SELL, qty=qty, price=price)


def _empty_portfolio() -> Portfolio:
    return Portfolio(positions={}, deposit=10_000_000.0)


def _portfolio_with_position(symbol: str, qty: int, avg_price: float) -> Portfolio:
    pos = Position(symbol=symbol, market=Market.DOMESTIC, env=Env.VPS, qty=qty, avg_price=avg_price)
    return Portfolio(positions={symbol: pos}, deposit=5_000_000.0)


def _make_rest_mock(odno: str = "0000000001") -> MagicMock:
    rest = MagicMock()
    rest.place_order = AsyncMock(
        side_effect=lambda order: OrderAck(
            client_order_id=order.client_order_id,
            broker_order_id=odno,
            symbol=order.symbol,
            status="submitted",
            raw={"ODNO": odno},
        )
    )
    return rest


# ---------------------------------------------------------------------------
# 통합 테스트: 정상 흐름
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSignalToOrderHappyPath:
    async def test_buy_signal_passes_risk_and_submits(self):
        """BUY 시그널이 Risk Manager를 통과하고 OrderExecutor가 주문을 제출한다."""
        async with StateStore(":memory:") as store:
            bus = EventBus()
            rm = RiskManager()
            executor = OrderExecutor(rest_client=_make_rest_mock(), store=store, bus=bus)

            signal = _buy_signal(qty=5, price=50_000.0)
            portfolio = _empty_portfolio()

            result = rm.evaluate(signal, portfolio)
            assert isinstance(result, Order), f"Risk 거부: {result}"

            ack = await executor.submit(result)
            assert ack.status == "submitted"
            assert ack.symbol == "005930"

    async def test_sell_signal_passes_risk_and_submits(self):
        """SELL 시그널이 Risk Manager를 통과하고 주문이 제출된다."""
        async with StateStore(":memory:") as store:
            bus = EventBus()
            rm = RiskManager()
            executor = OrderExecutor(rest_client=_make_rest_mock(), store=store, bus=bus)

            signal = _sell_signal(qty=5, price=55_000.0)
            result = rm.evaluate(signal, _empty_portfolio())
            assert isinstance(result, Order)
            assert result.side == OrderSide.SELL

            ack = await executor.submit(result)
            assert ack.status == "submitted"

    async def test_full_pipeline_emits_submitted_event(self):
        """전체 파이프라인: 시그널 → 주문 승인 → ORDER_SUBMITTED 이벤트 발행."""
        async with StateStore(":memory:") as store:
            bus = EventBus()
            rm = RiskManager()
            executor = OrderExecutor(rest_client=_make_rest_mock(), store=store, bus=bus)

            submitted_events: list = []
            bus.subscribe(EventType.ORDER_SUBMITTED, lambda e: submitted_events.append(e))
            await bus.start()

            signal = _buy_signal(qty=3, price=70_000.0)
            order = rm.evaluate(signal, _empty_portfolio())
            assert isinstance(order, Order)
            await executor.submit(order)
            await asyncio.sleep(0.05)

            await bus.stop()
            assert len(submitted_events) == 1
            payload = submitted_events[0].payload
            assert payload["symbol"] == "005930"
            assert payload["qty"] == 3

    async def test_fill_recorded_after_submit(self):
        """주문 제출 후 체결 기록 → ORDER_FILLED 이벤트."""
        async with StateStore(":memory:") as store:
            bus = EventBus()
            rm = RiskManager()
            executor = OrderExecutor(rest_client=_make_rest_mock(), store=store, bus=bus)

            filled_events: list = []
            bus.subscribe(EventType.ORDER_FILLED, lambda e: filled_events.append(e))
            await bus.start()

            signal = _buy_signal(qty=10, price=50_000.0)
            order = rm.evaluate(signal, _empty_portfolio())
            assert isinstance(order, Order)
            ack = await executor.submit(order)

            await executor.record_fill(ack.client_order_id, fill_qty=10, fill_price=50_100.0)
            await asyncio.sleep(0.05)

            await bus.stop()
            assert len(filled_events) == 1
            assert filled_events[0].payload["fill_price"] == 50_100.0


# ---------------------------------------------------------------------------
# 통합 테스트: 리스크 차단
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSignalToOrderRiskBlocked:
    async def test_kill_switch_blocks_buy(self):
        """KILL 수준 킬스위치가 활성화되면 BUY 주문이 거부된다."""
        async with StateStore(":memory:"):
            EventBus()
            rm = RiskManager()
            await rm.graduated_halt(HaltLevel.KILL)

            signal = _buy_signal()
            result = rm.evaluate(signal, _empty_portfolio())
            assert isinstance(result, Rejection)
            assert "킬스위치" in result.reason

    async def test_daily_limit_blocks_after_max(self):
        """일일 주문 한도 초과 시 거부된다."""
        config = RiskConfig(max_daily_orders=3)
        rm = RiskManager(config)
        portfolio = _empty_portfolio()

        # 3회 승인
        for _ in range(3):
            res = rm.evaluate(_buy_signal(qty=1, price=100.0), portfolio)
            assert isinstance(res, Order)

        # 4번째 → 거부
        result = rm.evaluate(_buy_signal(qty=1, price=100.0), portfolio)
        assert isinstance(result, Rejection)
        assert "일일 주문 한도" in result.reason

    async def test_position_limit_blocks_large_order(self):
        """종목당 한도 초과 주문이 거부된다."""
        config = RiskConfig(max_position_value=200_000.0)
        rm = RiskManager(config)
        # 기존 포지션: 10주 × 15,000원 = 150,000원
        portfolio = _portfolio_with_position("005930", qty=10, avg_price=15_000.0)
        # 신규 10주 × 10,000원 = 100,000원 → 합계 250,000원 > 200,000원
        result = rm.evaluate(_buy_signal(qty=10, price=10_000.0), portfolio)
        assert isinstance(result, Rejection)
        assert "종목 한도" in result.reason


# ---------------------------------------------------------------------------
# 통합 테스트: 손절/익절 → 주문 실행
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExitPipelineIntegration:
    async def test_stop_loss_triggers_sell_order(self):
        """손절 조건 → check_exit() → Order Executor 제출."""
        async with StateStore(":memory:") as store:
            bus = EventBus()
            rm = RiskManager(RiskConfig(stop_loss_pct=-0.05))
            executor = OrderExecutor(rest_client=_make_rest_mock(), store=store, bus=bus)

            pos = Position(
                symbol="005930", market=Market.DOMESTIC, env=Env.VPS,
                qty=10, avg_price=10_000.0,
            )
            # 현재가 -6% → 손절 트리거
            order = rm.check_exit(pos, current_price=9_400.0)
            assert order is not None
            assert order.side == OrderSide.SELL

            ack = await executor.submit(order)
            assert ack.status == "submitted"

    async def test_take_profit_triggers_sell_order(self):
        """익절 조건 → check_exit() → Order Executor 제출."""
        async with StateStore(":memory:") as store:
            bus = EventBus()
            rm = RiskManager(RiskConfig(take_profit_pct=0.15))
            executor = OrderExecutor(rest_client=_make_rest_mock(), store=store, bus=bus)

            pos = Position(
                symbol="005930", market=Market.DOMESTIC, env=Env.VPS,
                qty=5, avg_price=10_000.0,
            )
            # 현재가 +16% → 익절 트리거
            order = rm.check_exit(pos, current_price=11_600.0)
            assert order is not None
            ack = await executor.submit(order)
            assert ack.status == "submitted"
