"""Toss 캔들 데이터 소스 & 캐싱 테스트.

캐시 히트/미스, API 장애 시 예외 전파, fetch_range 동작 검증.
"""

from __future__ import annotations

import csv
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.backtest.toss_data_source import (
    CSVBacktestDataSource,
    TossBacktestDataSource,
    _CacheDB,
    _candle_to_dict,
    _dict_to_candle,
)
from core.marketdata.models import Candle


# ============================================================================
# 픽스처
# ============================================================================

_TS_BASE = datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)


def _make_candle(i: int, symbol: str = "000660") -> Candle:
    return Candle(
        symbol=symbol,
        open=100.0 + i,
        high=101.0 + i,
        low=99.0 + i,
        close=100.5 + i,
        volume=1000,
        timestamp=_TS_BASE + timedelta(days=i),
        market="domestic",
        interval="1d",
    )


class _FakeTossCandle:
    def __init__(self, i: int) -> None:
        self.open_price = 100.0 + i
        self.high_price = 101.0 + i
        self.low_price = 99.0 + i
        self.close_price = 100.5 + i
        self.volume = 1000
        self.timestamp = _TS_BASE + timedelta(days=i)
        self.currency = "KRW"


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_cache.db"


@pytest.fixture
def mock_rest_client():
    client = AsyncMock()
    return client


@pytest.fixture
def data_source(mock_rest_client, tmp_db):
    return TossBacktestDataSource(mock_rest_client, cache_db_path=tmp_db)


# ============================================================================
# 캐시 히트/미스
# ============================================================================


@pytest.mark.asyncio
async def test_cache_miss_calls_api(data_source, mock_rest_client):
    """캐시 없으면 API 호출."""
    mock_rest_client.get_candles.return_value = [_FakeTossCandle(i) for i in range(3)]

    result = await data_source.get_candles("000660", "1d", count=3)

    mock_rest_client.get_candles.assert_called_once()
    assert len(result) == 3


@pytest.mark.asyncio
async def test_cache_hit_no_api_call(data_source, mock_rest_client):
    """캐시 있으면 API 미호출."""
    mock_rest_client.get_candles.return_value = [_FakeTossCandle(i) for i in range(3)]

    # 첫 번째 호출 — API 호출
    await data_source.get_candles("000660", "1d", count=3)
    assert mock_rest_client.get_candles.call_count == 1

    # 두 번째 호출 — 캐시 히트
    result = await data_source.get_candles("000660", "1d", count=3)
    assert mock_rest_client.get_candles.call_count == 1  # 추가 API 호출 없음
    assert len(result) == 3


@pytest.mark.asyncio
async def test_cache_returns_same_data(data_source, mock_rest_client):
    """캐시 반환 데이터가 첫 호출 데이터와 동일."""
    mock_rest_client.get_candles.return_value = [_FakeTossCandle(0)]

    first = await data_source.get_candles("000660", "1d", count=1)
    second = await data_source.get_candles("000660", "1d", count=1)

    assert first[0].close == second[0].close
    assert first[0].timestamp == second[0].timestamp


# ============================================================================
# API 장애 처리
# ============================================================================


@pytest.mark.asyncio
async def test_api_failure_raises_when_no_cache(data_source, mock_rest_client):
    """캐시 없고 API 실패 시 예외 전파."""
    mock_rest_client.get_candles.side_effect = RuntimeError("API 연결 실패")

    with pytest.raises(RuntimeError, match="API 연결 실패"):
        await data_source.get_candles("000660", "1d", count=3)


@pytest.mark.asyncio
async def test_api_failure_uses_cache_when_available(tmp_db, mock_rest_client):
    """첫 호출 성공 후 캐시 저장 → API 장애 시 캐시 반환 (TTL 내)."""
    # 이 테스트는 TossBacktestDataSource가 캐시를 우선 반환함으로써
    # 두 번째 호출에서 API를 호출하지 않음을 검증
    mock_rest_client.get_candles.return_value = [_FakeTossCandle(0)]
    source = TossBacktestDataSource(mock_rest_client, cache_db_path=tmp_db)

    await source.get_candles("000660", "1d", count=1)  # 캐시 저장

    mock_rest_client.get_candles.side_effect = RuntimeError("API DOWN")
    result = await source.get_candles("000660", "1d", count=1)  # 캐시 반환
    assert len(result) == 1


# ============================================================================
# fetch_range
# ============================================================================


@pytest.mark.asyncio
async def test_fetch_range_combines_batches(tmp_db, mock_rest_client):
    """fetch_range: start_date 이전 도달 시 루프 중단."""
    start = _TS_BASE + timedelta(days=5)
    end = _TS_BASE + timedelta(days=10)

    # 첫 배치: days 8~10 (end 기준 before)
    # 두 번째 배치: days 5~7
    # 세 번째 배치: days 2~4 (start 이전 포함 → 루프 중단)
    call_count = 0

    async def fake_get_candles(symbol, interval="1d", count=200, before=None, adjusted=True):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [_FakeTossCandle(i) for i in range(8, 11)]
        elif call_count == 2:
            return [_FakeTossCandle(i) for i in range(5, 8)]
        else:
            return [_FakeTossCandle(i) for i in range(2, 5)]  # start 이전 포함

    mock_rest_client.get_candles.side_effect = fake_get_candles
    source = TossBacktestDataSource(mock_rest_client, cache_db_path=tmp_db)

    result = await source.fetch_range("000660", "1d", start_date=start, end_date=end)

    # start 이상 end 이하 캔들만 포함
    for c in result:
        assert c.timestamp >= start


@pytest.mark.asyncio
async def test_fetch_range_sorted_ascending(tmp_db, mock_rest_client):
    """fetch_range 결과는 오래된 순 정렬."""
    mock_rest_client.get_candles.return_value = [_FakeTossCandle(i) for i in [3, 1, 2]]
    source = TossBacktestDataSource(mock_rest_client, cache_db_path=tmp_db)

    result = await source.fetch_range("000660", "1d")
    timestamps = [c.timestamp for c in result]
    assert timestamps == sorted(timestamps)


# ============================================================================
# CSV 데이터 소스
# ============================================================================


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "candles.csv"
    rows = [
        {
            "symbol": "000660",
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 1000,
            "timestamp": (_TS_BASE + timedelta(days=i)).isoformat(),
            "market": "domestic",
            "interval": "1d",
        }
        for i in range(10)
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.mark.asyncio
async def test_csv_get_candles(csv_file):
    """CSV에서 캔들 반환."""
    source = CSVBacktestDataSource(csv_file)
    result = await source.get_candles("000660", count=5)
    assert len(result) == 5


@pytest.mark.asyncio
async def test_csv_fetch_range(csv_file):
    """fetch_range로 날짜 범위 필터링."""
    source = CSVBacktestDataSource(csv_file)
    start = _TS_BASE + timedelta(days=3)
    end = _TS_BASE + timedelta(days=6)

    result = await source.fetch_range("000660", start_date=start, end_date=end)

    for c in result:
        assert start <= c.timestamp <= end


# ============================================================================
# 직렬화 라운드트립
# ============================================================================


def test_candle_serialization_roundtrip():
    """Candle → dict → Candle 라운드트립."""
    original = _make_candle(0)
    d = _candle_to_dict(original)
    restored = _dict_to_candle(d)

    assert restored.symbol == original.symbol
    assert restored.close == original.close
    assert restored.timestamp == original.timestamp
