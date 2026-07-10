"""Control API /balance 엔드포인트 테스트."""

from __future__ import annotations

from decimal import Decimal
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
def kis_client_mock():
    client = MagicMock()
    client.get_prev_close = AsyncMock(return_value=Decimal("74200"))
    return client


@pytest.fixture
def container_with_broker(store, broker_mock, kis_client_mock):
    bus = EventBus()
    risk = RiskManager(bus=bus)
    return AppContainer(
        store=store,
        risk=risk,
        bus=bus,
        env="vps",
        market="domestic",
        broker=broker_mock,
        kis_client=kis_client_mock,
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


def test_balance_day_change_computed_from_kis_prev_close(client_with_broker, kis_client_mock):
    """day_change는 profit_loss_rate(매입가 기준)와 다른 값이어야 한다.

    전일 종가는 KIS 시세 조회(get_prev_close)로 얻는다 — Toss 캔들 데이터가
    실제 시세와 어긋나는 사례가 확인돼 KIS로 대체했다.
    """
    data = client_with_broker.get("/balance").json()
    item = data["items"][0]
    kis_client_mock.get_prev_close.assert_awaited_once_with("005930")
    # current_price=75000, 전일 종가(KIS)=74200
    assert float(item["day_change"]["amount"]) == 800.0
    assert item["day_change"]["rate"] == pytest.approx(800 / 74200)
    assert item["day_change"]["rate"] != pytest.approx(item["profit_loss_rate"])


def test_balance_day_change_null_when_kis_client_not_configured(store, broker_mock):
    """kis_client가 주입 안 되면(설정 미비) day_change는 결측이어야 한다."""
    bus = EventBus()
    risk = RiskManager(bus=bus)
    container = AppContainer(
        store=store, risk=risk, bus=bus, env="vps", market="domestic", broker=broker_mock
    )
    client = TestClient(create_app(container))
    data = client.get("/balance").json()
    item = data["items"][0]
    assert item["day_change"] is None


def test_balance_day_change_null_when_kis_lookup_fails(container_with_broker, kis_client_mock):
    kis_client_mock.get_prev_close = AsyncMock(side_effect=RuntimeError("KIS 조회 실패"))
    client = TestClient(create_app(container_with_broker))
    data = client.get("/balance").json()
    item = data["items"][0]
    assert item["day_change"] is None


def test_balance_day_change_null_when_prev_close_is_zero(container_with_broker, kis_client_mock):
    """KIS가 0/falsy 전일 종가를 주면 결측으로 처리해야 한다(가짜 0원 금지)."""
    kis_client_mock.get_prev_close = AsyncMock(return_value=Decimal("0"))
    client = TestClient(create_app(container_with_broker))
    data = client.get("/balance").json()
    item = data["items"][0]
    assert item["day_change"] is None


def test_balance_logs_warning_when_prev_close_is_zero(container_with_broker, kis_client_mock, caplog):
    kis_client_mock.get_prev_close = AsyncMock(return_value=Decimal("0"))
    client = TestClient(create_app(container_with_broker))
    with caplog.at_level("WARNING"):
        client.get("/balance")
    assert any("전일 종가가 비정상" in record.message for record in caplog.records)


def test_balance_day_change_null_for_overseas_symbol(container_with_broker, store, kis_client_mock):
    """KIS 국내 시세 조회 범위 밖(해외 종목)이면 day_change는 결측이어야 한다."""
    bus = EventBus()
    risk = RiskManager(bus=bus)
    broker = MagicMock()
    broker.get_balance = AsyncMock(
        return_value=BalanceInfo(
            items=[
                BalanceItem(
                    symbol="AAPL",
                    symbol_name="Apple",
                    qty=1,
                    avg_price=150.0,
                    current_price=160.0,
                    eval_amount=160.0,
                    profit_loss=10.0,
                    profit_loss_rate=6.67,
                    market=Market.OVERSEAS,
                ),
            ],
            total_eval_amount_krw=160.0,
            total_profit_loss_krw=10.0,
            deposit=0.0,
        )
    )
    container = AppContainer(
        store=store,
        risk=risk,
        bus=bus,
        env="vps",
        market="domestic",
        broker=broker,
        kis_client=kis_client_mock,
    )
    client = TestClient(create_app(container))
    data = client.get("/balance").json()
    item = data["items"][0]
    assert item["day_change"] is None
    kis_client_mock.get_prev_close.assert_not_awaited()


def test_balance_day_change_mixed_success_across_holdings(store):
    """보유 종목 여럿 중 하나만 KIS 조회에 실패해도 나머지는 정상 반환돼야 한다."""
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

    async def _get_prev_close(symbol: str) -> Decimal:
        if symbol == "005930":
            return Decimal("74200")
        raise RuntimeError("KIS 조회 실패 for this symbol only")

    kis_client = MagicMock()
    kis_client.get_prev_close = AsyncMock(side_effect=_get_prev_close)

    container = AppContainer(
        store=store, risk=risk, bus=bus, env="vps", market="domestic", broker=broker, kis_client=kis_client
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
