"""DailyJob / DailyJobScheduler 단위 테스트."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from screener.agents.analyst_agent import StockSummary
from screener.data.collectors.dart_client import FinancialStatement
from screener.pipeline.screener import ScreenerConfig
from screener.scheduler.daily_job import DailyJob, DailyJobScheduler


def _universe_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["005930"],
            "name": ["삼성전자"],
            "sector": ["반도체"],
            "market": ["KOSPI"],
            "close": [70000],
            "volume": [1_000_000],
            "trading_value": [70_000_000_000],
            "market_cap": [400_000_000_000_000],
            "per": [12.0],
            "pbr": [1.2],
        }
    )


def _make_job(**overrides) -> tuple[DailyJob, dict]:
    pykrx = AsyncMock()
    pykrx.fetch_universe = AsyncMock(return_value=_universe_df())
    pykrx.fetch_investor_trading = AsyncMock(
        return_value=pd.DataFrame({"ticker": ["005930"], "foreign_net": [100], "institution_net": [100]})
    )
    # 히스토리 없음(빈 DataFrame) → assess_buy_principle이 캔들 부족으로 None 반환
    pykrx.fetch_ohlcv_history = AsyncMock(return_value=pd.DataFrame())

    dart = AsyncMock()
    dart.fetch_financials = AsyncMock(
        return_value=FinancialStatement(corp_code="005930", years=[])
    )
    dart.fetch_recent_disclosures = AsyncMock(return_value=[])

    analyst = AsyncMock()
    analyst.summarize_batch = AsyncMock(
        return_value={
            "005930": StockSummary(
                ticker="005930",
                name="삼성전자",
                one_line_thesis="테스트",
                protips=[],
                risk_flags=[],
                score_breakdown={},
            )
        }
    )

    notifier = AsyncMock()
    notifier.send_daily_report_with_summaries = AsyncMock()
    notifier.send_error_alert = AsyncMock()

    config = ScreenerConfig(min_market_cap=0, min_avg_trading_value_20d=0, exclude_administrative=False)

    mocks = {"pykrx": pykrx, "dart": dart, "analyst": analyst, "notifier": notifier}
    job = DailyJob(
        pykrx_client=pykrx,
        dart_client=dart,
        analyst_agent=analyst,
        notifier=notifier,
        screener_config=config,
        **overrides,
    )
    return job, mocks


class TestDailyJobRun:
    @pytest.mark.asyncio
    async def test_full_pipeline_sends_report(self) -> None:
        job, mocks = _make_job()

        await job.run("20260721")

        mocks["notifier"].send_daily_report_with_summaries.assert_called_once()
        mocks["analyst"].summarize_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_items_built_correctly_per_ticker(self) -> None:
        job, mocks = _make_job()

        await job.run("20260721")

        mocks["analyst"].summarize_batch.assert_called_once()
        batch_items = mocks["analyst"].summarize_batch.call_args.args[0]
        assert len(batch_items) == 1
        stock, disclosures, bbc_signal = batch_items[0]
        assert stock.ticker == "005930"
        assert stock.name == "삼성전자"
        assert disclosures == []  # dart.fetch_recent_disclosures가 [] 반환
        assert bbc_signal is None  # 히스토리 없음 → assess_buy_principle이 None 반환

    @pytest.mark.asyncio
    async def test_empty_universe_alerts_instead_of_silent_skip(self, monkeypatch) -> None:
        # fetch_universe는 내부적으로 최대 7영업일 폴백을 이미 시도한 뒤에도 비어
        # 있다면 실제 휴장일이 아니라 KRX 응답 실패(로그인 차단 등)일 가능성이 높다
        # — 조용히 스킵하면 리포트 누락이 사용자에게 전혀 알려지지 않으므로, 예외로
        # 올려 기존 재시도+알림 경로를 타도록 한다.
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        job, mocks = _make_job()
        mocks["pykrx"].fetch_universe = AsyncMock(return_value=pd.DataFrame())

        await job.run("20260721")

        mocks["notifier"].send_daily_report_with_summaries.assert_not_called()
        mocks["notifier"].send_error_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_after_filter_alerts_instead_of_silent_skip(self, monkeypatch) -> None:
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        _, mocks = _make_job()
        job = DailyJob(
            pykrx_client=mocks["pykrx"],
            dart_client=mocks["dart"],
            analyst_agent=mocks["analyst"],
            notifier=mocks["notifier"],
            screener_config=ScreenerConfig(
                min_market_cap=10**20, min_avg_trading_value_20d=0, exclude_administrative=False
            ),
        )

        await job.run("20260721")

        mocks["notifier"].send_daily_report_with_summaries.assert_not_called()
        mocks["notifier"].send_error_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_alerts(self, monkeypatch) -> None:
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        job, mocks = _make_job()
        mocks["pykrx"].fetch_universe = AsyncMock(side_effect=Exception("KRX down"))

        await job.run("20260721")

        assert mocks["pykrx"].fetch_universe.call_count == 3
        mocks["notifier"].send_error_alert.assert_called_once()
        alert_text = mocks["notifier"].send_error_alert.call_args.args[0]
        assert "파이프라인 실패" in alert_text

    @pytest.mark.asyncio
    async def test_recovers_after_transient_failure(self, monkeypatch) -> None:
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        job, mocks = _make_job()

        call_count = 0

        async def flaky_fetch_universe(date):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("transient")
            return _universe_df()

        mocks["pykrx"].fetch_universe = flaky_fetch_universe

        await job.run("20260721")

        mocks["notifier"].send_error_alert.assert_not_called()
        mocks["notifier"].send_daily_report_with_summaries.assert_called_once()

    @pytest.mark.asyncio
    async def test_defaults_date_to_today_kst(self) -> None:
        job, mocks = _make_job()

        await job.run()

        # fetch_universe는 20일 평균 거래대금 계산에도 재사용되어 여러 번 호출된다 —
        # 첫 호출(메인 조회)이 today(YYYYMMDD) 포맷인지만 확인한다.
        first_call_date = mocks["pykrx"].fetch_universe.call_args_list[0].args[0]
        assert len(first_call_date) == 8
        assert first_call_date.isdigit()


class TestDailyJobScheduler:
    def test_registers_cron_job_with_kst_timezone(self) -> None:
        job, _ = _make_job()
        scheduler = DailyJobScheduler(job)

        jobs = scheduler.scheduler.get_jobs()
        assert len(jobs) == 1
        trigger = jobs[0].trigger
        assert str(trigger.timezone) == "Asia/Seoul"

    def test_cron_fields_match_1830_weekdays(self) -> None:
        job, _ = _make_job()
        scheduler = DailyJobScheduler(job)

        trigger = scheduler.scheduler.get_jobs()[0].trigger
        field_map = {f.name: str(f) for f in trigger.fields}
        assert field_map["hour"] == "18"
        assert field_map["minute"] == "30"
        assert field_map["day_of_week"] == "mon-fri"

    def test_misfire_and_coalesce_configured(self) -> None:
        job, _ = _make_job()
        scheduler = DailyJobScheduler(job)

        j = scheduler.scheduler.get_jobs()[0]
        assert j.misfire_grace_time == 300
        assert j.coalesce is True

    @pytest.mark.asyncio
    async def test_run_job_exception_does_not_propagate(self, monkeypatch) -> None:
        job, mocks = _make_job()
        job.run = AsyncMock(side_effect=Exception("boom"))
        scheduler = DailyJobScheduler(job)

        await scheduler._run_job()  # 예외가 전파되지 않아야 함 (스케줄러 중단 방지)
