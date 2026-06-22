"""T033 — NotifyLevel / NotifyEvent / Notifier Protocol 테스트."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.notifier.base import NotifyEvent, NotifyLevel, Notifier, level_rank
from core.notifier.mock import MockNotifier


def test_level_rank_order():
    assert level_rank(NotifyLevel.DEBUG) < level_rank(NotifyLevel.INFO)
    assert level_rank(NotifyLevel.INFO) < level_rank(NotifyLevel.WARNING)
    assert level_rank(NotifyLevel.WARNING) < level_rank(NotifyLevel.ERROR)
    assert level_rank(NotifyLevel.ERROR) < level_rank(NotifyLevel.CRITICAL)


def test_notify_event_defaults():
    event = NotifyEvent(level=NotifyLevel.INFO, title="t", body="b")
    assert event.source == ""
    assert event.timestamp.tzinfo is not None


def test_notify_event_is_frozen():
    event = NotifyEvent(level=NotifyLevel.INFO, title="t", body="b")
    with pytest.raises((AttributeError, TypeError)):
        event.title = "changed"  # type: ignore[misc]


def test_mock_notifier_satisfies_protocol():
    notifier = MockNotifier()
    assert isinstance(notifier, Notifier)
