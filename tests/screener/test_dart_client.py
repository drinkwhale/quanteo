"""DartClient 단위 테스트."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from screener.data.collectors.dart_client import DartClient


def _finstate_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _account_row(name: str, amount: str) -> dict:
    return {"account_nm": name, "thstrm_amount": amount}


class TestFetchFinancials:
    @pytest.mark.asyncio
    async def test_parses_core_accounts(self, tmp_path: Path) -> None:
        client = DartClient(api_key="test-key", cache_dir=tmp_path)
        df = _finstate_df(
            [
                _account_row("매출액", "1,000,000"),
                _account_row("영업이익", "200,000"),
                _account_row("당기순이익", "150,000"),
                _account_row("부채총계", "500,000"),
                _account_row("자본총계", "800,000"),
                _account_row("유동자산", "300,000"),
                _account_row("유동부채", "100,000"),
                _account_row("영업활동현금흐름", "250,000"),
            ]
        )
        mock_dart = MagicMock()
        mock_dart.finstate_all.return_value = df

        with patch("screener.data.collectors.dart_client.OpenDartReader", return_value=mock_dart):
            stmt = await client.fetch_financials("00164779", years=1)

        assert len(stmt.years) == 1
        yf = stmt.years[0]
        assert yf.revenue == 1_000_000
        assert yf.operating_income == 200_000
        assert yf.net_income == 150_000
        assert yf.total_equity == 800_000
        assert yf.operating_cash_flow == 250_000

    @pytest.mark.asyncio
    async def test_missing_account_returns_none(self, tmp_path: Path) -> None:
        client = DartClient(api_key="test-key", cache_dir=tmp_path)
        df = _finstate_df([_account_row("매출액", "1,000,000")])
        mock_dart = MagicMock()
        mock_dart.finstate_all.return_value = df

        with patch("screener.data.collectors.dart_client.OpenDartReader", return_value=mock_dart):
            stmt = await client.fetch_financials("00164779", years=1)

        assert stmt.years[0].operating_income is None

    @pytest.mark.asyncio
    async def test_api_exception_returns_empty_years(self, tmp_path: Path) -> None:
        client = DartClient(api_key="test-key", cache_dir=tmp_path)

        with patch(
            "screener.data.collectors.dart_client.OpenDartReader",
            side_effect=Exception("auth failed"),
        ):
            stmt = await client.fetch_financials("00164779", years=3)

        assert stmt.years == []

    @pytest.mark.asyncio
    async def test_per_year_failure_is_isolated(self, tmp_path: Path) -> None:
        client = DartClient(api_key="test-key", cache_dir=tmp_path)
        mock_dart = MagicMock()
        mock_dart.finstate_all.side_effect = [
            Exception("temporary error"),
            _finstate_df([_account_row("매출액", "1,000,000")]),
        ]

        with patch("screener.data.collectors.dart_client.OpenDartReader", return_value=mock_dart):
            stmt = await client.fetch_financials("00164779", years=2)

        assert len(stmt.years) == 1

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(self, tmp_path: Path) -> None:
        client = DartClient(api_key="test-key", cache_dir=tmp_path)
        df = _finstate_df([_account_row("매출액", "1,000,000")])
        mock_dart = MagicMock()
        mock_dart.finstate_all.return_value = df

        with patch("screener.data.collectors.dart_client.OpenDartReader", return_value=mock_dart):
            await client.fetch_financials("00164779", years=1)
            await client.fetch_financials("00164779", years=1)

        assert mock_dart.finstate_all.call_count == 1  # 두 번째 호출은 캐시 사용


class TestFetchRecentDisclosures:
    @pytest.mark.asyncio
    async def test_important_disclosure_included(self) -> None:
        client = DartClient(api_key="test-key")
        raw = pd.DataFrame(
            [{"report_nm": "유상증자결정", "rcept_dt": "20260701", "rcept_no": "1"}]
        )
        mock_dart = MagicMock()
        mock_dart.list.return_value = raw

        with patch("screener.data.collectors.dart_client.OpenDartReader", return_value=mock_dart):
            items = await client.fetch_recent_disclosures("00164779")

        assert len(items) == 1
        assert items[0].report_type == "유상증자결정"

    @pytest.mark.asyncio
    async def test_unimportant_disclosure_excluded(self) -> None:
        client = DartClient(api_key="test-key")
        raw = pd.DataFrame([{"report_nm": "분기보고서", "rcept_dt": "20260701", "rcept_no": "1"}])
        mock_dart = MagicMock()
        mock_dart.list.return_value = raw

        with patch("screener.data.collectors.dart_client.OpenDartReader", return_value=mock_dart):
            items = await client.fetch_recent_disclosures("00164779")

        assert items == []

    @pytest.mark.asyncio
    async def test_api_exception_returns_empty_list(self) -> None:
        client = DartClient(api_key="test-key")

        with patch(
            "screener.data.collectors.dart_client.OpenDartReader",
            side_effect=Exception("network error"),
        ):
            items = await client.fetch_recent_disclosures("00164779")

        assert items == []
