"""core/execution/executor.py 단위 테스트."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config.settings import Env, Market
from core.events.bus import EventBus
from core.events.types import EventType
from core.execution.executor import OrderAck, OrderExecutor
from core.risk.models import Order, OrderSide, OrderType
from core.store.db import StateStore
from core.strategy.base import Signal, SignalSide

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _signal(symbol: str = "005930") -> Signal:
    return Signal(strategy="test", symbol=symbol, side=SignalSide.BUY, qty=5, price=75000.0)


def _order(symbol: str = "005930", qty: int = 5) -> Order:
    return Order(
        symbol=symbol,
        market=Market.DOMESTIC,
        env=Env.VPS,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        qty=qty,
        price=75000.0,
        source_signal=_signal(symbol),
    )


def _make_ack(order: Order) -> OrderAck:
    return OrderAck(
        client_order_id=order.client_order_id,
        broker_order_id="KIS-0001",
        symbol=order.symbol,
        status="submitted",
        raw={"rt_cd": "0"},
    )


async def _make_executor(store: StateStore) -> tuple[OrderExecutor, EventBus, MagicMock]:
    bus = EventBus()
    rest = MagicMock()
    executor = OrderExecutor(rest_client=rest, store=store, bus=bus)
    return executor, bus, rest


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestOrderExecutorSubmit:
    async def test_submit_stores_pending_then_submitted(self):
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            order = _order()
            rest.place_order = AsyncMock(return_value=_make_ack(order))

            ack = await executor.submit(order)

            assert ack.status == "submitted"
            assert ack.kis_order_id == "KIS-0001"

            row = await executor._fetch_existing(order.client_order_id)
            assert row["status"] == "submitted"
            assert row["kis_order_id"] == "KIS-0001"

    async def test_submit_publishes_order_submitted_event(self):
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            order = _order()
            rest.place_order = AsyncMock(return_value=_make_ack(order))

            received = []
            bus.subscribe(EventType.ORDER_SUBMITTED, lambda e: received.append(e))
            await bus.start()

            await executor.submit(order)
            await asyncio.sleep(0.05)
            await bus.stop()

            assert len(received) == 1
            payload = received[0].payload
            assert payload["symbol"] == "005930"
            assert payload["qty"] == 5

    async def test_submit_idempotent_on_duplicate(self):
        """동일 client_order_id 재전송 시 KIS API 1회만 호출."""
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            order = _order()
            rest.place_order = AsyncMock(return_value=_make_ack(order))

            await executor.submit(order)
            await executor.submit(order)  # 재전송

            assert rest.place_order.call_count == 1

    async def test_submit_raises_on_rejected_duplicate(self):
        """이미 rejected 상태인 주문 재제출 시 RuntimeError 발생. (H1)"""
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            order = _order()
            rest.place_order = AsyncMock(side_effect=RuntimeError("KIS 오류"))

            with pytest.raises(RuntimeError):
                await executor.submit(order)

            # rejected 상태 주문 재제출 → 다른 RuntimeError 발생
            with pytest.raises(RuntimeError, match="이미 거부된 주문"):
                await executor.submit(order)

    async def test_submit_on_api_failure_stores_rejected(self):
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            order = _order()
            rest.place_order = AsyncMock(side_effect=RuntimeError("KIS 서버 오류"))

            with pytest.raises(RuntimeError):
                await executor.submit(order)

            row = await executor._fetch_existing(order.client_order_id)
            assert row["status"] == "rejected"

    async def test_submit_rejected_publishes_event(self):
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            order = _order()
            rest.place_order = AsyncMock(side_effect=RuntimeError("오류"))

            received = []
            bus.subscribe(EventType.ORDER_REJECTED, lambda e: received.append(e))
            await bus.start()

            with pytest.raises(RuntimeError):
                await executor.submit(order)

            await asyncio.sleep(0.05)
            await bus.stop()

            assert len(received) == 1


@pytest.mark.asyncio
class TestOrderExecutorRecordFill:
    async def test_record_fill_stores_fill_and_updates_status(self):
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            order = _order()
            rest.place_order = AsyncMock(return_value=_make_ack(order))
            await executor.submit(order)

            await executor.record_fill(order.client_order_id, fill_qty=5, fill_price=75100.0)

            row = await executor._fetch_existing(order.client_order_id)
            assert row["status"] == "filled"

    async def test_record_fill_publishes_event(self):
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            order = _order()
            rest.place_order = AsyncMock(return_value=_make_ack(order))
            await executor.submit(order)

            received = []
            bus.subscribe(EventType.ORDER_FILLED, lambda e: received.append(e))
            await bus.start()

            await executor.record_fill(order.client_order_id, fill_qty=5, fill_price=75100.0)
            await asyncio.sleep(0.05)
            await bus.stop()

            assert len(received) == 1
            assert received[0].payload["fill_qty"] == 5
            assert received[0].payload["fill_price"] == 75100.0

    async def test_record_fill_unknown_order_raises(self):
        """존재하지 않는 주문 체결 기록 → RuntimeError 발생. (H2)"""
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            with pytest.raises(RuntimeError, match="미등록 주문"):
                await executor.record_fill("nonexistent-id", fill_qty=1, fill_price=100.0)

    async def test_partial_fill_sets_partial_status(self):
        """부분 체결 시 주문 상태가 'partial'로 변경된다. (C2)"""
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            order = _order(qty=10)
            rest.place_order = AsyncMock(return_value=_make_ack(order))
            await executor.submit(order)

            await executor.record_fill(order.client_order_id, fill_qty=5, fill_price=75000.0)

            row = await executor._fetch_existing(order.client_order_id)
            assert row["status"] == "partial"

    async def test_full_fill_after_partial_sets_filled_status(self):
        """2회 체결(부분 → 완전)시 최종 상태가 'filled'. (C2)"""
        async with StateStore(":memory:") as store:
            executor, bus, rest = await _make_executor(store)
            order = _order(qty=10)
            rest.place_order = AsyncMock(return_value=_make_ack(order))
            await executor.submit(order)

            await executor.record_fill(order.client_order_id, fill_qty=6, fill_price=75000.0)
            row = await executor._fetch_existing(order.client_order_id)
            assert row["status"] == "partial"

            await executor.record_fill(order.client_order_id, fill_qty=4, fill_price=75100.0)
            row = await executor._fetch_existing(order.client_order_id)
            assert row["status"] == "filled"
