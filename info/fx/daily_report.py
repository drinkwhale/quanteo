"""
환율 일일 마감 리포트.

오후 4시 기준 yfinance 4종 환율 종가를 조회해 일중 변동률과 종합 평가를 생성한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

import pytz

from info.fx.rate_rule import interpret_fx

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")


@dataclass
class FxDailyReport:
    """환율 일일 마감 리포트 데이터."""

    date: datetime
    usdkrw: float
    dxy: float
    jpykrw: float
    cnykrw: float
    usdkrw_change_pct: float
    dxy_change_pct: float
    jpykrw_change_pct: float
    cnykrw_change_pct: float
    summary: str


class FxDailyReporter:
    """오후 4시 기준 일일 환율 마감 리포트 생성기."""

    def __init__(self, info_notifier=None) -> None:
        self._notifier = info_notifier

    async def generate(self) -> FxDailyReport:
        """오후 4시 yfinance 조회 후 리포트를 생성한다."""
        loop = asyncio.get_running_loop()
        report = await loop.run_in_executor(None, self._generate_sync)

        if self._notifier:
            try:
                await self._notifier.send_fx_daily_report(report)
            except Exception as exc:
                logger.error("일일 환율 리포트 발송 실패: %s", exc)

        return report

    def _generate_sync(self) -> FxDailyReport:
        import yfinance as yf

        tickers = ["USDKRW=X", "DX-Y.NYB", "JPYKRW=X", "CNYKRW=X"]
        keys = ["usdkrw", "dxy", "jpykrw", "cnykrw"]

        try:
            data = yf.download(
                tickers,
                period="1d",
                interval="1m",
                progress=False,
                auto_adjust=True,
            )
        except Exception as exc:
            logger.error("yfinance 일일 리포트 조회 실패: %s", exc)
            return self._empty_report()

        closes: dict[str, float] = {}
        opens: dict[str, float] = {}

        for key, ticker in zip(keys, tickers):
            try:
                if "Close" in data.columns:
                    series = data["Close"][ticker].dropna()
                else:
                    series = data[ticker]["Close"].dropna()

                if series.empty:
                    closes[key] = 0.0
                    opens[key] = 0.0
                else:
                    closes[key] = float(series.iloc[-1])
                    opens[key] = float(series.iloc[0])
            except Exception as exc:
                logger.warning("yfinance 일일 ticker 파싱 실패 %s: %s", ticker, exc)
                closes[key] = 0.0
                opens[key] = 0.0

        def pct(close: float, open_: float) -> float:
            if open_ == 0:
                return 0.0
            return (close - open_) / open_ * 100

        usdkrw_chg = pct(closes["usdkrw"], opens["usdkrw"])
        dxy_chg = pct(closes["dxy"], opens["dxy"])

        summary = interpret_fx(usdkrw_chg, dxy_chg)

        return FxDailyReport(
            date=datetime.now(tz=KST),
            usdkrw=closes["usdkrw"],
            dxy=closes["dxy"],
            jpykrw=closes["jpykrw"],
            cnykrw=closes["cnykrw"],
            usdkrw_change_pct=usdkrw_chg,
            dxy_change_pct=dxy_chg,
            jpykrw_change_pct=pct(closes["jpykrw"], opens["jpykrw"]),
            cnykrw_change_pct=pct(closes["cnykrw"], opens["cnykrw"]),
            summary=summary,
        )

    def _empty_report(self) -> FxDailyReport:
        return FxDailyReport(
            date=datetime.now(tz=KST),
            usdkrw=0.0, dxy=0.0, jpykrw=0.0, cnykrw=0.0,
            usdkrw_change_pct=0.0, dxy_change_pct=0.0,
            jpykrw_change_pct=0.0, cnykrw_change_pct=0.0,
            summary="데이터 조회 실패",
        )
