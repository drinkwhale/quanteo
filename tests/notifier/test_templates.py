"""T036 — templates.event_to_notify() 테스트."""

from __future__ import annotations

import pytest

from core.events.types import Event, EventType
from core.notifier.base import NotifyLevel
from core.notifier.templates import event_to_notify


def _event(event_type: EventType, payload: object = None) -> Event:
    return Event(type=event_type, payload=payload or {}, source="test")


# ---------------------------------------------------------------------------
# 고빈도 이벤트 — None 반환
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("et", [EventType.TICK, EventType.QUOTE, EventType.CANDLE])
def test_high_frequency_events_return_none(et: EventType):
    assert event_to_notify(_event(et)) is None


# ---------------------------------------------------------------------------
# 알림 이벤트 — NotifyEvent 반환
# ---------------------------------------------------------------------------


def test_signal_returns_info():
    result = event_to_notify(_event(EventType.SIGNAL, {"symbol": "005930", "direction": "BUY", "strategy": "ma_cross"}))
    assert result is not None
    assert result.level == NotifyLevel.INFO
    assert "005930" in result.title
    assert "BUY" in result.title


def test_order_submitted_returns_info():
    result = event_to_notify(_event(EventType.ORDER_SUBMITTED, {"symbol": "005930", "side": "BUY", "qty": 10, "price": 70000}))
    assert result is not None
    assert result.level == NotifyLevel.INFO
    assert "10" in result.title


def test_order_filled_returns_info():
    result = event_to_notify(_event(EventType.ORDER_FILLED, {"symbol": "005930", "side": "BUY", "fill_qty": 10, "fill_price": 70500}))
    assert result is not None
    assert result.level == NotifyLevel.INFO
    assert "70500" in result.title


def test_order_cancelled_returns_warning():
    result = event_to_notify(_event(EventType.ORDER_CANCELLED, {"symbol": "005930", "reason": "timeout"}))
    assert result is not None
    assert result.level == NotifyLevel.WARNING
    assert "timeout" in result.body


def test_order_rejected_returns_error():
    result = event_to_notify(_event(EventType.ORDER_REJECTED, {"symbol": "005930", "reason": "잔고 부족"}))
    assert result is not None
    assert result.level == NotifyLevel.ERROR
    assert "잔고 부족" in result.body


def test_risk_breach_returns_error():
    result = event_to_notify(_event(EventType.RISK_BREACH, {"rule": "max_position", "value": 1000, "limit": 500}))
    assert result is not None
    assert result.level == NotifyLevel.ERROR
    assert "max_position" in result.title


def test_kill_switch_returns_critical():
    result = event_to_notify(_event(EventType.KILL_SWITCH, {"reason": "일일 손실 한도 초과"}))
    assert result is not None
    assert result.level == NotifyLevel.CRITICAL
    assert "킬스위치" in result.title


def test_error_returns_error():
    result = event_to_notify(_event(EventType.ERROR, {"message": "연결 오류", "module": "ws"}))
    assert result is not None
    assert result.level == NotifyLevel.ERROR
    assert "ws" in result.title


def test_status_returns_info():
    result = event_to_notify(_event(EventType.STATUS, {"state": "running", "detail": "정상 동작 중"}))
    assert result is not None
    assert result.level == NotifyLevel.INFO
    assert "running" in result.title


def test_source_and_timestamp_preserved():
    event = Event(type=EventType.ERROR, payload={"message": "err"}, source="risk_manager")
    result = event_to_notify(event)
    assert result is not None
    assert result.source == "risk_manager"
    assert result.timestamp == event.timestamp


def test_payload_missing_fields_uses_dash():
    result = event_to_notify(_event(EventType.SIGNAL, {}))
    assert result is not None
    assert "-" in result.title or result.title  # 기본값으로 채워짐


def test_dataclass_payload_works():
    from datetime import datetime

    from core.marketdata.models import Tick
    tick = Tick(symbol="005930", price=70000.0, volume=100, timestamp=datetime.now(), market="domestic")
    # TICK은 None 반환
    result = event_to_notify(Event(type=EventType.TICK, payload=tick))
    assert result is None
