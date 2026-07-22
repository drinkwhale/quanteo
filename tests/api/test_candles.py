"""캔들 차트 데이터 조회 엔드포인트 테스트."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from core.marketdata.models import Candle
from core.api.app import create_app
from core.api.deps import AppContainer
from core.events.bus import EventBus
from core.risk.manager import RiskManager
from core.store.db import StateStore


@pytest.fixture
async def container(tmp_path):
    store = StateStore(db_path=str(tmp_path / "test.db"))
    await store.open()
    bus = EventBus()
    risk = RiskManager(bus=bus)
    c = AppContainer(store=store, risk=risk, bus=bus, env="vps", market="domestic")
    yield c
    await store.close()


@pytest.fixture
def client_with_broker(container):
    # Mock broker 주입
    mock_broker = MagicMock()
    container.broker = mock_broker
    return TestClient(create_app(container)), mock_broker


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


# ============================================================================
# GET /candles
# ============================================================================


def test_candles_returns_200_with_data(client_with_broker):
    """정상 응답 — 캔들 데이터 반환."""
    client, mock_broker = client_with_broker
    candles = [
        Candle(
            symbol="005930",
            open=100.0,
            high=105.0,
            low=99.0,
            close=102.0,
            volume=1000,
            timestamp=datetime(2024, 1, 1, 9, 30),
            market="domestic",
        ),
        Candle(
            symbol="005930",
            open=102.0,
            high=110.0,
            low=100.0,
            close=108.0,
            volume=2000,
            timestamp=datetime(2024, 1, 2, 9, 30),
            market="domestic",
        ),
    ]

    mock_broker.get_candles = AsyncMock(return_value=candles)

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert len(body["items"]) == 2
    assert body["items"][0]["open"] == 100.0
    assert body["items"][0]["close"] == 102.0


def test_candles_validates_interval(client):
    """interval 검증 — 잘못된 값 시 422 반환."""
    res = client.get("/candles?symbol=005930&interval=5m")
    assert res.status_code == 422


def test_candles_enforces_count_limit(client):
    """count 상한 검증 — 200 초과 시 422 반환."""
    res = client.get("/candles?symbol=005930&interval=1d&count=201")
    assert res.status_code == 422


def test_candles_accepts_count_min(client):
    """count 최소값 검증 — 0 이하는 422."""
    res = client.get("/candles?symbol=005930&interval=1d&count=0")
    assert res.status_code == 422


def test_candles_503_when_broker_none(client):
    """브로커 미초기화 — 503 반환."""
    client.app.state.container.broker = None

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 503
    assert "브로커" in res.json()["detail"]


def test_candles_502_on_adapter_exception(client_with_broker):
    """어댑터 예외 — 502 반환."""
    client, mock_broker = client_with_broker

    async def mock_error(*args, **kwargs):
        raise RuntimeError("API 오류")

    mock_broker.get_candles = AsyncMock(side_effect=mock_error)

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 502
    assert "오류" in res.json()["detail"]


def test_candles_accepts_before_parameter(client_with_broker):
    """before 파라미터 전달 — 시그니처 검증."""
    client, mock_broker = client_with_broker
    candles = [
        Candle(
            symbol="005930",
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=0,
            timestamp=datetime(2024, 1, 1),
            market="domestic",
        )
    ]

    async def mock_get_candles(**kwargs):
        assert "before" in kwargs
        return candles

    mock_broker.get_candles = AsyncMock(side_effect=mock_get_candles)

    res = client.get("/candles?symbol=005930&interval=1d&count=10&before=2024-01-15")
    assert res.status_code == 200


def test_candles_accepts_adjusted_parameter(client_with_broker):
    """adjusted 파라미터 전달 — 기본값 True."""
    client, mock_broker = client_with_broker

    async def mock_get_candles(**kwargs):
        assert kwargs.get("adjusted") is True
        return []

    mock_broker.get_candles = AsyncMock(side_effect=mock_get_candles)

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 200


def test_candles_response_structure(client_with_broker):
    """응답 구조 검증 — CandleList 형식."""
    client, mock_broker = client_with_broker
    candles = [
        Candle(
            symbol="005930",
            open=100.0,
            high=105.0,
            low=99.0,
            close=102.0,
            volume=1000,
            timestamp=datetime(2024, 1, 1, 9, 30),
            market="domestic",
        )
    ]

    mock_broker.get_candles = AsyncMock(return_value=candles)

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 200
    body = res.json()

    assert "items" in body
    item = body["items"][0]
    assert "timestamp" in item
    assert "open" in item
    assert "high" in item
    assert "low" in item
    assert "close" in item
    assert "volume" in item
