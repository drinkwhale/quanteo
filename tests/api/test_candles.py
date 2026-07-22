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


# ============================================================================
# 심볼 검증
# ============================================================================


def test_candles_rejects_empty_symbol(client):
    """빈 심볼 — 400 반환."""
    res = client.get("/candles?symbol=&interval=1d&count=100")
    assert res.status_code == 400
    assert "심볼" in res.json()["detail"]


def test_candles_rejects_whitespace_symbol(client):
    """공백만 있는 심볼 — 400 반환."""
    res = client.get("/candles?symbol=%20%20%20&interval=1d&count=100")
    assert res.status_code == 400
    assert "심볼" in res.json()["detail"]


def test_candles_rejects_symbol_with_special_chars(client):
    """특수문자 포함 심볼 — 400 반환."""
    res = client.get("/candles?symbol=005@930&interval=1d&count=100")
    assert res.status_code == 400
    assert "심볼 형식" in res.json()["detail"]


def test_candles_rejects_symbol_too_long(client):
    """심볼이 20자 초과 — 400 반환."""
    long_symbol = "A" * 21
    res = client.get(f"/candles?symbol={long_symbol}&interval=1d&count=100")
    assert res.status_code == 400
    assert "심볼 형식" in res.json()["detail"]


def test_candles_accepts_valid_symbols(client_with_broker):
    """유효한 심볼들 — 200 반환."""
    client, mock_broker = client_with_broker
    mock_broker.get_candles = AsyncMock(return_value=[])

    for symbol in ["005930", "AAPL", "BRK-B", "005930-A", "A1"]:
        res = client.get(f"/candles?symbol={symbol}&interval=1d&count=100")
        assert res.status_code == 200, f"심볼 {symbol!r} 실패"


# ============================================================================
# before 날짜 검증
# ============================================================================


def test_candles_accepts_before_full_iso8601(client_with_broker):
    """완전한 ISO 8601 형식 (타임존 포함) — 200 반환."""
    client, mock_broker = client_with_broker
    mock_broker.get_candles = AsyncMock(return_value=[])

    for before_val in [
        "2024-01-15T14:30:00Z",
        "2024-01-15T14:30:00.123Z",
        "2024-01-15T14:30:00+09:00",
        "2024-01-15T14:30:00-05:00",
    ]:
        res = client.get(
            f"/candles?symbol=005930&interval=1d&count=100&before={before_val}"
        )
        assert res.status_code == 200, f"before={before_val!r} 실패"


def test_candles_accepts_before_date_only(client_with_broker):
    """날짜만 (시간 없음) — 200 반환."""
    client, mock_broker = client_with_broker
    mock_broker.get_candles = AsyncMock(return_value=[])

    res = client.get(
        "/candles?symbol=005930&interval=1d&count=100&before=2024-01-15"
    )
    assert res.status_code == 200


def test_candles_rejects_before_invalid_format(client):
    """잘못된 날짜 형식 — 400 반환."""
    invalid_befores = [
        "2024/01/15",  # 슬래시 구분자
        "15-01-2024",  # 날짜 순서 뒤바뀜
        "2024-01-15 14:30:00",  # T 대신 공백
        "2024-1-15",  # 월/일이 0-패딩 없음
        "invalid",  # 완전히 다른 형식
    ]

    for before_val in invalid_befores:
        res = client.get(
            f"/candles?symbol=005930&interval=1d&count=100&before={before_val}"
        )
        assert res.status_code == 400, f"before={before_val!r} 검증 실패"
        assert "before" in res.json()["detail"]


def test_candles_rejects_before_invalid_date(client):
    """존재하지 않는 날짜값 — 400 반환."""
    invalid_dates = [
        "2024-02-30",  # 2월 30일 없음
        "2024-13-01",  # 13월 없음
        "2024-01-32",  # 31일까지만 가능
    ]

    for before_val in invalid_dates:
        res = client.get(
            f"/candles?symbol=005930&interval=1d&count=100&before={before_val}"
        )
        assert res.status_code == 400, f"before={before_val!r} 날짜값 검증 실패"
        assert "before" in res.json()["detail"]


def test_candles_rejects_empty_before(client):
    """빈 before 값 — 400 반환."""
    res = client.get("/candles?symbol=005930&interval=1d&count=100&before=")
    assert res.status_code == 400
    assert "before" in res.json()["detail"]


# ============================================================================
# 응답 데이터 검증
# ============================================================================


def test_candles_handles_non_list_response(client_with_broker):
    """어댑터가 리스트 아닌 응답 반환 — 502 반환."""
    client, mock_broker = client_with_broker

    async def mock_error(*args, **kwargs):
        return {}  # 리스트가 아님

    mock_broker.get_candles = AsyncMock(side_effect=mock_error)

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 502
    assert "응답 형식" in res.json()["detail"]


def test_candles_handles_malformed_candle_data(client_with_broker):
    """캔들 객체 변환 실패 (필드 누락) — 502 반환."""
    client, mock_broker = client_with_broker

    class BadCandle:
        # timestamp 필드 누락
        open = 100.0
        high = 105.0
        low = 99.0
        close = 102.0
        volume = 1000

    mock_broker.get_candles = AsyncMock(return_value=[BadCandle()])

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 502
    assert "변환" in res.json()["detail"]


def test_candles_handles_invalid_numeric_candle_field(client_with_broker):
    """캔들 숫자 필드가 변환 불가능 — 502 반환."""
    client, mock_broker = client_with_broker

    class BadCandle:
        timestamp = datetime(2024, 1, 1)
        open = "not_a_number"  # 숫자 아님
        high = 105.0
        low = 99.0
        close = 102.0
        volume = 1000

    mock_broker.get_candles = AsyncMock(return_value=[BadCandle()])

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 502
    assert "변환" in res.json()["detail"]


# ============================================================================
# 예외 분류 처리
# ============================================================================


def test_candles_handles_runtime_error(client_with_broker):
    """RuntimeError (API 응답 구조 오류) — 502 반환."""
    client, mock_broker = client_with_broker

    async def mock_error(*args, **kwargs):
        raise RuntimeError("API 응답 구조 오류")

    mock_broker.get_candles = AsyncMock(side_effect=mock_error)

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 502
    assert "오류" in res.json()["detail"]


def test_candles_handles_connection_error(client_with_broker):
    """ConnectionError (네트워크 오류) — 502 반환."""
    client, mock_broker = client_with_broker

    async def mock_error(*args, **kwargs):
        raise ConnectionError("네트워크 연결 실패")

    mock_broker.get_candles = AsyncMock(side_effect=mock_error)

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 502
    assert "연결" in res.json()["detail"]


def test_candles_handles_timeout_error(client_with_broker):
    """TimeoutError (타임아웃) — 502 반환."""
    client, mock_broker = client_with_broker

    async def mock_error(*args, **kwargs):
        raise TimeoutError("요청 타임아웃")

    mock_broker.get_candles = AsyncMock(side_effect=mock_error)

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 502
    assert "연결" in res.json()["detail"]


def test_candles_handles_unexpected_exception(client_with_broker):
    """예기치 못한 예외 — 502 반환."""
    client, mock_broker = client_with_broker

    async def mock_error(*args, **kwargs):
        raise KeyError("예상 오류")

    mock_broker.get_candles = AsyncMock(side_effect=mock_error)

    res = client.get("/candles?symbol=005930&interval=1d&count=100")
    assert res.status_code == 502
    assert "예상 오류" in res.json()["detail"]
