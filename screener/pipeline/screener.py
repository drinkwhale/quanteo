"""유니버스 1차 필터 (결정론적).

관리종목·거래정지·시가총액·20일 평균 거래대금 순으로 필터를 적용해
~2000개 유니버스를 ~50개 수준으로 압축한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import yaml

if TYPE_CHECKING:
    from screener.data.collectors.pykrx_client import PykrxClient

logger = logging.getLogger(__name__)

_DEFAULT_SETTINGS_PATH = "screener/config/settings.yaml"


@dataclass(frozen=True)
class ScreenerConfig:
    """settings.yaml `universe` 섹션."""

    min_market_cap: float = 50_000_000_000
    min_avg_trading_value_20d: float = 500_000_000
    exclude_administrative: bool = True

    @classmethod
    def from_yaml(cls, path: str | Path = _DEFAULT_SETTINGS_PATH) -> ScreenerConfig:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        universe = raw.get("universe", {})
        return cls(
            min_market_cap=float(universe.get("min_market_cap", cls.min_market_cap)),
            min_avg_trading_value_20d=float(
                universe.get("min_avg_trading_value_20d", cls.min_avg_trading_value_20d)
            ),
            exclude_administrative=bool(
                universe.get("exclude_administrative", cls.exclude_administrative)
            ),
        )


def filter_universe(
    df: pd.DataFrame,
    config: ScreenerConfig,
    avg_trading_value_20d: pd.Series | None = None,
) -> pd.DataFrame:
    """유니버스를 관리종목/거래정지 → 시가총액 → 20일 평균 거래대금 순으로 필터링한다.

    Args:
        df: `PykrxClient.fetch_universe()` 출력 (ticker, market_cap, volume 등 컬럼 포함).
        config: 필터 임계값.
        avg_trading_value_20d: 티커별 20일 평균 거래대금 (index=ticker). None이면
            이 단계는 건너뛴다 (호출자가 별도로 `compute_avg_trading_value_20d()`로
            계산해 전달해야 실제로 적용된다).

    Returns:
        필터를 통과한 종목만 남은 DataFrame.
    """
    result = df.copy()
    original_count = len(result)

    if config.exclude_administrative:
        # NOTE: pykrx는 "관리종목" 지정 여부를 별도 API로 노출하지 않는다. 여기서는
        # 근사치로 당일 거래정지(거래량 0)만 걸러낸다 — 관리종목 자체 판별은 추후
        # 별도 데이터 소스(KRX 공시 등) 확보 전까지 보류한다.
        before = len(result)
        result = result[result["volume"] > 0]
        logger.info("거래정지(거래량 0) 필터: %d개 제외", before - len(result))

    before = len(result)
    result = result[result["market_cap"] >= config.min_market_cap]
    logger.info(
        "시가총액(%.0f 미만) 필터: %d개 제외", config.min_market_cap, before - len(result)
    )

    if avg_trading_value_20d is not None:
        result = result.merge(
            avg_trading_value_20d.rename("avg_trading_value_20d"),
            left_on="ticker",
            right_index=True,
            how="left",
        )
        before = len(result)
        result = result[
            result["avg_trading_value_20d"].fillna(0) >= config.min_avg_trading_value_20d
        ]
        logger.info(
            "20일 평균 거래대금(%.0f 미만) 필터: %d개 제외",
            config.min_avg_trading_value_20d,
            before - len(result),
        )

    logger.info("유니버스 필터 완료: %d개 → %d개", original_count, len(result))
    return result


async def average_over_trading_days(
    client: PykrxClient, date: str, column: str, days: int = 20
) -> pd.Series:
    """최근 `days` 거래일(월~금)의 티커별 `column` 평균을 계산한다.

    `PykrxClient.fetch_universe()`가 반환하는 컬럼(trading_value, volume 등)
    아무거나에 재사용 가능한 일반 헬퍼 — 20일 평균 거래대금(T100)과
    거래량 급증 배수(T104)가 공유한다.

    Args:
        client: 시세 조회에 사용할 PykrxClient.
        date: 기준일 (YYYYMMDD). 이 날짜를 포함해 과거로 거슬러 올라간다.
        column: 평균낼 컬럼명 (예: "trading_value", "volume").
        days: 집계할 거래일 수.

    Returns:
        index=ticker, value=평균값 Series.

    NOTE: 주말은 건너뛰지만 임시공휴일까지는 걸러내지 못한다 — 공휴일은
    PykrxClient.fetch_universe() 내부의 직전 영업일 폴백이 흡수하지만, 그
    결과 동일 영업일 데이터가 이웃 날짜에 중복 집계될 수 있다. 완전한
    거래일 캘린더가 필요해지면 Toss market-calendar API(T052) 연동을 검토.
    """
    frames: list[pd.DataFrame] = []
    cursor = datetime.strptime(date, "%Y%m%d")
    max_calendar_days = days * 3  # 주말 비율 감안 여유
    checked = 0

    while len(frames) < days and checked < max_calendar_days:
        if cursor.weekday() < 5:  # Mon-Fri만
            day_str = cursor.strftime("%Y%m%d")
            snapshot = await client.fetch_universe(day_str)
            if not snapshot.empty and column in snapshot.columns:
                frames.append(snapshot[["ticker", column]])
        cursor -= timedelta(days=1)
        checked += 1

    if not frames:
        logger.warning("%d일 평균(%s) 계산 실패 — 유효 거래일 데이터 없음", days, column)
        return pd.Series(dtype=float, name=column)

    combined = pd.concat(frames)
    return combined.groupby("ticker")[column].mean()


async def compute_avg_trading_value_20d(
    client: PykrxClient, date: str, days: int = 20
) -> pd.Series:
    """최근 `days` 거래일의 티커별 평균 거래대금을 계산한다 (유니버스 필터용)."""
    return await average_over_trading_days(client, date, "trading_value", days=days)
