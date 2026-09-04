"""Tests for KRX Open API client."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
import requests_mock

from screener.data.collectors.krx_openapi_client import KrxOpenApiClient


class TestKrxOpenApiClientInit:
    """Test client initialization and validation."""

    def test_init_raises_on_empty_key(self) -> None:
        with pytest.raises(ValueError, match="api_key must not be empty"):
            KrxOpenApiClient(api_key="")

    def test_init_valid_key(self, tmp_path: Path) -> None:
        client = KrxOpenApiClient(api_key="test_key", cache_dir=tmp_path)
        assert client._api_key == "test_key"
        assert client._cache_dir == tmp_path

    def test_session_auth_header(self, tmp_path: Path) -> None:
        """Test that session has AUTH_KEY header set."""
        client = KrxOpenApiClient(api_key="test_key", cache_dir=tmp_path)
        assert client._session.headers["AUTH_KEY"] == "test_key"
        assert client._session.headers["Content-Type"] == "application/json"


class TestKrxOpenApiClientFetch:
    """Test actual API fetch and data transformation logic."""

    @pytest.fixture
    def client(self, tmp_path: Path) -> KrxOpenApiClient:
        return KrxOpenApiClient(api_key="test_key", cache_dir=tmp_path)

    def test_fetch_universe_sync_success(self, client: KrxOpenApiClient) -> None:
        """Test successful fetch and DataFrame transformation."""
        with requests_mock.Mocker() as m:
            # Mock both KOSPI and KOSDAQ responses
            kospi_response = {
                "OutBlock_1": [
                    {
                        "ISU_CD": "005930",
                        "ISU_NM": "삼성전자",
                        "TDD_CLSPRC": 70000,
                        "ACC_TRDVOL": 1000000,
                        "MKTCAP": 500000000,
                        "LIST_SHRS": 50000000,
                    }
                ]
            }
            kosdaq_response = {
                "OutBlock_1": [
                    {
                        "ISU_CD": "007660",
                        "ISU_NM": "삼성디스플레이",
                        "TDD_CLSPRC": 50000,
                        "ACC_TRDVOL": 500000,
                        "MKTCAP": 300000000,
                        "LIST_SHRS": 30000000,
                    }
                ]
            }

            m.post(
                "https://openapi.krx.co.kr/api/sto/stk_bydd_trd",
                json=kospi_response,
                status_code=200,
            )
            m.post(
                "https://openapi.krx.co.kr/api/sto/ksq_bydd_trd",
                json=kosdaq_response,
                status_code=200,
            )

            df = client._fetch_universe_sync("20260903")

            assert not df.empty
            assert len(df) == 2
            assert "ticker" in df.columns
            assert "name" in df.columns
            assert "market" in df.columns
            assert "close" in df.columns
            assert (df["market"] == "KOSPI").sum() == 1
            assert (df["market"] == "KOSDAQ").sum() == 1
            assert df.loc[df["ticker"] == "005930", "name"].values[0] == "삼성전자"

    def test_fetch_universe_sync_one_market_fails(self, client: KrxOpenApiClient) -> None:
        """Test that partial failure (one market) returns available data."""
        with requests_mock.Mocker() as m:
            kospi_response = {
                "OutBlock_1": [
                    {
                        "ISU_CD": "005930",
                        "ISU_NM": "삼성전자",
                        "TDD_CLSPRC": 70000,
                        "ACC_TRDVOL": 1000000,
                        "MKTCAP": 500000000,
                        "LIST_SHRS": 50000000,
                    }
                ]
            }

            m.post(
                "https://openapi.krx.co.kr/api/sto/stk_bydd_trd",
                json=kospi_response,
                status_code=200,
            )
            m.post(
                "https://openapi.krx.co.kr/api/sto/ksq_bydd_trd",
                status_code=500,
                text="Internal Server Error",
            )

            df = client._fetch_universe_sync("20260903")

            # Should return KOSPI data despite KOSDAQ failure
            assert not df.empty
            assert len(df) == 1
            assert df.iloc[0]["market"] == "KOSPI"

    def test_fetch_universe_sync_all_markets_fail(self, client: KrxOpenApiClient) -> None:
        """Test that total failure returns empty DataFrame."""
        with requests_mock.Mocker() as m:
            m.post(
                "https://openapi.krx.co.kr/api/sto/stk_bydd_trd",
                status_code=401,
                text="Unauthorized",
            )
            m.post(
                "https://openapi.krx.co.kr/api/sto/ksq_bydd_trd",
                status_code=401,
                text="Unauthorized",
            )

            df = client._fetch_universe_sync("20260903")

            assert df.empty

    def test_fetch_universe_sync_malformed_json(self, client: KrxOpenApiClient) -> None:
        """Test graceful handling of malformed JSON response."""
        with requests_mock.Mocker() as m:
            # Empty OutBlock_1
            m.post(
                "https://openapi.krx.co.kr/api/sto/stk_bydd_trd",
                json={"OutBlock_1": None},
                status_code=200,
            )
            m.post(
                "https://openapi.krx.co.kr/api/sto/ksq_bydd_trd",
                json={"OutBlock_1": []},
                status_code=200,
            )

            df = client._fetch_universe_sync("20260903")

            # Should return empty rather than crash
            assert df.empty


class TestKrxOpenApiClientCache:
    """Test cache behavior."""

    @pytest.fixture
    def client(self, tmp_path: Path) -> KrxOpenApiClient:
        return KrxOpenApiClient(api_key="test_key", cache_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_fetch_universe_cache_hit(self, client: KrxOpenApiClient) -> None:
        """Test that cached data is returned without calling _fetch_universe_sync."""
        # Pre-write a cached file
        test_df = pd.DataFrame({
            "ticker": ["005930"],
            "name": ["삼성전자"],
            "market": ["KOSPI"],
            "close": [70000],
            "volume": [1000000],
            "market_cap": [500000000],
            "shares_outstanding": [50000000],
        })
        cache_path = client._cache_dir / "20260903_krx_universe.parquet"
        client._cache_dir.mkdir(parents=True, exist_ok=True)
        test_df.to_parquet(cache_path)

        with patch.object(client, "_fetch_universe_sync") as mock_fetch:
            df = await client.fetch_universe("20260903")

            # _fetch_universe_sync should NOT be called when cache exists
            mock_fetch.assert_not_called()
            assert not df.empty
            assert df.iloc[0]["ticker"] == "005930"

    @pytest.mark.asyncio
    async def test_fetch_universe_cache_write(self, client: KrxOpenApiClient) -> None:
        """Test that successful fetch result is cached."""
        with patch.object(client, "_fetch_universe_sync") as mock_fetch:
            test_df = pd.DataFrame({
                "ticker": ["005930"],
                "name": ["삼성전자"],
                "market": ["KOSPI"],
                "close": [70000],
                "volume": [1000000],
                "market_cap": [500000000],
                "shares_outstanding": [50000000],
            })
            mock_fetch.return_value = test_df

            await client.fetch_universe("20260903")

            # Check that cache file was written
            cache_path = client._cache_dir / "20260903_krx_universe.parquet"
            assert cache_path.exists()
            cached_df = pd.read_parquet(cache_path)
            assert len(cached_df) == 1

    @pytest.mark.asyncio
    async def test_fetch_universe_no_cache_on_empty(self, client: KrxOpenApiClient) -> None:
        """Test that empty results are not cached."""
        with patch.object(client, "_fetch_universe_sync") as mock_fetch:
            mock_fetch.return_value = pd.DataFrame()

            await client.fetch_universe("20260903")

            # Check that cache file was NOT written
            cache_path = client._cache_dir / "20260903_krx_universe.parquet"
            assert not cache_path.exists()


class TestKrxOpenApiClientStockInfo:
    """Test single stock info retrieval."""

    @pytest.fixture
    def client(self, tmp_path: Path) -> KrxOpenApiClient:
        return KrxOpenApiClient(api_key="test_key", cache_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_fetch_stock_info_found(self, client: KrxOpenApiClient) -> None:
        """Test fetching info for an existing ticker."""
        with patch.object(client, "_fetch_universe_sync") as mock_fetch:
            test_df = pd.DataFrame({
                "ticker": ["005930", "000660"],
                "name": ["삼성전자", "SK하이닉스"],
                "market": ["KOSPI", "KOSPI"],
                "close": [70000, 100000],
                "volume": [1000000, 500000],
                "market_cap": [500000000, 200000000],
                "shares_outstanding": [50000000, 20000000],
            })
            mock_fetch.return_value = test_df

            result = await client.fetch_stock_info("005930", "20260903")

            assert result is not None
            assert result["ticker"] == "005930"
            assert result["name"] == "삼성전자"
            assert result["close"] == 70000

    @pytest.mark.asyncio
    async def test_fetch_stock_info_not_found_in_universe(self, client: KrxOpenApiClient) -> None:
        """Test fetching info for a ticker not in universe."""
        with patch.object(client, "_fetch_universe_sync") as mock_fetch:
            test_df = pd.DataFrame({
                "ticker": ["005930"],
                "name": ["삼성전자"],
                "market": ["KOSPI"],
                "close": [70000],
                "volume": [1000000],
                "market_cap": [500000000],
                "shares_outstanding": [50000000],
            })
            mock_fetch.return_value = test_df

            result = await client.fetch_stock_info("999999", "20260903")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_stock_info_empty_universe(self, client: KrxOpenApiClient) -> None:
        """Test fetching info when universe fetch fails."""
        with patch.object(client, "_fetch_universe_sync") as mock_fetch:
            mock_fetch.return_value = pd.DataFrame()

            result = await client.fetch_stock_info("005930", "20260903")

            assert result is None
