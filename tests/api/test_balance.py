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
    """day_change는 profit_loss_rate(매입가 기준)와 다른 값이어야 한다 — 이번에 고친 버그."""
    data = client_with_broker.get("/balance").json()
    item = data["items"][0]
    # current_price=75000, 오늘 캔들의 open_price=74600
    assert float(item["day_change"]["amount"]) == 400.0
    assert item["day_change"]["rate"] == pytest.approx(400 / 74600)
    assert item["day_change"]["rate"] != pytest.approx(item["profit_loss_rate"])


def test_balance_day_change_null_when_candles_fail(container_with_broker, broker_mock):
    broker_mock.get_candles = AsyncMock(side_effect=RuntimeError("candle fetch failed"))
    client = TestClient(create_app(container_with_broker))
    data = client.get("/balance").json()
    item = data["items"][0]
    assert item["day_change"] is None


def test_balance_day_change_null_when_no_candle_for_today(container_with_broker, broker_mock):
    """오늘 날짜의 캔들이 아직 없으면(개장 전 등) day_change는 결측이어야 한다.

    여러 날짜(2~5일 전)의 캔들을 섞어서 날짜 매칭이 off-by-one 없이 정확히
    "오늘"만 걸러내는지 확인한다 — 오늘 캔들이 하나도 없으면 무조건 None.
    """
    today = datetime.now(_KST)
    past_candles = [
        TossCandle(
            timestamp=today - timedelta(days=n),
            open_price=Decimal("74000"),
            high_price=Decimal("74500"),
            low_price=Decimal("73800"),
            close_price=Decimal("74200"),
            volume=1_000_000,
            currency="KRW",
        )
        for n in range(2, 6)
    ]
    broker_mock.get_candles = AsyncMock(return_value=past_candles)
    client = TestClient(create_app(container_with_broker))
    data = client.get("/balance").json()
    item = data["items"][0]
    assert item["day_change"] is None


def test_balance_day_change_null_when_todays_open_is_zero(container_with_broker, broker_mock):
    """오늘 캔들은 있는데 open_price가 0/falsy면 결측으로 처리해야 한다(가짜 0원 금지)."""
    broker_mock.get_candles = AsyncMock(return_value=_make_candles_with_today_open("0"))
    client = TestClient(create_app(container_with_broker))
    data = client.get("/balance").json()
    item = data["items"][0]
    assert item["day_change"] is None


def test_balance_logs_warning_when_todays_open_is_zero(container_with_broker, broker_mock, caplog):
    """open_price==0은 개장 전과 달리 데이터 이상이라 warning으로 남아야 한다."""
    broker_mock.get_candles = AsyncMock(return_value=_make_candles_with_today_open("0"))
    client = TestClient(create_app(container_with_broker))
    with caplog.at_level("WARNING"):
        client.get("/balance")
    assert any("open_price가 비정상" in record.message for record in caplog.records)


def test_balance_day_change_mixed_success_across_holdings(container_no_broker, store):
    """보유 종목 여럿 중 하나만 캔들 조회에 실패해도 나머지는 정상 반환돼야 한다."""
    bus = EventBus()
    risk = RiskManager(bus=bus)
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
                ),
                BalanceItem(
                    symbol="000660",
                    symbol_name="SK하이닉스",
                    qty=1,
                    avg_price=200000.0,
                    current_price=210000.0,
                    eval_amount=210000.0,
                    profit_loss=10000.0,
                    profit_loss_rate=5.0,
                    market=Market.DOMESTIC,
                ),
            ],
            total_eval_amount_krw=960000.0,
            total_profit_loss_krw=60000.0,
            deposit=0.0,
        )
    )

    async def _get_candles(symbol: str, **kwargs: object) -> list[TossCandle]:
        if symbol == "005930":
            return _make_candles_with_today_open("74600")
        raise RuntimeError("candle fetch failed for this symbol only")

    broker.get_candles = AsyncMock(side_effect=_get_candles)

    container = AppContainer(
        store=store, risk=risk, bus=bus, env="vps", market="domestic", broker=broker
    )
    client = TestClient(create_app(container))
    res = client.get("/balance")
    assert res.status_code == 200
    items = {item["symbol"]: item for item in res.json()["items"]}
    assert items["005930"]["day_change"] is not None
    assert items["000660"]["day_change"] is None


def test_balance_totals(client_with_broker):
    data = client_with_broker.get("/balance").json()
    assert float(data["total_eval_amount_krw"]) == 750000.0
    assert float(data["total_profit_loss_krw"]) == 50000.0


def test_balance_503_without_broker(client_no_broker):
    res = client_no_broker.get("/balance")
    assert res.status_code == 503
