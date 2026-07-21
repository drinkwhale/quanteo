"""ScreenerNotifier 단위 테스트."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from screener.agents.analyst_agent import StockSummary
from screener.notify.telegram_reporter import ScreenerNotifier


def _make_notifier(tg=None):
    tg = tg or AsyncMock()
    tg.send_raw = AsyncMock()
    return ScreenerNotifier(telegram_notifier=tg), tg


def _ranked_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rank": [1, 2],
            "ticker": ["005930", "000660"],
            "name": ["삼성전자", "SK하이닉스"],
            "weighted_score": [4.2, 3.8],
            "per": [12.3, 15.0],
            "foreign_institution_streak": [5, 0],
            "volume_surge_ratio": [2.1, 1.0],
        }
    )


class TestSendDailyReport:
    @pytest.mark.asyncio
    async def test_sends_header_plus_one_message_per_stock(self) -> None:
        notifier, tg = _make_notifier()

        await notifier.send_daily_report(_ranked_df(), top_n=10)

        # 헤더 1건 + 종목 2건 = 3건
        assert tg.send_raw.call_count == 3

    @pytest.mark.asyncio
    async def test_stock_message_excludes_llm_summary_markers(self) -> None:
        notifier, tg = _make_notifier()

        await notifier.send_daily_report(_ranked_df(), top_n=10)

        stock_calls = tg.send_raw.call_args_list[1:]
        for c in stock_calls:
            text = c.args[0]
            assert "💡" not in text
            assert "✅" not in text
            assert "⚠️" not in text

    @pytest.mark.asyncio
    async def test_stock_message_includes_quant_fields(self) -> None:
        notifier, tg = _make_notifier()

        await notifier.send_daily_report(_ranked_df(), top_n=10)

        first_text = tg.send_raw.call_args_list[1].args[0]
        assert "삼성전자" in first_text
        assert "005930" in first_text
        assert "12.3" in first_text
        assert "5일 연속" in first_text

    @pytest.mark.asyncio
    async def test_respects_top_n(self) -> None:
        notifier, tg = _make_notifier()

        await notifier.send_daily_report(_ranked_df(), top_n=1)

        assert tg.send_raw.call_count == 2  # 헤더 1 + 종목 1

    @pytest.mark.asyncio
    async def test_includes_watchlist_keyboard(self) -> None:
        notifier, tg = _make_notifier()

        await notifier.send_daily_report(_ranked_df(), top_n=10)

        _, kwargs = tg.send_raw.call_args_list[1]
        markup = kwargs["reply_markup"]
        callback_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "watchlist_add:005930" in callback_data
        assert "detail:005930" in callback_data
        assert "ignore:005930" in callback_data


class TestSendDailyReportWithSummaries:
    @pytest.mark.asyncio
    async def test_includes_llm_markers_for_summarized_stock(self) -> None:
        notifier, tg = _make_notifier()
        summaries = {
            "005930": StockSummary(
                ticker="005930",
                name="삼성전자",
                one_line_thesis="메모리 업턴 초입",
                protips=["영업이익률 개선"],
                risk_flags=["최근 유상증자 공시"],
                score_breakdown={},
            )
        }

        await notifier.send_daily_report_with_summaries(_ranked_df(), summaries, top_n=10)

        first_text = tg.send_raw.call_args_list[1].args[0]
        assert "💡 메모리 업턴 초입" in first_text
        assert "✅ 영업이익률 개선" in first_text
        assert "⚠️ 최근 유상증자 공시" in first_text

    @pytest.mark.asyncio
    async def test_stock_without_summary_gets_quant_only(self) -> None:
        notifier, tg = _make_notifier()

        await notifier.send_daily_report_with_summaries(_ranked_df(), summaries={}, top_n=10)

        second_text = tg.send_raw.call_args_list[2].args[0]
        assert "💡" not in second_text
        assert "SK하이닉스" in second_text


class TestRetryAndDlq:
    @pytest.mark.asyncio
    async def test_retries_before_giving_up(self, monkeypatch) -> None:
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        tg = AsyncMock()
        tg.send_raw = AsyncMock(side_effect=[Exception("fail1"), Exception("fail2"), None])
        notifier = ScreenerNotifier(telegram_notifier=tg)

        await notifier._send_raw("test")

        assert tg.send_raw.call_count == 3
        assert notifier.dlq_size == 0

    @pytest.mark.asyncio
    async def test_dlq_after_exhausting_retries(self, monkeypatch) -> None:
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        tg = AsyncMock()
        tg.send_raw = AsyncMock(side_effect=Exception("always fails"))
        notifier = ScreenerNotifier(telegram_notifier=tg)

        await notifier._send_raw("test")

        assert notifier.dlq_size == 1

    @pytest.mark.asyncio
    async def test_retry_dlq_drains_queue(self, monkeypatch) -> None:
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        tg = AsyncMock()
        tg.send_raw = AsyncMock(side_effect=Exception("always fails"))
        notifier = ScreenerNotifier(telegram_notifier=tg)
        await notifier._send_raw("test")
        assert notifier.dlq_size == 1

        tg.send_raw = AsyncMock(return_value=None)  # 이제 성공
        await notifier.retry_dlq()

        assert notifier.dlq_size == 0
