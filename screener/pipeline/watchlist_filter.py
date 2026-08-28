"""관심종목 다단계 필터링 (자산·영업이익·매출 증가율 기반).

최근 3년간 재무 성장성을 기준으로 순차 필터링:
1. 자산 증가율 top 300
2. 영업이익 증가율 top 200
3. 매출 증가율 top 50
4. 시총 3천억 이상 필터
→ 최종 관심종목 리스트 생성
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from screener.data.collectors.dart_client import DartClient
    from screener.data.collectors.pykrx_client import PykrxClient

logger = logging.getLogger(__name__)

MIN_MARKET_CAP_WATCHLIST = 300_000_000_000  # 3천억


@dataclass(frozen=True)
class YearOverYearGrowth:
    """연간 증가율 지표."""

    metric_name: str
    current_year: float | None
    prior_year: float | None
    growth_rate: float  # 퍼센트 (%)

    @classmethod
    def calculate(
        cls, metric_name: str, current: float | None, prior: float | None
    ) -> YearOverYearGrowth:
        """연간 증가율 계산 (prior_year 기준).

        Args:
            metric_name: 지표명 (예: "자산", "영업이익", "매출")
            current: 현재 연도 값
            prior: 전년도 값

        Returns:
            YearOverYearGrowth 인스턴스. 값이 부족하면 growth_rate = 0.0
        """
        growth_rate = 0.0
        if current is not None and prior is not None and prior > 0:
            growth_rate = ((current - prior) / prior) * 100
        return cls(
            metric_name=metric_name,
            current_year=current,
            prior_year=prior,
            growth_rate=growth_rate,
        )


@dataclass(frozen=True)
class WatchlistCandidate:
    """필터링을 통과한 관심종목 후보."""

    ticker: str
    name: str
    market_cap: float  # 시총 (원)
    asset_growth: float  # 자산 증가율 (%)
    operating_income_growth: float  # 영업이익 증가율 (%)
    revenue_growth: float  # 매출 증가율 (%)
    rank_by_asset: int | None = None
    rank_by_oi: int | None = None
    rank_by_revenue: int | None = None


def calculate_yoy_growth(
    financials_df: pd.DataFrame, metric: str
) -> pd.Series:
    """연간 증가율 계산.

    Args:
        financials_df: [ticker, {metric}_current_year, {metric}_prior_year] 컬럼 포함 DataFrame.
            예: ["asset_current_year", "asset_prior_year"]
        metric: 지표명 ("asset", "operating_income", "revenue")

    Returns:
        pd.Series (index=ticker, 증가율 %). NaN 또는 <= 0 prior_year는 NaN 유지.
    """
    current_col = f"{metric}_current_year"
    prior_col = f"{metric}_prior_year"

    if current_col not in financials_df.columns or prior_col not in financials_df.columns:
        logger.warning(f"컬럼 누락: {current_col}, {prior_col}")
        return pd.Series(dtype=float)

    growth = pd.Series(dtype=float, index=financials_df.index)
    valid = (financials_df[prior_col] > 0) & (
        financials_df[current_col].notna()
    )
    growth[valid] = (
        (financials_df.loc[valid, current_col] - financials_df.loc[valid, prior_col])
        / financials_df.loc[valid, prior_col]
        * 100
    )
    return growth


def filter_by_metric_top_n(
    df: pd.DataFrame, metric_col: str, top_n: int, ascending: bool = False
) -> pd.DataFrame:
    """지표 상위 N개로 필터링.

    Args:
        df: DataFrame
        metric_col: 정렬 대상 컬럼
        top_n: 상위 N개
        ascending: False면 내림차순(높은 값 우선)

    Returns:
        상위 N개 선택된 DataFrame
    """
    before_count = len(df)
    result = df.nlargest(top_n, metric_col) if not ascending else df.nsmallest(
        top_n, metric_col
    )
    logger.info(
        f"[{metric_col}] {before_count}개 중 상위 {top_n}개 선택 → {len(result)}개 남음"
    )
    return result.copy()


def filter_by_market_cap(df: pd.DataFrame, min_market_cap: float) -> pd.DataFrame:
    """시총 하한선으로 필터링.

    Args:
        df: market_cap 컬럼 포함 DataFrame
        min_market_cap: 최소 시총 (원)

    Returns:
        필터링된 DataFrame
    """
    before_count = len(df)
    result = df[df["market_cap"] >= min_market_cap].copy()
    logger.info(
        f"[시총 >= {min_market_cap/1e9:.0f}B] {before_count}개 중 {len(result)}개 통과"
    )
    return result


def build_watchlist_candidates(
    universe_df: pd.DataFrame,
    financials_df: pd.DataFrame,
) -> list[WatchlistCandidate]:
    """관심종목 후보 조립.

    Args:
        universe_df: 시장 데이터 (ticker, name, market_cap)
        financials_df: 재무 데이터 (ticker, 연간 增減率 컬럼)

    Returns:
        WatchlistCandidate 리스트
    """
    # 통합: ticker 기준 left join
    merged = universe_df.merge(
        financials_df, on="ticker", how="left"
    )

    candidates = []
    for _, row in merged.iterrows():
        candidate = WatchlistCandidate(
            ticker=row["ticker"],
            name=row.get("name", ""),
            market_cap=float(row.get("market_cap", 0)),
            asset_growth=float(row.get("asset_growth", 0.0) or 0.0),
            operating_income_growth=float(
                row.get("operating_income_growth", 0.0) or 0.0
            ),
            revenue_growth=float(row.get("revenue_growth", 0.0) or 0.0),
        )
        candidates.append(candidate)

    return candidates


def apply_watchlist_filters(
    universe_df: pd.DataFrame,
    financials_df: pd.DataFrame,
    top_n_asset: int = 300,
    top_n_oi: int = 200,
    top_n_revenue: int = 50,
    min_market_cap: float = MIN_MARKET_CAP_WATCHLIST,
) -> list[WatchlistCandidate]:
    """다단계 필터링 적용.

    1단계: 자산 증가율 top {top_n_asset}
    2단계: 영업이익 증가율 top {top_n_oi}
    3단계: 매출 증가율 top {top_n_revenue}
    4단계: 시총 >= {min_market_cap}

    Args:
        universe_df: 시장 데이터 (index=ticker, columns: name, market_cap)
        financials_df: 재무 데이터 (index=ticker, columns: 증가율 등)
        top_n_asset: 1단계 상위 N개
        top_n_oi: 2단계 상위 N개
        top_n_revenue: 3단계 상위 N개
        min_market_cap: 4단계 시총 하한

    Returns:
        최종 필터링된 WatchlistCandidate 리스트
    """
    logger.info(
        f"관심종목 필터링 시작 — "
        f"자산상위{top_n_asset} → "
        f"영업이익상위{top_n_oi} → "
        f"매출상위{top_n_revenue} → "
        f"시총>={min_market_cap/1e9:.0f}B"
    )

    # 1단계: 자산 증가율 top
    if "asset_growth" in financials_df.columns:
        filtered = filter_by_metric_top_n(
            financials_df.reset_index(), "asset_growth", top_n_asset
        ).set_index("ticker")
    else:
        logger.warning("asset_growth 컬럼 없음 — 필터링 건너뜀")
        filtered = financials_df.copy()

    # 2단계: 영업이익 증가율 top
    if "operating_income_growth" in filtered.columns:
        filtered = filter_by_metric_top_n(
            filtered.reset_index(), "operating_income_growth", top_n_oi
        ).set_index("ticker")
    else:
        logger.warning("operating_income_growth 컬럼 없음 — 필터링 건너뜀")

    # 3단계: 매출 증가율 top
    if "revenue_growth" in filtered.columns:
        filtered = filter_by_metric_top_n(
            filtered.reset_index(), "revenue_growth", top_n_revenue
        ).set_index("ticker")
    else:
        logger.warning("revenue_growth 컬럼 없음 — 필터링 건너뜀")

    # universe와 재병합 (시총 포함)
    universe_reset = universe_df.reset_index()
    filtered_reset = filtered.reset_index()

    # 중복 컬럼 제거 후 병합
    universe_cols = ["ticker", "market_cap"]
    if "name" in universe_reset.columns:
        universe_cols.append("name")

    merged = filtered_reset.merge(
        universe_reset[universe_cols],
        on="ticker",
        how="left",
        suffixes=("", "_market"),
    )

    # market_cap 컬럼 통합 (market_cap이 두 개인 경우)
    if "market_cap_market" in merged.columns:
        merged["market_cap"] = merged["market_cap_market"]
        merged = merged.drop(columns=["market_cap_market"])

    # 4단계: 시총 필터
    filtered = filter_by_market_cap(merged, min_market_cap)

    logger.info(f"최종 관심종목: {len(filtered)}개")

    # 최종 후보 조립
    candidates = build_watchlist_candidates(
        filtered,
        filtered,
    )

    return candidates
