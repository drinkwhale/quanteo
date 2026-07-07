"""Control API /balance 엔드포인트 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from core.adapters.models import BalanceInfo, BalanceItem
from core.api.app import create_app
from core.api.deps import AppContainer
from core.config.settings import Market
from core.events.bus import EventBus
from core.risk.manager import RiskManager
from core.store.db import StateStore


@pytest.fixture
async def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "test.db"))
    await s.open()
    yield s
    await s.close()


@pytest.fixture
def broker_mock():
    broker = MagicMock()
    broker.get_balance = AsyncMock(
        return_value=BalanceInfo(
            items=[
                BalanceItem(
                    symbol="005930",
                    symbol_name="삼성전자",
                    qty=10,
                    avg_price=70000.0,
                    current_price=75000.0,
                    eval_amount=750000.0,
                    profit_loss=50000.0,
                    profit_loss_rate=7.14,
                    market=Market.DOMESTIC,
                )
            ],
            total_eval_amount_krw=750000.0,
            total_profit_loss_krw=50000.0,
            deposit=0.0,
        )
    )
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
    return TestClient(create_app(container_with_broker))


@pytest.fixture
def client_no_broker(container_no_broker):
    return TestClient(create_app(container_no_broker))


def test_balance_returns_200_with_broker(client_with_broker):
    res = client_with_broker.get("/balance")
    assert res.status_code == 200


def test_balance_item_fields(client_with_broker):
    data = client_with_broker.get("/balance").json()
    item = data["items"][0]
    assert item["symbol"] == "005930"
    assert item["symbol_name"] == "삼성전자"
    assert float(item["eval_amount"]) == 750000.0
    assert float(item["profit_loss"]) == 50000.0
    assert item["profit_loss_rate"] == 7.14
    assert item["market"] == "domestic"


def test_balance_totals(client_with_broker):
    data = client_with_broker.get("/balance").json()
    assert float(data["total_eval_amount_krw"]) == 750000.0
    assert float(data["total_profit_loss_krw"]) == 50000.0


def test_balance_503_without_broker(client_no_broker):
    res = client_no_broker.get("/balance")
    assert res.status_code == 503
