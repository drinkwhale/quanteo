"""screener/pipeline/ranker.py 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pandas as pd
import pytest

from screener.data.collectors.dart_client import Disclosure
from screener.pipeline.ranker import (
    earnings_surprise_flag,
    foreign_institution_streak,
    has_recent_disclosure,
    rank_top_n,
    volume_surge_ratio,
)


class TestRankTopN:
    def test_sorts_by_weighted_score_descending(self) -> None:
        df = pd.DataFrame({"ticker": ["A", "B", "C"], "weighted_score": [3.0, 5.0, 1.0]})

        result = rank_top_n(df, top_n=10)

        assert result["ticker"].tolist() == ["B", "A", "C"]
        assert result["rank"].tolist() == [1, 2, 3]

    def test_limits_to_top_n(self) -> None:
        df = pd.DataFrame({"ticker": list("ABCDE"), "weighted_score": [5, 4, 3, 2, 1]})

        result = rank_top_n(df, top_n=2)

        assert len(result) == 2
        assert result["ticker"].tolist() == ["A", "B"]

    def test_tie_broken_by_foreign_institution_streak(self) -> None:
        df = pd.DataFrame(
            {
                "ticker": ["A", "B"],
                "weighted_score": [3.0, 3.0],
                "foreign_institution_streak": [2, 5],
            }
        )

        result = rank_top_n(df, top_n=10)

        assert result["ticker"].tolist() == ["B", "A"]

    def test_second_tiebreak_volume_surge_ratio(self) -> None:
        df = pd.DataFrame(
            {
                "ticker": ["A", "B"],
                "weighted_score": [3.0, 3.0],
                "foreign_institution_streak": [2, 2],
                "volume_surge_ratio": [1.0, 3.0],
            }
        )

        result = rank_top_n(df, top_n=10)

        assert result["ticker"].tolist() == ["B", "A"]


class TestForeignInstitutionStreak:
    @pytest.mark.asyncio
    async def test_counts_consecutive_days(self) -> None:
        client = AsyncMock()
        client.fetch_investor_trading.return_value = pd.DataFrame(
            {"ticker": ["A"], "foreign_net": [100], "institution_net": [100]}
        )

        result = await foreign_institution_streak(client, ["A"], "20260721", max_days=3)

        assert result["A"] == 3

    @pytest.mark.asyncio
    async def test_stops_at_first_break(self) -> None:
        client = AsyncMock()
        # 20260721(화) → 20260717(금) 순으로 호출됨 (역순)
        call_results = {
            "20260721": pd.DataFrame({"ticker": ["A"], "foreign_net": [100], "institution_net": [100]}),
            "20260720": pd.DataFrame({"ticker": ["A"], "foreign_net": [-100], "institution_net": [100]}),
            "20260717": pd.DataFrame({"ticker": ["A"], "foreign_net": [100], "institution_net": [100]}),
        }

        async def side_effect(date):
            return call_results.get(date, pd.DataFrame())

        client.fetch_investor_trading.side_effect = side_effect

        result = await foreign_institution_streak(client, ["A"], "20260721", max_days=5)

        assert result["A"] == 1  # 20260721만 카운트, 20260720에서 끊김


class TestVolumeSurgeRatio:
    @pytest.mark.asyncio
    async def test_ratio_computed_against_average(self) -> None:
        client = AsyncMock()
        client.fetch_universe.return_value = pd.DataFrame({"ticker": ["A"], "volume": [2000.0]})
        universe = pd.DataFrame({"ticker": ["A"], "volume": [4000.0]})

        result = await volume_surge_ratio(client, universe, "20260721", days=1)

        assert result["A"] == pytest.approx(2.0)


class TestDisclosureFlags:
    def test_earnings_surprise_flag_true_on_correction(self) -> None:
        disclosures = {
            "A": [
                Disclosure(
                    corp_code="A",
                    title="영업(잠정)실적(정정)",
                    url="",
                    report_type="실적정정",
                    published_kst=None,  # type: ignore[arg-type]
                )
            ],
            "B": [],
        }

        result = earnings_surprise_flag(disclosures)

        assert bool(result["A"]) is True
        assert bool(result["B"]) is False

    def test_has_recent_disclosure(self) -> None:
        disclosures = {
            "A": [
                Disclosure(
                    corp_code="A",
                    title="유상증자결정",
                    url="",
                    report_type="유상증자결정",
                    published_kst=None,  # type: ignore[arg-type]
                )
            ],
            "B": [],
        }

        result = has_recent_disclosure(disclosures)

        assert bool(result["A"]) is True
        assert bool(result["B"]) is False
