"""관심종목 필터링 로직 단위 테스트."""

from __future__ import annotations

import pytest
import pandas as pd

from screener.pipeline.watchlist_filter import (
    YearOverYearGrowth,
    WatchlistCandidate,
    calculate_yoy_growth,
    filter_by_metric_top_n,
    filter_by_market_cap,
    build_watchlist_candidates,
    apply_watchlist_filters,
)


class TestYearOverYearGrowth:
    """연간 증가율 계산 테스트."""

    def test_positive_growth(self):
        """양의 성장률 계산."""
        growth = YearOverYearGrowth.calculate("매출", current=110, prior=100)
        assert growth.metric_name == "매출"
        assert growth.current_year == 110
        assert growth.prior_year == 100
        assert growth.growth_rate == 10.0

    def test_negative_growth(self):
        """음의 성장률 계산."""
        growth = YearOverYearGrowth.calculate("매출", current=90, prior=100)
        assert growth.growth_rate == -10.0

    def test_zero_prior_year(self):
        """전년도가 0인 경우."""
        growth = YearOverYearGrowth.calculate("매출", current=100, prior=0)
        assert growth.growth_rate == 0.0

    def test_missing_values(self):
        """누락된 값 처리."""
        growth = YearOverYearGrowth.calculate("매출", current=None, prior=100)
        assert growth.growth_rate == 0.0


class TestCalculateYoYGrowth:
    """연간 증가율 계산 함수 테스트."""

    def test_normal_calculation(self):
        """정상 증가율 계산."""
        df = pd.DataFrame({
            "ticker": ["A", "B"],
            "revenue_current_year": [1100, 900],
            "revenue_prior_year": [1000, 1000],
        }).set_index("ticker")

        growth = calculate_yoy_growth(df, "revenue")
        assert growth["A"] == 10.0
        assert growth["B"] == -10.0

    def test_missing_columns(self):
        """누락된 컬럼."""
        df = pd.DataFrame({
            "ticker": ["A"],
        }).set_index("ticker")

        growth = calculate_yoy_growth(df, "revenue")
        assert len(growth) == 0

    def test_zero_prior_year_nan(self):
        """전년도 0일 때 NaN."""
        df = pd.DataFrame({
            "ticker": ["A", "B"],
            "asset_current_year": [100, 100],
            "asset_prior_year": [0, 100],
        }).set_index("ticker")

        growth = calculate_yoy_growth(df, "asset")
        assert pd.isna(growth["A"])
        assert growth["B"] == 0.0  # (100-100)/100 = 0


class TestFilterByMetricTopN:
    """지표 상위 필터링 테스트."""

    def test_top_n_descending(self):
        """상위 N개 (내림차순)."""
        df = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "score": [30, 10, 20],
        })

        result = filter_by_metric_top_n(df, "score", top_n=2, ascending=False)
        assert len(result) == 2
        assert set(result["ticker"]) == {"A", "C"}

    def test_top_n_exceeds_dataframe(self):
        """N이 데이터프레임 크기보다 클 때."""
        df = pd.DataFrame({
            "ticker": ["A", "B"],
            "score": [20, 10],
        })

        result = filter_by_metric_top_n(df, "score", top_n=5, ascending=False)
        assert len(result) == 2


class TestFilterByMarketCap:
    """시총 필터링 테스트."""

    def test_market_cap_filter(self):
        """시총 하한 필터링."""
        df = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "market_cap": [500e9, 200e9, 400e9],
        })

        result = filter_by_market_cap(df, min_market_cap=300e9)
        assert len(result) == 2
        assert set(result["ticker"]) == {"A", "C"}

    def test_market_cap_all_pass(self):
        """모두 통과."""
        df = pd.DataFrame({
            "ticker": ["A", "B"],
            "market_cap": [500e9, 600e9],
        })

        result = filter_by_market_cap(df, min_market_cap=300e9)
        assert len(result) == 2

    def test_market_cap_none_pass(self):
        """모두 탈락."""
        df = pd.DataFrame({
            "ticker": ["A", "B"],
            "market_cap": [100e9, 200e9],
        })

        result = filter_by_market_cap(df, min_market_cap=300e9)
        assert len(result) == 0


