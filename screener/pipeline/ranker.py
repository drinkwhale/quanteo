"""랭킹 산출 + 필터 레이어(수급/기술/모멘텀).

스코어에는 합산하지 않는 부가 정보 — 동점자 우선순위와 리포트 표시용.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pandas as pd

from screener.pipeline.screener import average_over_trading_days

if TYPE_CHECKING:
    from screener.data.collectors.dart_client import Disclosure
    from screener.data.collectors.pykrx_client import PykrxClient

logger = logging.getLogger(__name__)


def rank_top_n(scored_df: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
    """가중합 스코어 기준 상위 `top_n`개를 반환한다.

    동점자는 foreign_institution_streak → volume_surge_ratio 순으로
    우선순위를 매긴다 (해당 컬럼이 없으면 그 기준은 건너뛴다).
    """
    sort_cols = ["weighted_score"]
    ascending = [False]
    for col in ("foreign_institution_streak", "volume_surge_ratio"):
        if col in scored_df.columns:
            sort_cols.append(col)
            ascending.append(False)

    ranked = scored_df.sort_values(by=sort_cols, ascending=ascending).reset_index(drop=True)
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    return ranked.head(top_n)


# ---------------------------------------------------------------------------
# 필터 레이어 (스코어 미합산)
# ---------------------------------------------------------------------------


async def foreign_institution_streak(
    client: PykrxClient, tickers: list[str], date: str, max_days: int = 20
) -> pd.Series:
    """외인+기관 동반 순매수 연속일수 (date에서 역산, 끊기면 카운트 중단).

    Returns:
        index=ticker, value=연속일수(정수) Series.
    """
    streak: dict[str, int] = dict.fromkeys(tickers, 0)
    active = set(tickers)
    cursor = datetime.strptime(date, "%Y%m%d")
    max_calendar_days = max_days * 3
    checked = 0
    weekdays_examined = 0

    while active and weekdays_examined < max_days and checked < max_calendar_days:
        if cursor.weekday() < 5:
            day_df = await client.fetch_investor_trading(cursor.strftime("%Y%m%d"))
            day_lookup = (
                day_df.set_index("ticker") if not day_df.empty else pd.DataFrame()
            )
            still_active: set[str] = set()
            for ticker in active:
                if (
                    not day_lookup.empty
                    and ticker in day_lookup.index
                    and day_lookup.loc[ticker, "foreign_net"] > 0
                    and day_lookup.loc[ticker, "institution_net"] > 0
                ):
                    streak[ticker] += 1
                    still_active.add(ticker)
                # else: 연속 끊김 — active에서 제외해 더 이상 카운트하지 않는다.
            active = still_active
            weekdays_examined += 1
        cursor -= timedelta(days=1)
        checked += 1

    return pd.Series(streak, name="foreign_institution_streak")


async def volume_surge_ratio(
    client: PykrxClient, universe: pd.DataFrame, date: str, days: int = 20
) -> pd.Series:
    """당일 거래량 / 20일 평균 거래량 배수.

    Args:
        universe: `PykrxClient.fetch_universe(date)` 출력 (당일 volume 포함).
    """
    avg_volume = await average_over_trading_days(client, date, "volume", days=days)
    today = universe.set_index("ticker")["volume"]
    ratio = today / avg_volume.reindex(today.index)
    return ratio.rename("volume_surge_ratio")


def earnings_surprise_flag(disclosures: dict[str, list[Disclosure]]) -> pd.Series:
    """최근 실적 서프라이즈 근사 여부.

    NOTE: 전체 유니버스에 대한 컨센서스 실적 데이터를 수집하지 않으므로
    실제 컨센서스 대비 서프라이즈가 아니라, DART "실적정정" 공시 발생
    여부로 근사한다 (T102 DartClient.IMPORTANT_DISCLOSURE_TYPES 참고).
    """
    flags = {
        ticker: any(d.report_type == "실적정정" for d in items)
        for ticker, items in disclosures.items()
    }
    return pd.Series(flags, name="earnings_surprise_flag")


def has_recent_disclosure(disclosures: dict[str, list[Disclosure]]) -> pd.Series:
    """T102 `fetch_recent_disclosures()` 발생 여부."""
    flags = {ticker: len(items) > 0 for ticker, items in disclosures.items()}
    return pd.Series(flags, name="has_recent_disclosure")
