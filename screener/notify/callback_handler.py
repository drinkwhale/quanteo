"""워치리스트 등록 인터랙션 (bounded autonomy).

리포트 메시지의 인라인 버튼(워치리스트 등록/상세보기/무시) 콜백을 처리한다.

⚠️ 자동 매매 연동 금지: 이 모듈은 core/execution/ Order Executor를
import하지 않는다. 워치리스트 등록은 상태 기록만 수행하며, 실행 경로로
이어지지 않는다 (스펙 7.3절 경계 준수) — 정적 검증은
tests/screener/test_callback_handler.py 참고.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from aiogram import Dispatcher, F
from aiogram.types import CallbackQuery

if TYPE_CHECKING:
    from core.store.db import StateStore
    from screener.scheduler.daily_job import DailyJob

logger = logging.getLogger(__name__)


class CallbackHandler:
    """Stock Miner 리포트 인라인 버튼 콜백 처리기.

    Args:
        store: 워치리스트 upsert 대상 StateStore.
        job: 오늘자 LLM 요약(`last_summaries`)을 조회하기 위한 DailyJob 참조
            — "상세보기" 버튼이 재발송할 `StockSummary` 전체 데이터 소스.
    """

    def __init__(self, store: StateStore, job: DailyJob) -> None:
        self._store = store
        self._job = job

    def register(self, dp: Dispatcher) -> None:
        """aiogram Dispatcher에 콜백 라우트를 등록한다."""
        dp.callback_query.register(self.on_watchlist_add, F.data.startswith("watchlist_add:"))
        dp.callback_query.register(self.on_detail, F.data.startswith("detail:"))
        dp.callback_query.register(self.on_ignore, F.data.startswith("ignore:"))

    @staticmethod
    def _parse_ticker(callback_data: str) -> str:
        return callback_data.split(":", 1)[1]

    async def on_watchlist_add(self, callback: CallbackQuery) -> None:
        """"워치리스트 등록" — 유일하게 상태를 변경하는 액션."""
        ticker = self._parse_ticker(callback.data)
        summary = self._job.last_summaries.get(ticker)
        name = summary.name if summary else ticker
        score_snapshot = summary.score_breakdown if summary else {}

        await self._store.upsert_watchlist(symbol=ticker, name=name, score_snapshot=score_snapshot)
        logger.info("워치리스트 등록: %s (%s)", name, ticker)
        await callback.answer("워치리스트에 등록했습니다.")

    async def on_detail(self, callback: CallbackQuery) -> None:
        """"상세보기" — StockSummary 전체를 별도 메시지로 재발송한다."""
        ticker = self._parse_ticker(callback.data)
        summary = self._job.last_summaries.get(ticker)
        if summary is None:
            await callback.answer("상세 정보를 찾을 수 없습니다 (만료됨).", show_alert=True)
            return

        detail = {
            "ticker": summary.ticker,
            "name": summary.name,
            "one_line_thesis": summary.one_line_thesis,
            "protips": summary.protips,
            "risk_flags": summary.risk_flags,
            "score_breakdown": summary.score_breakdown,
        }
        text = json.dumps(detail, ensure_ascii=False, indent=2)
        await callback.message.answer(f"<pre>{text}</pre>")
        await callback.answer()

    async def on_ignore(self, callback: CallbackQuery) -> None:
        """"무시" — 정보 제공 목적이므로 상태 변경 없이 로그만 남긴다."""
        ticker = self._parse_ticker(callback.data)
        logger.info("종목 무시: %s (상태 변경 없음)", ticker)
        await callback.answer("무시했습니다.")
