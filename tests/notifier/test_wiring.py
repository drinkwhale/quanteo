"""T037 — wire_notifier() EventBus 배선 테스트."""

from __future__ import annotations

import asyncio

import pytest

from core.events.bus import EventBus
from core.events.types import Event, EventType
from core.notifier.mock import MockNotifier
from core.notifier.wiring import wire_notifier


async def _drain(bus: EventBus) -> None:
    await asyncio.wait_for(bus.join(), timeout=2.0)


@pytest.mark.asyncio
async def test_signal_event_reaches_notifier():
    bus = EventBus()
    notifier = MockNotifier()
    wire_notifier(bus, notifier)
    await bus.start()

    await bus.publish(Event(type=EventType.SIGNAL, payload={"symbol": "005930", "direction": "BUY", "strategy": "test"}))
    await _drain(bus)
    await bus.stop()

    assert notifier.count == 1
    assert "005930" in notifier.sent_events[0].title


@pytest.mark.asyncio
async def test_tick_event_not_forwarded():
    """TICK 이벤트는 알림을 보내지 않는다 (고빈도 필터)."""
    bus = EventBus()
    notifier = MockNotifier()
    wire_notifier(bus, notifier)
    await bus.start()

    await bus.publish(Event(type=EventType.TICK, payload={}))
    await _drain(bus)
    await bus.stop()

    assert notifier.count == 0


@pytest.mark.asyncio
async def test_kill_switch_is_critical():
    bus = EventBus()
    notifier = MockNotifier()
    wire_notifier(bus, notifier)
    await bus.start()

    await bus.publish(Event(type=EventType.KILL_SWITCH, payload={"reason": "테스트 킬"}))
    await _drain(bus)
    await bus.stop()

    from core.notifier.base import NotifyLevel
    assert notifier.count == 1
    assert notifier.sent_events[0].level == NotifyLevel.CRITICAL


@pytest.mark.asyncio
async def test_multiple_events_all_forwarded():
    bus = EventBus()
    notifier = MockNotifier()
    wire_notifier(bus, notifier)
    await bus.start()

    events = [
        Event(type=EventType.ORDER_SUBMITTED, payload={"symbol": "A", "side": "BUY", "qty": 1, "price": 100}),
        Event(type=EventType.ORDER_FILLED, payload={"symbol": "A", "side": "BUY", "fill_qty": 1, "fill_price": 101}),
        Event(type=EventType.STATUS, payload={"state": "ok", "detail": "정상"}),
    ]
    for e in events:
        await bus.publish(e)

    await _drain(bus)
    await bus.stop()

    assert notifier.count == 3
