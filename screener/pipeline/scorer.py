"""5축 스코어링 (성장성/수익성/현금흐름/재무안정성/상대가치).

입력은 PykrxClient.fetch_universe() 출력(ticker, sector, market_cap, per,
pbr, div_yield 등)에 build_financial_features()로 변환한 DartClient
재무 피처를 합친 DataFrame이다.

DartClient가 수집하는 재무 항목 범위 밖의 하위 지표는 근사치로 대체하거나
계산하지 않는다:
- EPS YoY → 발행주식수 변동을 무시하고 순이익 YoY로 근사
- 영업이익률 추세(스펙 원문 "3분기") → 분기 재무제표를 수집하지 않으므로
  최근 2개년(연간) 영업이익률 차분으로 근사
- FCF 전환율 → CapEx를 수집하지 않으므로 영업활동현금흐름/매출액으로 근사
- 이자보상배율·Altman Z-Score → 이자비용·총자산·이익잉여금을 수집하지
  않아 계산 불가. `calculate_altman_z_score()`는 항상 None을 반환한다
  (스펙상 "보조 지표, 스코어 미반영"이므로 최종 스코어에는 영향 없음).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from screener.data.collectors.dart_client import FinancialStatement

logger = logging.getLogger(__name__)

_DEFAULT_WEIGHTS: dict[str, float] = {
    "growth": 0.2,
    "profitability": 0.2,
    "cashflow": 0.2,
    "stability": 0.2,
    "valuation": 0.2,
}


# ---------------------------------------------------------------------------
# 재무제표 → 피처
# ---------------------------------------------------------------------------


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _yoy(curr: float | None, prior: float | None) -> float | None:
    if curr is None or prior is None or prior == 0:
        return None
    return (curr - prior) / abs(prior)


_FEATURE_COLUMNS: tuple[str, ...] = (
    "revenue_yoy",
    "operating_income_yoy",
    "net_income_yoy",
    "roe",
    "operating_margin",
    "operating_margin_trend",
    "cfo_to_net_income",
    "fcf_conversion",
    "debt_ratio",
    "current_ratio",
)


def build_financial_features(statements: dict[str, FinancialStatement]) -> pd.DataFrame:
    """{ticker: FinancialStatement} → 스코어링 입력 피처 DataFrame.

    2개년 미만 데이터만 있으면 YoY/추세 관련 필드는 NaN(결측)으로 남는다
    — score_growth() 등이 결측을 섹터 중앙값으로 대체한다. 재무제표가
    아예 없는 티커도 전체 컬럼을 NaN으로 채운 행을 반환한다 — 그래야
    merge 후 DataFrame에 컬럼 자체가 누락되는 일이 없다(score_*()가
    KeyError 없이 동작하려면 스키마가 항상 일정해야 한다).
    """
    rows: list[dict] = []
    for ticker, stmt in statements.items():
        years = sorted(stmt.years, key=lambda y: y.year, reverse=True)
        row: dict = {"ticker": ticker, **dict.fromkeys(_FEATURE_COLUMNS)}
        if not years:
            rows.append(row)
            continue

        latest = years[0]
        prev = years[1] if len(years) > 1 else None

        operating_margin = _safe_div(latest.operating_income, latest.revenue)
        prev_operating_margin = _safe_div(prev.operating_income, prev.revenue) if prev else None

        row.update(
            {
                "revenue_yoy": _yoy(latest.revenue, prev.revenue if prev else None),
                "operating_income_yoy": _yoy(
                    latest.operating_income, prev.operating_income if prev else None
                ),
                "net_income_yoy": _yoy(latest.net_income, prev.net_income if prev else None),
                "roe": _safe_div(latest.net_income, latest.total_equity),
                "operating_margin": operating_margin,
                "operating_margin_trend": (
                    operating_margin - prev_operating_margin
                    if operating_margin is not None and prev_operating_margin is not None
                    else None
                ),
                "cfo_to_net_income": _safe_div(latest.operating_cash_flow, latest.net_income),
                "fcf_conversion": _safe_div(latest.operating_cash_flow, latest.revenue),
                "debt_ratio": _safe_div(latest.total_liabilities, latest.total_equity),
                "current_ratio": _safe_div(latest.current_assets, latest.current_liabilities),
            }
        )
        rows.append(row)

    return pd.DataFrame(rows)


def calculate_altman_z_score(row: pd.Series) -> float | None:  # noqa: ARG001
    """Altman Z-Score 보조 지표. 스코어에는 반영하지 않는다.

    항상 None — 계산에 필요한 총자산·이익잉여금·이자비용을 DartClient가
    수집하지 않는다. 추후 데이터 소스가 추가되면 구현.
    """
    return None


# ---------------------------------------------------------------------------
# 섹터 percentile 스코어러
# ---------------------------------------------------------------------------


class SectorPercentileScorer:
    """섹터 내 percentile 기반 1~5점 스코어 산출 헬퍼."""

    def __init__(self, levels: int = 5) -> None:
        self._levels = levels

    def score(
        self, df: pd.DataFrame, column: str, sector_col: str = "sector", ascending: bool = True
    ) -> pd.Series:
        """섹터별로 `column`의 percentile을 계산해 1~`levels`점으로 이산화한다.

        Args:
            ascending: True면 값이 클수록 고득점(성장성 등). False면 값이
                작을수록 고득점(밸류에이션 — PER 낮을수록 좋음).
        """
        values = pd.to_numeric(df[column], errors="coerce")
        median = values.median()
        filled = values.fillna(median)  # 결측 → 섹터 전체가 아닌 전체 중앙값 대체(보수적)

        def _rank_group(group: pd.Series) -> pd.Series:
            pct = group.rank(pct=True, ascending=ascending)
            scores = np.ceil(pct * self._levels)
            return scores.clip(lower=1, upper=self._levels)

        sectors = df[sector_col] if sector_col in df.columns else pd.Series("UNKNOWN", index=df.index)
        result = filled.groupby(sectors).transform(_rank_group)
        return result.rename(column)


_scorer = SectorPercentileScorer()


# ---------------------------------------------------------------------------
# 5축 스코어
# ---------------------------------------------------------------------------


def score_growth(df: pd.DataFrame) -> pd.Series:
    """성장성: 매출/영업이익/순이익(EPS 근사) YoY 평균."""
    components = pd.DataFrame(
        {
            "revenue": _scorer.score(df, "revenue_yoy"),
            "operating_income": _scorer.score(df, "operating_income_yoy"),
            "eps": _scorer.score(df, "net_income_yoy"),
        }
    )
    return components.mean(axis=1).rename("growth")


def score_profitability(df: pd.DataFrame) -> pd.Series:
    """수익성: ROE, 영업이익률, 영업이익률 추세 평균."""
    components = pd.DataFrame(
        {
            "roe": _scorer.score(df, "roe"),
            "operating_margin": _scorer.score(df, "operating_margin"),
            "operating_margin_trend": _scorer.score(df, "operating_margin_trend"),
        }
    )
    return components.mean(axis=1).rename("profitability")


def score_cashflow(df: pd.DataFrame) -> pd.Series:
    """현금흐름: 영업CF/순이익 비율, FCF 전환율(근사) 평균."""
    components = pd.DataFrame(
        {
            "cfo_to_net_income": _scorer.score(df, "cfo_to_net_income"),
            "fcf_conversion": _scorer.score(df, "fcf_conversion"),
        }
    )
    return components.mean(axis=1).rename("cashflow")


def score_stability(df: pd.DataFrame) -> pd.Series:
    """재무안정성: 부채비율(낮을수록 고득점), 유동비율(높을수록 고득점) 평균.

    이자보상배율은 데이터 미수집으로 제외 (docstring 참고).
    """
    components = pd.DataFrame(
        {
            "debt_ratio": _scorer.score(df, "debt_ratio", ascending=False),
            "current_ratio": _scorer.score(df, "current_ratio", ascending=True),
        }
    )
    return components.mean(axis=1).rename("stability")


def score_valuation(df: pd.DataFrame) -> pd.Series:
    """상대가치: PER/PBR 섹터 대비 — 낮을수록 고득점(역방향 정규화)."""
    components = pd.DataFrame(
        {
            "per": _scorer.score(df, "per", ascending=False),
            "pbr": _scorer.score(df, "pbr", ascending=False),
        }
    )
    return components.mean(axis=1).rename("valuation")


def calculate_weighted_score(
    scores: pd.DataFrame, weights: dict[str, float] | None = None
) -> pd.Series:
    """5축 스코어를 `settings.yaml` scoring_weights 기준으로 가중합한다."""
    weights = weights or _DEFAULT_WEIGHTS
    total = sum(weights.values())
    normalized = {k: v / total for k, v in weights.items()} if total else weights
    weighted = sum(scores[axis] * w for axis, w in normalized.items() if axis in scores.columns)
    return weighted.rename("weighted_score")
