"""screener/pipeline/scorer.py 단위 테스트."""

from __future__ import annotations

import pandas as pd
import pytest

from screener.data.collectors.dart_client import FinancialStatement, YearlyFinancials
from screener.pipeline.scorer import (
    build_financial_features,
    calculate_altman_z_score,
    calculate_weighted_score,
    score_cashflow,
    score_growth,
    score_profitability,
    score_stability,
    score_valuation,
)


class TestBuildFinancialFeatures:
    def test_computes_yoy_from_two_years(self) -> None:
        stmt = FinancialStatement(
            corp_code="X",
            years=[
                YearlyFinancials(year=2026, revenue=1100, operating_income=220, net_income=110),
                YearlyFinancials(year=2025, revenue=1000, operating_income=200, net_income=100),
            ],
        )

        df = build_financial_features({"A": stmt})

        row = df.iloc[0]
        assert row["revenue_yoy"] == pytest.approx(0.1)
        assert row["operating_income_yoy"] == pytest.approx(0.1)
        assert row["net_income_yoy"] == pytest.approx(0.1)

    def test_single_year_leaves_yoy_none(self) -> None:
        stmt = FinancialStatement(
            corp_code="X", years=[YearlyFinancials(year=2026, revenue=1000)]
        )

        df = build_financial_features({"A": stmt})

        assert df.iloc[0]["revenue_yoy"] is None

    def test_no_years_produces_row_of_nulls(self) -> None:
        stmt = FinancialStatement(corp_code="X", years=[])

        df = build_financial_features({"A": stmt})

        assert df.iloc[0]["ticker"] == "A"

    def test_altman_z_always_none(self) -> None:
        assert calculate_altman_z_score(pd.Series({"revenue": 1000})) is None


def _scoring_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "sector": ["tech", "tech", "tech", "tech"],
            "revenue_yoy": [0.3, 0.2, 0.1, None],
            "operating_income_yoy": [0.3, 0.2, 0.1, None],
            "net_income_yoy": [0.3, 0.2, 0.1, None],
            "roe": [0.2, 0.15, 0.1, None],
            "operating_margin": [0.3, 0.2, 0.1, None],
            "operating_margin_trend": [0.05, 0.0, -0.05, None],
            "cfo_to_net_income": [1.2, 1.0, 0.8, None],
            "fcf_conversion": [0.2, 0.15, 0.1, None],
            "debt_ratio": [0.5, 1.0, 2.0, None],
            "current_ratio": [2.0, 1.5, 1.0, None],
            "per": [8.0, 12.0, 20.0, None],
            "pbr": [0.8, 1.2, 2.0, None],
        }
    )


class TestScoreAxes:
    def test_score_growth_ranks_higher_growth_higher(self) -> None:
        result = score_growth(_scoring_df())

        assert result.iloc[0] > result.iloc[1] > result.iloc[2]

    def test_score_profitability_ranks_higher_roe_higher(self) -> None:
        result = score_profitability(_scoring_df())

        assert result.iloc[0] >= result.iloc[1] >= result.iloc[2]

    def test_score_cashflow(self) -> None:
        result = score_cashflow(_scoring_df())

        assert result.iloc[0] >= result.iloc[2]

    def test_score_stability_low_debt_ratio_scores_higher(self) -> None:
        result = score_stability(_scoring_df())

        # A has lowest debt_ratio(0.5) and highest current_ratio(2.0) → best
        assert result.iloc[0] >= result.iloc[2]

    def test_score_valuation_reverse_normalized(self) -> None:
        """PER/PBR가 낮을수록(A) 고득점, 높을수록(C) 저득점이어야 한다."""
        result = score_valuation(_scoring_df())

        assert result.iloc[0] > result.iloc[2]

    def test_missing_values_default_to_median_not_excluded(self) -> None:
        result = score_growth(_scoring_df())

        assert not pd.isna(result.iloc[3])  # D(전부 결측)도 중앙값 기반 점수를 받는다


class TestCalculateWeightedScore:
    def test_equal_weights_average(self) -> None:
        scores = pd.DataFrame(
            {
                "growth": [4, 2],
                "profitability": [4, 2],
                "cashflow": [4, 2],
                "stability": [4, 2],
                "valuation": [4, 2],
            }
        )

        result = calculate_weighted_score(scores)

        assert result.iloc[0] == pytest.approx(4)
        assert result.iloc[1] == pytest.approx(2)

    def test_custom_weights(self) -> None:
        scores = pd.DataFrame(
            {
                "growth": [5, 1],
                "profitability": [1, 1],
                "cashflow": [1, 1],
                "stability": [1, 1],
                "valuation": [1, 1],
            }
        )
        weights = {
            "growth": 1.0,
            "profitability": 0.0,
            "cashflow": 0.0,
            "stability": 0.0,
            "valuation": 0.0,
        }

        result = calculate_weighted_score(scores, weights)

        assert result.iloc[0] == pytest.approx(5)
        assert result.iloc[1] == pytest.approx(1)
