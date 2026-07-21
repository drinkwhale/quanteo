"""전체 파이프라인 오케스트레이션 + 크론 등록.

Collector → Screener → Scorer → Ranker → BBC매수원칙판정 → AnalystAgent → Reporter
순서로 매 거래일 18:30 KST에 실행한다 (T067 InfoScheduler와 동일한 타임존 원칙).

18:30 실행 이유: pykrx 투자자별 순매수 데이터(외인/기관)는 장 마감 직후가 아니라
저녁 무렵 확정되므로, 15:40처럼 확정 전에 조회하면 foreign_institution_streak() 등
당일 수급 필드가 비어있거나 부정확할 수 있다. 확정 이후로 늦춰 정확한 값을 사용한다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from screener.agents.analyst_agent import RankedStock, StockSummary
from screener.pipeline.bbc_timing import assess_buy_principle, candles_from_history
from screener.pipeline.ranker import (
    earnings_surprise_flag,
    foreign_institution_streak,
    has_recent_disclosure,
    rank_top_n,
    volume_surge_ratio,
)
from screener.pipeline.scorer import (
    build_financial_features,
    calculate_weighted_score,
    score_cashflow,
    score_growth,
    score_profitability,
    score_stability,
    score_valuation,
)
from screener.pipeline.screener import (
    ScreenerConfig,
    compute_avg_trading_value_20d,
    filter_universe,
)

if TYPE_CHECKING:
    from screener.agents.analyst_agent import AnalystAgent
    from screener.data.collectors.dart_client import DartClient
    from screener.data.collectors.pykrx_client import PykrxClient
    from screener.notify.telegram_reporter import ScreenerNotifier

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

_MAX_RETRIES = 3
_INITIAL_RETRY_DELAY = 5.0  # 초


class DailyJob:
    """Stock Miner 일일 파이프라인.

    Args:
        pykrx_client: 시세·시총·수급 데이터 소스.
        dart_client: 재무제표·공시 데이터 소스.
        analyst_agent: LLM 요약 생성기.
        notifier: 리포트 발송기.
        screener_config: 유니버스 필터 설정 (T100).
        scoring_weights: 5축 가중치 (기본: 균등 20%).
        universe_top_n: 스코어링 후 유지할 랭킹 풀 크기 (스펙 5절, 30~50).
        report_top_n: 실제 발송·LLM 요약 대상 상위 종목 수 (기본 10, 비용 통제).
    """

    def __init__(
        self,
        pykrx_client: PykrxClient,
        dart_client: DartClient,
        analyst_agent: AnalystAgent,
        notifier: ScreenerNotifier,
        screener_config: ScreenerConfig,
        scoring_weights: dict[str, float] | None = None,
        universe_top_n: int = 50,
        report_top_n: int = 10,
    ) -> None:
        self._pykrx = pykrx_client
        self._dart = dart_client
        self._analyst = analyst_agent
        self._notifier = notifier
        self._config = screener_config
        self._weights = scoring_weights
        self._universe_top_n = universe_top_n
        self._report_top_n = report_top_n
        # 가장 최근 실행에서 생성된 티커별 LLM 요약 — CallbackHandler "상세보기"가 참조.
        # 프로세스 메모리에만 유지되므로 재시작 후에는 당일 리포트를 다시 실행해야 채워진다.
        self.last_summaries: dict[str, StockSummary] = {}

    async def run(self, date: str | None = None) -> None:
        """파이프라인을 실행한다. 전체 실패 시 지수 백오프 3회 재시도 후 에러 알림."""
        date = date or datetime.now(tz=KST).strftime("%Y%m%d")
        delay = _INITIAL_RETRY_DELAY

        for attempt in range(_MAX_RETRIES):
            try:
                await self._run_once(date)
                return
            except Exception as exc:
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(
                        "DailyJob 실행 실패, %.0fs 후 재시도 (%d/%d): %s",
                        delay,
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logger.error("DailyJob 파이프라인 3회 소진: %s", exc, exc_info=True)
                    await self._notifier.send_error_alert(
                        f"파이프라인 실패\n\n{date} Stock Miner 파이프라인이 "
                        f"3회 재시도 후 실패했습니다: {exc}"
                    )

    async def _run_once(self, date: str) -> None:
        logger.info("Stock Miner 파이프라인 시작: %s", date)

        # 1) Screener — 유니버스 필터
        universe = await self._pykrx.fetch_universe(date)
        if universe.empty:
            logger.warning("유니버스가 비어 있습니다(%s) — 휴장일일 수 있음, 파이프라인 스킵", date)
            return

        avg_trading_value = await compute_avg_trading_value_20d(self._pykrx, date)
        filtered = filter_universe(universe, self._config, avg_trading_value_20d=avg_trading_value)
        if filtered.empty:
            logger.warning("필터 통과 종목이 없습니다(%s)", date)
            return

        tickers: list[str] = filtered["ticker"].tolist()

        # 2) Scorer — 재무제표 수집 + 5축 스코어
        statements = {}
        for ticker in tickers:
            statements[ticker] = await self._dart.fetch_financials(ticker)
        features = build_financial_features(statements)
        merged = filtered.merge(features, on="ticker", how="left")

        scores = pd.DataFrame(
            {
                "growth": score_growth(merged),
                "profitability": score_profitability(merged),
                "cashflow": score_cashflow(merged),
                "stability": score_stability(merged),
                "valuation": score_valuation(merged),
            }
        )
        merged = pd.concat([merged, scores], axis=1)
        merged["weighted_score"] = calculate_weighted_score(scores, self._weights)

        # 3) Ranker — 필터 레이어(수급/기술/모멘텀) + 순위
        disclosures = {}
        for ticker in tickers:
            disclosures[ticker] = await self._dart.fetch_recent_disclosures(ticker)

        streak = await foreign_institution_streak(self._pykrx, tickers, date)
        surge = await volume_surge_ratio(self._pykrx, universe, date)
        merged = merged.merge(
            streak.rename("foreign_institution_streak"), left_on="ticker", right_index=True, how="left"
        )
        merged = merged.merge(
            surge.rename("volume_surge_ratio"), left_on="ticker", right_index=True, how="left"
        )
        merged["earnings_surprise_flag"] = merged["ticker"].map(earnings_surprise_flag(disclosures))
        merged["has_recent_disclosure"] = merged["ticker"].map(has_recent_disclosure(disclosures))

        ranked = rank_top_n(merged, top_n=self._universe_top_n)

        # 4) 박병창 매수 3원칙 판정 — 상위 report_top_n개만(비용/호출 통제).
        #    라이브 트레이딩과 동일한 core.strategy.plugins.bbc_buy.evaluate_buy()를
        #    일봉 히스토리에 재사용한다 (screener/pipeline/bbc_timing.py 참고).
        top_tickers = ranked.head(self._report_top_n)["ticker"].tolist()
        bbc_signals = {}
        for ticker in top_tickers:
            history = await self._pykrx.fetch_ohlcv_history(ticker, date)
            candles = candles_from_history(history, ticker)
            bbc_signals[ticker] = assess_buy_principle(candles)

        # 5) AnalystAgent — 상위 report_top_n개만 LLM 요약 (비용 통제)
        summaries: dict[str, StockSummary] = {}
        for _, row in ranked.head(self._report_top_n).iterrows():
            stock = RankedStock.from_row(row)
            summaries[stock.ticker] = await self._analyst.summarize(
                stock,
                disclosures.get(stock.ticker, []),
                bbc_signal=bbc_signals.get(stock.ticker),
            )
        self.last_summaries = summaries

        # 6) Reporter
        await self._notifier.send_daily_report_with_summaries(
            ranked, summaries, top_n=self._report_top_n
        )
        logger.info(
            "Stock Miner 파이프라인 완료: %s (필터 %d개 → 랭킹 %d개)",
            date,
            len(filtered),
            len(ranked),
        )


class DailyJobScheduler:
    """평일 18:30 KST 크론 등록 (T067 InfoScheduler와 동일한 타임존/misfire 원칙).

    15:40이 아닌 18:30인 이유는 daily_job 모듈 docstring 참고 — pykrx 투자자별
    순매수 데이터의 당일 확정 시점을 확보하기 위함.
    """

    def __init__(self, job: DailyJob) -> None:
        self._job = job
        self._scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
        self._scheduler.add_job(
            self._run_job,
            CronTrigger(hour=18, minute=30, day_of_week="mon-fri", timezone="Asia/Seoul"),
            id="stock_miner_daily_job",
            misfire_grace_time=300,
            coalesce=True,
        )

    async def _run_job(self) -> None:
        try:
            await self._job.run()
        except Exception as exc:  # pragma: no cover - run()이 이미 재시도·알림 처리
            logger.error("DailyJobScheduler: 예기치 못한 예외: %s", exc, exc_info=True)

    def start(self) -> None:
        self._scheduler.start()
        logger.info("DailyJobScheduler 시작 (평일 18:30 KST)")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("DailyJobScheduler 종료")

    @property
    def scheduler(self) -> AsyncIOScheduler:
        return self._scheduler
