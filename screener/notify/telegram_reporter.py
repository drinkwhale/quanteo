"""정량 데이터 리포트 발송 (LLM 요약 없음).

core/notifier/TelegramNotifier를 생성자 주입으로 받아 래핑한다 — T062
InfoNotifier와 동일한 중복 구현 금지 원칙. 스펙 7.2절 포맷에서 LLM 요약
항목(💡, ✅, ⚠️)만 제외한, 순위·스코어·핵심 지표(PER, 수급)만 발송한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
import pytz
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from screener.agents.analyst_agent import StockSummary

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")
_MAX_RETRIES = 3
_DLQ_MAX = 100
_INITIAL_RETRY_DELAY = 1.0


@dataclass
class _DlqItem:
    text: str
    reply_markup: InlineKeyboardMarkup | None = None
    failed_at: datetime = field(default_factory=lambda: datetime.now(tz=pytz.UTC))


def _watchlist_keyboard(ticker: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="워치리스트 등록", callback_data=f"watchlist_add:{ticker}"),
                InlineKeyboardButton(text="상세보기", callback_data=f"detail:{ticker}"),
                InlineKeyboardButton(text="무시", callback_data=f"ignore:{ticker}"),
            ]
        ]
    )


class ScreenerNotifier:
    """Stock Miner 리포트 전용 Telegram 발송기."""

    def __init__(self, telegram_notifier) -> None:
        self._tg = telegram_notifier
        self._dlq: asyncio.Queue[_DlqItem] = asyncio.Queue(maxsize=_DLQ_MAX)

    # ------------------------------------------------------------------
    # 발송 핵심 (T062 InfoNotifier._send_text와 동일한 재시도/DLQ 정책)
    # ------------------------------------------------------------------

    async def _send_raw(self, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        delay = _INITIAL_RETRY_DELAY
        for attempt in range(_MAX_RETRIES):
            try:
                await self._tg.send_raw(text, reply_markup=reply_markup)
                return
            except Exception as exc:
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(
                        "Telegram 발송 실패, %.0fs 후 재시도 (%d/%d): %s",
                        delay,
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logger.error("Telegram 발송 3회 소진 — DLQ 적재: %s", exc)
                    if not self._dlq.full():
                        await self._dlq.put(_DlqItem(text=text, reply_markup=reply_markup))
                    else:
                        logger.critical(
                            "DLQ 포화(%d/%d) — 알람 영구 유실: %.100s",
                            self._dlq.qsize(),
                            _DLQ_MAX,
                            text,
                        )

    async def retry_dlq(self) -> None:
        """DLQ를 소진한다 (스케줄러 주기 호출)."""
        items: list[_DlqItem] = []
        while not self._dlq.empty():
            try:
                items.append(self._dlq.get_nowait())
            except asyncio.QueueEmpty:
                break
        for item in items:
            await self._send_raw(item.text, item.reply_markup)

    @property
    def dlq_size(self) -> int:
        return self._dlq.qsize()

    async def send_error_alert(self, message: str) -> None:
        """정상 리포트와 구분되는 파이프라인 오류 알림 (DailyJob 재시도 소진 시 호출)."""
        await self._send_raw(f"🚨 {message}")

    # ------------------------------------------------------------------
    # 리포트 포맷
    # ------------------------------------------------------------------

    async def send_daily_report(self, ranked: pd.DataFrame, top_n: int = 10) -> None:
        """상위 `top_n`개 종목을 정량 데이터만으로(LLM 요약 없이) 발송한다.

        Args:
            ranked: `ranker.rank_top_n()` 출력 (rank, ticker, name, weighted_score,
                per, foreign_institution_streak 등 컬럼 포함 가정. 없는 컬럼은
                건너뛴다).
        """
        today = datetime.now(tz=KST).strftime("%Y-%m-%d")
        header = f"📊 오늘의 발굴 종목 ({today})"
        await self._send_raw(header)

        for _, row in ranked.head(top_n).iterrows():
            text = self._format_stock_line(row)
            keyboard = _watchlist_keyboard(str(row.get("ticker", "")))
            await self._send_raw(text, reply_markup=keyboard)

    async def send_daily_report_with_summaries(
        self, ranked: pd.DataFrame, summaries: dict[str, StockSummary], top_n: int = 10
    ) -> None:
        """정량 리포트에 T106 AnalystAgent의 LLM 요약(💡/✅/⚠️)을 덧붙여 발송한다.

        `summaries`에 없는 티커는 정량 데이터만(send_daily_report()와 동일하게) 발송한다
        — AnalystAgent 개별 실패가 있어도 리포트 자체는 무음 누락 없이 계속 발송된다.
        """
        today = datetime.now(tz=KST).strftime("%Y-%m-%d")
        header = f"📊 오늘의 발굴 종목 ({today})"
        await self._send_raw(header)

        for _, row in ranked.head(top_n).iterrows():
            ticker = str(row.get("ticker", ""))
            text = self._format_stock_line(row)

            summary = summaries.get(ticker)
            if summary is not None:
                text += f"\n💡 {summary.one_line_thesis}"
                for tip in summary.protips:
                    text += f"\n✅ {tip}"
                for flag in summary.risk_flags:
                    text += f"\n⚠️ {flag}"
                if summary.bbc_principle is not None:
                    text += f"\n📐 박병창 매수 원칙: 제{summary.bbc_principle}원칙 — {summary.bbc_reason}"

            keyboard = _watchlist_keyboard(ticker)
            await self._send_raw(text, reply_markup=keyboard)

    def _format_stock_line(self, row: pd.Series) -> str:
        rank = row.get("rank", "?")
        name = row.get("name", row.get("ticker", "?"))
        ticker = row.get("ticker", "?")
        score = row.get("weighted_score")
        score_str = f"{score:.1f}/5" if score is not None and not pd.isna(score) else "N/A"

        lines = [f"{rank}️⃣ {name} ({ticker}) — 종합 {score_str}"]

        per = row.get("per")
        if per is not None and not pd.isna(per):
            lines.append(f"📈 PER {per:.1f}")

        streak = row.get("foreign_institution_streak")
        if streak is not None and not pd.isna(streak) and streak > 0:
            lines.append(f"외인+기관 {int(streak)}일 연속 순매수")

        surge = row.get("volume_surge_ratio")
        if surge is not None and not pd.isna(surge):
            lines.append(f"거래량 {surge:.1f}배")

        return "\n".join(lines)
