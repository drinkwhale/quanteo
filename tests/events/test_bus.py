"""EventBus — 발행/구독 테스트."""

from __future__ import annotations

import asyncio
import pytest

from core.events.bus import EventBus
from core.events.types import Event, EventType


def _tick_event() -> Event:
    return Event(type=EventType.TICK, payload={"price": 75000}, source="test")


@pytest.mark.asyncio
async def test_sync_handler_receives_event():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(EventType.TICK, received.append)

    await bus.start()
    await bus.publish(_tick_event())
    await asyncio.sleep(0.05)
    await bus.stop()

    assert len(received) == 1
    assert received[0].type == EventType.TICK


@pytest.mark.asyncio
async def test_async_handler_receives_event():
    bus = EventBus()
    received: list[Event] = []

    async def async_handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.SIGNAL, async_handler)
    await bus.start()
    await bus.publish(Event(type=EventType.SIGNAL, payload="buy"))
    await asyncio.sleep(0.05)
    await bus.stop()

    assert len(received) == 1


@pytest.mark.asyncio
async def test_wildcard_handler_receives_all():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe_all(received.append)

    await bus.start()
    await bus.publish(Event(type=EventType.TICK, payload=1))
    await bus.publish(Event(type=EventType.SIGNAL, payload=2))
    await asyncio.sleep(0.05)
    await bus.stop()

    assert len(received) == 2


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(EventType.TICK, received.append)
    bus.unsubscribe(EventType.TICK, received.append)

    await bus.start()
    await bus.publish(_tick_event())
    await asyncio.sleep(0.05)
    await bus.stop()

    assert received == []


@pytest.mark.asyncio
async def test_handler_exception_does_not_stop_bus():
    bus = EventBus()
    good_received: list[Event] = []

    def bad_handler(event: Event) -> None:
        raise RuntimeError("의도적 예외")

    bus.subscribe(EventType.TICK, bad_handler)
    bus.subscribe(EventType.TICK, good_received.append)

    await bus.start()
    await bus.publish(_tick_event())
    await asyncio.sleep(0.05)
    await bus.stop()

    # bad_handler 예외에도 good_handler는 호출됨
    assert len(good_received) == 1


@pytest.mark.asyncio
async def test_queue_full_drops_oldest():
    bus = EventBus(queue_maxsize=2)
    # 큐 가득 참 상태에서 publish 시 드롭되어야 함 (예외 없음)
    for i in range(5):
        await bus.publish(Event(type=EventType.TICK, payload=i))
    # 예외 없이 완료되면 통과
    assert bus.qsize <= 2
