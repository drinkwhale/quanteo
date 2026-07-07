"""Control API /balance 엔드포인트 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from core.adapters.models import BalanceInfo, BalanceItem
from core.adapters.toss.models import TossCandle
from core.api.app import create_app
from core.api.deps import AppContainer
from core.config.settings import Market
from core.events.bus import EventBus
from core.risk.manager import RiskManager
from core.store.db import StateStore

_KST = ZoneInfo("Asia/Seoul")


def _make_candles_with_today_open(open_price: str) -> list[TossCandle]:
    """day_change 계산이 "KST 오늘 날짜의 캔들"을 날짜로 찾아 쓰므로, 테스트
    실행 시점과 무관하게 항상 맞도록 실제 오늘 날짜로 캔들을 만든다."""
    today = datetime.now(_KST)
    yesterday = today - timedelta(days=1)
    return [
        TossCandle(
            timestamp=yesterday,
            open_price=Decimal("74000"),
            high_price=Decimal("74500"),
            low_price=Decimal("73800"),
            close_price=Decimal("74200"),
            volume=1_000_000,
            currency="KRW",
        ),
        TossCandle(
            timestamp=today,
            open_price=Decimal(open_price),
            high_price=Decimal("75200"),
            low_price=Decimal("74400"),
            close_price=Decimal("75000"),
            volume=1_200_000,
            currency="KRW",
        ),
    ]


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
    broker.get_candles = AsyncMock(return_value=_make_candles_with_today_open("74600"))
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


def test_balance_day_change_computed_from_todays_open(client_with_broker):
    """day_change*는 profit_loss_rate(매입가 기준)와 다른 값이어야 한다 — 이번에 고친 버그."""
    data = client_with_broker.get("/balance").json()
    item = data["items"][0]
    # current_price=75000, 오늘 캔들의 open_price=74600
    assert float(item["day_change"]) == 400.0
    assert item["day_change_rate"] == pytest.approx(400 / 74600)
    assert item["day_change_rate"] != pytest.approx(item["profit_loss_rate"])


def test_balance_day_change_null_when_candles_fail(container_with_broker, broker_mock):
    broker_mock.get_candles = AsyncMock(side_effect=RuntimeError("candle fetch failed"))
    client = TestClient(create_app(container_with_broker))
    data = client.get("/balance").json()
    item = data["items"][0]
    assert item["day_change"] is None
    assert item["day_change_rate"] is None


def test_balance_day_change_null_when_no_candle_for_today(container_with_broker, broker_mock):
    """오늘 날짜의 캔들이 아직 없으면(개장 전 등) day_change는 결측이어야 한다."""
    yesterday_only = _make_candles_with_today_open("74600")[:1]
    broker_mock.get_candles = AsyncMock(return_value=yesterday_only)
    client = TestClient(create_app(container_with_broker))
    data = client.get("/balance").json()
    item = data["items"][0]
    assert item["day_change"] is None
    assert item["day_change_rate"] is None


def test_balance_totals(client_with_broker):
    data = client_with_broker.get("/balance").json()
    assert float(data["total_eval_amount_krw"]) == 750000.0
    assert float(data["total_profit_loss_krw"]) == 50000.0


def test_balance_503_without_broker(client_no_broker):
    res = client_no_broker.get("/balance")
    assert res.status_code == 503
