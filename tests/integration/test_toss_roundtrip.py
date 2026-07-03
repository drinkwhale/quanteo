"""Toss 어댑터 통합 테스트 — 시그널 → Risk Manager → Toss 주문 라운드트립 (MockRestClient)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.adapters.models import BalanceInfo, BalanceItem, PriceInfo
from core.config.settings import Market
from core.events.bus import EventBus
from core.events.types import EventType
from core.execution.executor import OrderAck, OrderExecutor
from core.risk.manager import RiskConfig, RiskManager
from core.risk.models import Order, OrderSide, OrderType
from core.store.db import StateStore
from core.strategy.base import Signal, SignalSide


# ---------------------------------------------------------------------------
# MockRestClient (TossRestClient 인터페이스 모사)
# ---------------------------------------------------------------------------


class MockTossRestClient:
    """테스트용 Toss REST 클라이언트."""

    def __init__(self) -> None:
        self.submitted_orders: list[Order] = []

    async def get_price(self, symbol: str) -> PriceInfo:
        return PriceInfo(
            symbol=symbol,
            current_price=75000.0,
            open_price=74000.0,
            high_price=76000.0,
            low_price=73000.0,
            volume=100000,
            market=Market.DOMESTIC,
            raw={},
        )

    async def get_balance(self, symbol: str | None = None) -> BalanceInfo:
        return BalanceInfo(items=[], total_eval_amount_krw=0.0, total_profit_loss_krw=0.0, deposit=10_000_000.0)

    async def place_order(self, order: Order) -> OrderAck:
        self.submitted_orders.append(order)
        return OrderAck(
            client_order_id=order.client_order_id,
            broker_order_id=f"toss-{order.client_order_id[:8]}",
            symbol=order.symbol,
            status="submitted",
            raw={"orderId": f"toss-{order.client_order_id[:8]}"},
        )


# ---------------------------------------------------------------------------
# 라운드트립 테스트
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signal_to_toss_order_roundtrip():
    """시그널 → Risk Manager → Toss 주문 라운드트립 검증."""
    store = StateStore()
    await store.open()

    bus = EventBus()
    risk = RiskManager(config=RiskConfig(), bus=bus)
    mock_client = MockTossRestClient()
    executor = OrderExecutor(rest_client=mock_client, store=store, bus=bus)

    # 수신된 이벤트 수집
    received_events: list[EventType] = []
    bus.subscribe(EventType.ORDER_SUBMITTED, lambda e: received_events.append(e.type))

    signal = Signal(
        strategy="test-strategy",
        symbol="005930",
        side=SignalSide.BUY,
        qty=1,
        price=75000.0,
    )

    from core.risk.models import Portfolio
    portfolio = Portfolio(deposit=10_000_000.0)

    result = risk.evaluate(signal, portfolio)
    assert isinstance(result, Order), f"Risk Manager가 주문을 거부했습니다: {result}"

    ack = await executor.submit(result)

    assert ack.status == "submitted"
    assert ack.broker_order_id.startswith("toss-")
    assert len(mock_client.submitted_orders) == 1
    assert mock_client.submitted_orders[0].symbol == "005930"

    await store.close()


@pytest.mark.asyncio
async def test_idempotency_prevents_duplicate_toss_order():
    """동일 client_order_id로 재제출 시 Toss에 중복 주문이 가지 않아야 한다."""
    store = StateStore(":memory:")
    await store.open()

    bus = EventBus()
    mock_client = MockTossRestClient()
    executor = OrderExecutor(rest_client=mock_client, store=store, bus=bus)

    signal = Signal(
        strategy="test",
        symbol="005930",
        side=SignalSide.BUY,
        qty=5,
        price=75000.0,
    )
    order = Order(
        symbol="005930",
        market=Market.DOMESTIC,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        qty=5,
        price=75000.0,
        source_signal=signal,
        client_order_id="fixed-uuid-for-test",
    )

    ack1 = await executor.submit(order)
    ack2 = await executor.submit(order)  # 동일 ID 재제출

    assert ack1.broker_order_id == ack2.broker_order_id
    assert len(mock_client.submitted_orders) == 1  # Toss 실제 호출 1회만

    await store.close()
