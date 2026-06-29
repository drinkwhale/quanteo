"""Control API /market-status & /risk-metrics & /trades 엔드포인트 테스트."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.api.deps import AppContainer
from core.adapters.toss.models import (
    BuyingPowerInfo,
    Fill,
    KrMarketCalendar,
    KrMarketDay,
    UsMarketCalendar,
    UsMarketDay,
)
from core.events.bus import EventBus
from core.risk.manager import RiskManager
from core.store.db import StateStore


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


def _make_kr_calendar(is_open: bool = True) -> KrMarketCalendar:
    day = KrMarketDay(
        date="2026-06-29",
        is_open=is_open,
        open_time="09:00" if is_open else None,
        close_time="15:30" if is_open else None,
    )
    return KrMarketCalendar(today=day, previous_business_day=day, next_business_day=day)


def _make_us_calendar(is_open: bool = True) -> UsMarketCalendar:
    day = UsMarketDay(
        date="2026-06-29",
        is_open=is_open,
        regular_open="09:30" if is_open else None,
        regular_close="16:00" if is_open else None,
    )
    return UsMarketCalendar(today=day, previous_business_day=day, next_business_day=day)


@pytest.fixture
async def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "test.db"))
    await s.open()
    yield s
    await s.close()


@pytest.fixture
def broker_mock():
    broker = MagicMock()
    broker.get_market_calendar_kr = AsyncMock(return_value=_make_kr_calendar(is_open=True))
    broker.get_market_calendar_us = AsyncMock(return_value=_make_us_calendar(is_open=True))
    broker.get_buying_power = AsyncMock(
        return_value=BuyingPowerInfo(currency="KRW", cash_buying_power=Decimal("3500000"))
    )
    broker.get_trades = AsyncMock(return_value=[
        Fill(
            symbol="005930",
            price=Decimal("72000"),
            volume=10,
            timestamp=datetime(2026, 6, 29, 10, 30, 0, tzinfo=UTC),
            currency="KRW",
            side="BUY",
        )
    ])
    return broker


@pytest.fixture
def container_with_broker(store, broker_mock):
    bus = EventBus()
    risk = RiskManager(bus=bus)
    return AppContainer(
        store=store, risk=risk, bus=bus, env="vps", market="domestic", broker=broker_mock
    )


@pytest.fixture
def container_no_broker(store):
    bus = EventBus()
    risk = RiskManager(bus=bus)
    return AppContainer(store=store, risk=risk, bus=bus, env="vps", market="domestic")


@pytest.fixture
def client_with_broker(container_with_broker):
    app = create_app(container_with_broker)
    return TestClient(app)


@pytest.fixture
def client_no_broker(container_no_broker):
    app = create_app(container_no_broker)
    return TestClient(app)


# ---------------------------------------------------------------------------
# /market-status
# ---------------------------------------------------------------------------


def test_market_status_returns_200_with_broker(client_with_broker):
    res = client_with_broker.get("/market-status")
    assert res.status_code == 200


def test_market_status_contains_kr_and_us(client_with_broker):
    data = client_with_broker.get("/market-status").json()
    markets = {m["market"]: m for m in data["markets"]}
    assert "KR" in markets
    assert "US" in markets


def test_market_status_kr_is_open(client_with_broker):
    data = client_with_broker.get("/market-status").json()
    kr = next(m for m in data["markets"] if m["market"] == "KR")
    assert kr["is_open"] is True
    assert kr["today_date"] == "2026-06-29"
    assert kr["open_time"] == "09:00"


def test_market_status_503_without_broker(client_no_broker):
    res = client_no_broker.get("/market-status")
    assert res.status_code == 503


# ---------------------------------------------------------------------------
# /risk-metrics
# ---------------------------------------------------------------------------


def test_risk_metrics_returns_200(client_with_broker):
    res = client_with_broker.get("/risk-metrics")
    assert res.status_code == 200


def test_risk_metrics_fields(client_with_broker):
    data = client_with_broker.get("/risk-metrics").json()
    assert data["halt_level"] == "none"
    assert data["daily_order_count"] == 0
    assert float(data["buying_power"]) == 3500000.0
    assert data["buying_power_currency"] == "KRW"


def test_risk_metrics_buying_power_null_without_broker(client_no_broker):
    data = client_no_broker.get("/risk-metrics").json()
    assert data["halt_level"] == "none"
    assert data["buying_power"] is None


# ---------------------------------------------------------------------------
# /trades
# ---------------------------------------------------------------------------


def test_trades_returns_200_with_broker(client_with_broker):
    res = client_with_broker.get("/trades")
    assert res.status_code == 200


def test_trades_returns_fill_list(client_with_broker):
    data = client_with_broker.get("/trades").json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["symbol"] == "005930"
    assert float(item["price"]) == 72000.0
    assert item["volume"] == 10
    assert item["currency"] == "KRW"
    assert item["side"] == "BUY"


def test_trades_503_without_broker(client_no_broker):
    res = client_no_broker.get("/trades")
    assert res.status_code == 503