class TestBuildWatchlistCandidates:
    """관심종목 후보 조립 테스트."""

    def test_normal_merge(self):
        """정상 병합."""
        merged_df = pd.DataFrame({
            "ticker": ["A", "B"],
            "name": ["종목A", "종목B"],
            "market_cap": [500e9, 400e9],
            "asset_growth": [50.0, 40.0],
            "operating_income_growth": [45.0, 35.0],
            "revenue_growth": [40.0, 30.0],
        })

        candidates = build_watchlist_candidates(merged_df)
        assert len(candidates) == 2
        assert candidates[0].ticker == "A"
        assert candidates[0].name == "종목A"
        assert candidates[0].market_cap == 500e9
        assert candidates[0].asset_growth == 50.0
        assert candidates[0].operating_income_growth == 45.0
        assert candidates[0].revenue_growth == 40.0

    def test_nan_to_zero_conversion(self):
        """NaN 값을 0.0으로 변환."""
        merged_df = pd.DataFrame({
            "ticker": ["A"],
            "name": ["종목A"],
            "market_cap": [500e9],
            "asset_growth": [float("nan")],
            "operating_income_growth": [45.0],
            "revenue_growth": [40.0],
        })

        candidates = build_watchlist_candidates(merged_df)
        assert candidates[0].asset_growth == 0.0
        assert not pd.isna(candidates[0].asset_growth)

    def test_missing_values_default(self):
        """누락된 값은 기본값 사용."""
        merged_df = pd.DataFrame({
            "ticker": ["A"],
            "market_cap": [500e9],
            "asset_growth": [50.0],
            "operating_income_growth": [45.0],
            "revenue_growth": [40.0],
            # name 누락
        })

        candidates = build_watchlist_candidates(merged_df)
        assert candidates[0].name == ""
        assert candidates[0].market_cap == 500e9


class TestApplyWatchlistFilters:
    """다단계 필터링 테스트."""

    def test_sequential_filtering(self):
        """순차 필터링 — 출력값 검증."""
        universe_df = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "name": ["종목A", "종목B", "종목C", "종목D", "종목E"],
            "market_cap": [500e9, 200e9, 600e9, 150e9, 700e9],
        })

        financials_df = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "asset_growth": [50, 40, 30, 20, 10],
            "operating_income_growth": [45, 35, 25, 15, 5],
            "revenue_growth": [40, 30, 20, 10, 0],
        }).set_index("ticker")

        candidates = apply_watchlist_filters(
            universe_df.set_index("ticker"),
            financials_df,
            top_n_asset=3,
            top_n_oi=2,
            top_n_revenue=1,
            min_market_cap=300e9,
        )

        # 1단계: asset_growth top 3 = [A(50), B(40), C(30)]
        # 2단계: oi_growth top 2 = [A(45), B(35)]
        # 3단계: revenue_growth top 1 = [A(40)]
        # 4단계: market_cap >= 300B = [A(500B)] → 통과
        assert [c.ticker for c in candidates] == ["A"]
        assert candidates[0].name == "종목A"
        assert candidates[0].market_cap == 500e9
        assert candidates[0].asset_growth == 50
        assert candidates[0].operating_income_growth == 45
        assert candidates[0].revenue_growth == 40

    def test_missing_financials_column(self):
        """필수 재무 컬럼 누락 — ValueError 발생."""
        universe_df = pd.DataFrame({
            "ticker": ["A"],
            "name": ["종목A"],
            "market_cap": [500e9],
        })

        financials_df = pd.DataFrame({
            "ticker": ["A"],
            # asset_growth 등 컬럼 누락
        }).set_index("ticker")

        # 필수 컬럼이 없으면 ValueError 발생
        with pytest.raises(ValueError, match="필수 컬럼 누락"):
            apply_watchlist_filters(
                universe_df.set_index("ticker"),
                financials_df,
            )

    def test_empty_inputs(self):
        """빈 입력."""
        universe_df = pd.DataFrame({
            "ticker": [],
            "name": [],
            "market_cap": [],
        })

        financials_df = pd.DataFrame({
            "ticker": [],
            "asset_growth": [],
            "operating_income_growth": [],
            "revenue_growth": [],
        }).set_index("ticker")

        candidates = apply_watchlist_filters(
            universe_df.set_index("ticker"),
            financials_df,
        )
        assert len(candidates) == 0


class TestWatchlistCandidate:
    """관심종목 후보 클래스 테스트."""

    def test_candidate_creation(self):
        """후보 생성."""
        candidate = WatchlistCandidate(
            ticker="005930",
            name="SK하이닉스",
            market_cap=50e12,
            asset_growth=15.5,
            operating_income_growth=12.3,
            revenue_growth=8.7,
        )

        assert candidate.ticker == "005930"
        assert candidate.name == "SK하이닉스"
        assert candidate.market_cap == 50e12
        assert candidate.asset_growth == 15.5

    def test_candidate_frozen(self):
        """불변 객체."""
        candidate = WatchlistCandidate(
            ticker="005930",
            name="SK하이닉스",
            market_cap=50e12,
            asset_growth=15.5,
            operating_income_growth=12.3,
            revenue_growth=8.7,
        )

        with pytest.raises(AttributeError):
            candidate.ticker = "999999"
