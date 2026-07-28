"""GET /market-stocks, /market-stocks/summary 엔드포인트 테스트."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.api.deps import AppContainer
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
def container(store):
    bus = EventBus()
    risk = RiskManager(bus=bus)
    return AppContainer(store=store, risk=risk, bus=bus, env="vps", market="domestic")


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


async def _insert_market_data(
    store: StateStore,
    symbol: str,
    price: float,
    change_rate: float,
    trading_volume: int,
    trading_value: int,
    timestamp: str,
) -> None:
    await store.conn.execute(
        """
        INSERT INTO market_data
            (symbol, price, change_rate, trading_volume, trading_value, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (symbol, price, change_rate, trading_volume, trading_value, timestamp),
    )
    await store.conn.commit()


# ============================================================================
# GET /market-stocks
# ============================================================================


def test_market_stocks_returns_404_when_no_data(client):
    res = client.get("/market-stocks")
    assert res.status_code == 404
    assert "마켓 데이터가 없습니다" in res.json()["detail"]


async def test_market_stocks_returns_200_with_data(store, client):
    # 구 타임스탬프(제외되어야 함)와 최신 타임스탬프(포함) 데이터를 함께 넣어
    # "최신 타임스탬프만 조회" 동작을 검증한다.
    await _insert_market_data(store, "000001", 1000.0, -0.01, 100, 100_000, "2024-07-24T09:00:00")
    await _insert_market_data(
        store, "005930", 70500.0, 0.71, 17_500_000, 1_234_567_890, "2024-07-24T10:30:00"
    )
    await _insert_market_data(
        store, "000660", 200000.0, 0.30, 5_000_000, 900_000_000, "2024-07-24T10:30:00"
    )

    res = client.get("/market-stocks?sort_by=trading_value&limit=10")
    assert res.status_code == 200
    body = res.json()
    assert body["timestamp"] == "2024-07-24T10:30:00"
    assert len(body["data"]) == 2  # 구 타임스탬프 종목은 제외

    symbols = [item["symbol"] for item in body["data"]]
    assert "000001" not in symbols
    # trading_value DESC 정렬 확인
    assert symbols == ["005930", "000660"]

    item = body["data"][0]
    assert item["symbol"] == "005930"
    assert item["price"] == 70500.0
    assert item["change_rate"] == 0.71
    assert item["trading_volume"] == 17_500_000
    assert item["trading_value"] == 1_234_567_890
    assert item["timestamp"] == "2024-07-24T10:30:00"


@pytest.mark.parametrize(
    "sort_by,expected_order",
    [
        ("trading_value", ["C", "A", "B"]),
        ("volume", ["B", "A", "C"]),
        ("uptrend", ["C", "A", "B"]),
        ("downtrend", ["B", "A", "C"]),
    ],
)
async def test_market_stocks_sort_by_options(store, client, sort_by, expected_order):
    ts = "2024-07-24T10:30:00"
    # symbol, price, change_rate, trading_volume, trading_value
    await _insert_market_data(store, "A", 100.0, 0.0, 50, 500, ts)
    await _insert_market_data(store, "B", 100.0, -1.0, 90, 300, ts)
    await _insert_market_data(store, "C", 100.0, 1.0, 10, 700, ts)

    res = client.get(f"/market-stocks?sort_by={sort_by}&limit=10")
    assert res.status_code == 200
    symbols = [item["symbol"] for item in res.json()["data"]]
    assert symbols == expected_order


async def test_market_stocks_limit_applied(store, client):
    ts = "2024-07-24T10:30:00"
    for i in range(5):
        await _insert_market_data(store, f"S{i}", 100.0, 0.0, 10, 1000 - i, ts)

    res = client.get("/market-stocks?sort_by=trading_value&limit=2")
    assert res.status_code == 200
    assert len(res.json()["data"]) == 2


def test_market_stocks_limit_out_of_range_returns_422(client):
    assert client.get("/market-stocks?limit=0").status_code == 422
    assert client.get("/market-stocks?limit=101").status_code == 422


def test_market_stocks_invalid_sort_by_returns_422(client):
    # sort_by는 Literal이라 FastAPI가 핸들러 진입 전에 422로 거부한다.
    res = client.get("/market-stocks?sort_by=not-a-real-option")
    assert res.status_code == 422


async def test_market_stocks_db_failure_returns_503(store, client):
    await _insert_market_data(store, "005930", 70500.0, 0.71, 100, 1000, "2024-07-24T10:30:00")
    await store.close()  # StateStore.conn이 이제 RuntimeError를 던짐

    res = client.get("/market-stocks")
    assert res.status_code == 503


# ============================================================================
# GET /market-stocks/summary
# ============================================================================


def test_market_summary_returns_404_when_no_data(client):
    res = client.get("/market-stocks/summary")
    assert res.status_code == 404


async def test_market_summary_returns_200_with_categories(store, client):
    ts = "2024-07-24T10:30:00"
    await _insert_market_data(store, "005930", 70500.0, 0.71, 17_500_000, 1_234_567_890, ts)
    await _insert_market_data(store, "000660", 200000.0, 1.50, 5_000_000, 900_000_000, ts)

    res = client.get("/market-stocks/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["timestamp"] == ts
    assert set(body["categories"].keys()) == {"top_trading_value", "top_volume", "top_gainers"}

    top_value = body["categories"]["top_trading_value"]
    assert top_value["label"] == "거래대금"
    assert top_value["stocks"][0]["symbol"] == "005930"

    top_gainers = body["categories"]["top_gainers"]
    assert top_gainers["stocks"][0]["symbol"] == "000660"  # change_rate 1.50 > 0.71


async def test_market_summary_db_failure_returns_503(store, client):
    await _insert_market_data(store, "005930", 70500.0, 0.71, 100, 1000, "2024-07-24T10:30:00")
    await store.close()

    res = client.get("/market-stocks/summary")
    assert res.status_code == 503
