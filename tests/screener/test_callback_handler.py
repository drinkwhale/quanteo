"""CallbackHandler 단위 테스트."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from screener.agents.analyst_agent import StockSummary
from screener.notify.callback_handler import CallbackHandler

_CALLBACK_HANDLER_PATH = (
    Path(__file__).resolve().parents[2] / "screener" / "notify" / "callback_handler.py"
)


def _make_callback(data: str) -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    return callback


def _make_handler(summaries: dict | None = None):
    store = AsyncMock()
    store.upsert_watchlist = AsyncMock()

    job = MagicMock()
    job.last_summaries = summaries or {}

    return CallbackHandler(store=store, job=job), store, job


class TestOnWatchlistAdd:
    @pytest.mark.asyncio
    async def test_parses_ticker_and_upserts(self) -> None:
        handler, store, _ = _make_handler(
            summaries={
                "005930": StockSummary(
                    ticker="005930",
                    name="삼성전자",
                    one_line_thesis="t",
                    protips=[],
                    risk_flags=[],
                    score_breakdown={"growth": 4},
                )
            }
        )
        callback = _make_callback("watchlist_add:005930")

        await handler.on_watchlist_add(callback)

        store.upsert_watchlist.assert_called_once_with(
            symbol="005930", name="삼성전자", score_snapshot={"growth": 4}
        )
        callback.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_ticker_when_no_summary(self) -> None:
        handler, store, _ = _make_handler(summaries={})
        callback = _make_callback("watchlist_add:000660")

        await handler.on_watchlist_add(callback)

        store.upsert_watchlist.assert_called_once_with(
            symbol="000660", name="000660", score_snapshot={}
        )


class TestOnDetail:
    @pytest.mark.asyncio
    async def test_resends_full_summary_json(self) -> None:
        handler, _, _ = _make_handler(
            summaries={
                "005930": StockSummary(
                    ticker="005930",
                    name="삼성전자",
                    one_line_thesis="메모리 업턴",
                    protips=["영업이익률 개선"],
                    risk_flags=[],
                    score_breakdown={"growth": 4},
                )
            }
        )
        callback = _make_callback("detail:005930")

        await handler.on_detail(callback)

        callback.message.answer.assert_called_once()
        text = callback.message.answer.call_args.args[0]
        assert "메모리 업턴" in text
        assert "영업이익률 개선" in text

    @pytest.mark.asyncio
    async def test_missing_summary_shows_alert(self) -> None:
        handler, _, _ = _make_handler(summaries={})
        callback = _make_callback("detail:999999")

        await handler.on_detail(callback)

        callback.message.answer.assert_not_called()
        callback.answer.assert_called_once()
        assert callback.answer.call_args.kwargs.get("show_alert") is True


class TestOnIgnore:
    @pytest.mark.asyncio
    async def test_no_state_change(self) -> None:
        handler, store, job = _make_handler()
        callback = _make_callback("ignore:005930")

        await handler.on_ignore(callback)

        store.upsert_watchlist.assert_not_called()
        callback.answer.assert_called_once()


class TestOrderExecutorBoundary:
    def test_callback_handler_does_not_import_order_executor(self) -> None:
        """스펙 7.3절 경계: 워치리스트 등록은 core/execution/과 연결되지 않는다."""
        source = _CALLBACK_HANDLER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported_modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)

        assert not any("core.execution" in m for m in imported_modules), (
            f"core.execution import 발견 — 워치리스트 등록이 자동 매매와 연결되면 안 됩니다: {imported_modules}"
        )
