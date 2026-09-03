"""Tests for KRX Open API client."""

from __future__ import annotations

import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import patch

from screener.data.collectors.krx_openapi_client import KrxOpenApiClient


class TestKrxOpenApiClient:
    """KRX API client tests."""

    @pytest.fixture
    def client(self, tmp_path: Path) -> KrxOpenApiClient:
        return KrxOpenApiClient(api_key="test_key", cache_dir=tmp_path)

    def test_init_raises_on_empty_key(self) -> None:
        with pytest.raises(ValueError, match="api_key must not be empty"):
            KrxOpenApiClient(api_key="")

    def test_init_valid_key(self) -> None:
        client = KrxOpenApiClient(api_key="valid_key")
        assert client._api_key == "valid_key"

    @pytest.mark.asyncio
    async def test_fetch_stock_info_not_found(self, client: KrxOpenApiClient) -> None:
        """Test fetch_stock_info returns None for missing ticker."""
        with patch.object(client, "_fetch_universe_sync") as mock_fetch:
            mock_fetch.return_value = pd.DataFrame()

            result = await client.fetch_stock_info("INVALID", "20260903")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_universe_calls_sync(self, client: KrxOpenApiClient) -> None:
        """Test fetch_universe delegates to sync method."""
        with patch.object(client, "_fetch_universe_sync") as mock_fetch:
            mock_fetch.return_value = pd.DataFrame({"ticker": ["005930"], "close": [100]})

            df = await client.fetch_universe("20260903")
            assert not df.empty
            mock_fetch.assert_called_once_with("20260903")

    def test_session_headers(self, client: KrxOpenApiClient) -> None:
        """Test session has correct headers set."""
        assert client._session.headers["AUTH_KEY"] == "test_key"
        assert client._session.headers["Content-Type"] == "application/json"
