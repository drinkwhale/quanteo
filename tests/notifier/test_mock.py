"""T035 — MockNotifier 테스트."""

from __future__ import annotations

import asyncio

import pytest

from core.notifier.base import NotifyEvent, NotifyLevel
from core.notifier.mock import MockNotifier


def _make_event(level: NotifyLevel = NotifyLevel.INFO, title: str = "t") -> NotifyEvent:
    return NotifyEvent(level=level, title=title, body="body")


@pytest.mark.asyncio
async def test_send_appends_event():
    notifier = MockNotifier()
    event = _make_event()
    await notifier.send(event)
    assert notifier.count == 1
    assert notifier.sent_events[0] is event


@pytest.mark.asyncio
async def test_send_filters_below_min_level():
    notifier = MockNotifier(min_level=NotifyLevel.WARNING)
    await notifier.send(_make_event(NotifyLevel.DEBUG))
    await notifier.send(_make_event(NotifyLevel.INFO))
    assert notifier.count == 0


@pytest.mark.asyncio
async def test_send_accepts_at_min_level():
    notifier = MockNotifier(min_level=NotifyLevel.WARNING)
    await notifier.send(_make_event(NotifyLevel.WARNING))
    await notifier.send(_make_event(NotifyLevel.ERROR))
    assert notifier.count == 2


def test_clear_resets_events():
    notifier = MockNotifier()
    notifier.sent_events.append(_make_event())
    notifier.clear()
    assert notifier.count == 0


def test_events_by_level_filters():
    notifier = MockNotifier()
    notifier.sent_events.extend([
        _make_event(NotifyLevel.INFO),
        _make_event(NotifyLevel.ERROR),
        _make_event(NotifyLevel.INFO),
    ])
    assert len(notifier.events_by_level(NotifyLevel.INFO)) == 2
    assert len(notifier.events_by_level(NotifyLevel.ERROR)) == 1
    assert len(notifier.events_by_level(NotifyLevel.CRITICAL)) == 0


@pytest.mark.asyncio
async def test_run_and_stop():
    notifier = MockNotifier()
    task = asyncio.create_task(notifier.run())
    await asyncio.sleep(0.05)
    await notifier.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert not notifier._running
