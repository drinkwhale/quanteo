"""screener/pipeline/screener.py 단위 테스트."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from screener.pipeline.screener import (
    ScreenerConfig,
    compute_avg_trading_value_20d,
    filter_universe,
)


def _universe_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "market_cap": [100_000_000_000, 10_000_000_000, 60_000_000_000, 60_000_000_000],
            "volume": [1000, 1000, 0, 1000],
        }
    )


class TestScreenerConfig:
    def test_from_yaml_loads_universe_section(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.yaml"
        path.write_text(
            "universe:\n"
            "  min_market_cap: 1000\n"
            "  min_avg_trading_value_20d: 2000\n"
            "  exclude_administrative: false\n"
        )

        config = ScreenerConfig.from_yaml(path)

        assert config.min_market_cap == 1000
        assert config.min_avg_trading_value_20d == 2000
        assert config.exclude_administrative is False

    def test_defaults_when_section_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.yaml"
        path.write_text("report:\n  top_n: 10\n")

        config = ScreenerConfig.from_yaml(path)

        assert config.min_market_cap == 50_000_000_000


class TestFilterUniverse:
    def test_excludes_below_market_cap(self) -> None:
        config = ScreenerConfig(
            min_market_cap=50_000_000_000, min_avg_trading_value_20d=0, exclude_administrative=False
        )

        result = filter_universe(_universe_df(), config)

        assert "B" not in result["ticker"].values

    def test_excludes_halted_when_flag_enabled(self) -> None:
        config = ScreenerConfig(
            min_market_cap=0, min_avg_trading_value_20d=0, exclude_administrative=True
        )

        result = filter_universe(_universe_df(), config)

        assert "C" not in result["ticker"].values

    def test_keeps_halted_when_flag_disabled(self) -> None:
        config = ScreenerConfig(
            min_market_cap=0, min_avg_trading_value_20d=0, exclude_administrative=False
        )

        result = filter_universe(_universe_df(), config)

        assert "C" in result["ticker"].values

    def test_avg_trading_value_filter(self) -> None:
        config = ScreenerConfig(
            min_market_cap=0, min_avg_trading_value_20d=500, exclude_administrative=False
        )
        avg = pd.Series({"A": 1000, "B": 100, "C": 500, "D": 499})

        result = filter_universe(_universe_df(), config, avg_trading_value_20d=avg)

        assert set(result["ticker"]) == {"A", "C"}

    def test_boundary_market_cap_inclusive(self) -> None:
        config = ScreenerConfig(
            min_market_cap=60_000_000_000, min_avg_trading_value_20d=0, exclude_administrative=False
        )

        result = filter_universe(_universe_df(), config)

        assert "C" in result["ticker"].values  # 정확히 임계값과 같으면 포함

    def test_logs_excluded_counts(self, caplog) -> None:
        config = ScreenerConfig(
            min_market_cap=50_000_000_000, min_avg_trading_value_20d=0, exclude_administrative=False
        )

        with caplog.at_level("INFO"):
            filter_universe(_universe_df(), config)

        assert any("필터" in record.message for record in caplog.records)


class TestComputeAvgTradingValue20d:
    @pytest.mark.asyncio
    async def test_averages_across_trading_days(self) -> None:
        client = AsyncMock()
        client.fetch_universe.return_value = pd.DataFrame(
            {"ticker": ["A"], "trading_value": [1000.0]}
        )

        result = await compute_avg_trading_value_20d(client, "20260721", days=5)

        assert result["A"] == 1000.0
        assert client.fetch_universe.await_count == 5

    @pytest.mark.asyncio
    async def test_skips_weekends(self) -> None:
        client = AsyncMock()
        client.fetch_universe.return_value = pd.DataFrame(
            {"ticker": ["A"], "trading_value": [1000.0]}
        )

        # 2026-07-21은 화요일 — 5 거래일 뒤로 가면 주말 2일을 건너뛰어야 한다.
        await compute_avg_trading_value_20d(client, "20260721", days=5)

        called_dates = [call.args[0] for call in client.fetch_universe.await_args_list]
        for d in called_dates:
            weekday = pd.Timestamp(d).weekday()
            assert weekday < 5

    @pytest.mark.asyncio
    async def test_returns_empty_series_when_no_data(self) -> None:
        client = AsyncMock()
        client.fetch_universe.return_value = pd.DataFrame()

        result = await compute_avg_trading_value_20d(client, "20260721", days=3)

        assert result.empty
