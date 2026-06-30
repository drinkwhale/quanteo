"""
InfoNotifier — 정보 수집 서브시스템 전용 Telegram 알람 포맷터.

기존 core/notifier/TelegramNotifier를 생성자 주입으로 받아 래핑한다.
발송 실패 시 지수 백오프 3회 재시도, 소진 시 dead-letter queue 보존.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import pytz

if TYPE_CHECKING:
    from info.ai_filter.claude_filter import FilterResult
    from info.calendar.earnings_data import EarningsEvent
    from info.fx.rate_monitor import FxSnapshot
    from info.fx.daily_report import FxDailyReport
    from info.news.rss_collector import NewsItem

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")
_MAX_RETRIES = 3
_DLQ_MAX = 100
_INITIAL_RETRY_DELAY = 1.0  # 지수 백오프 초기 지연 (초)


@dataclass
class _DlqItem:
    """Dead-letter queue 아이템."""

    text: str
    failed_at: datetime = field(default_factory=lambda: datetime.now(tz=pytz.UTC))


class InfoNotifier:
    """정보 수집·알람 전용 Telegram 알람 발송기."""

    def __init__(self, telegram_notifier, chat_id: str = "") -> None:
        self._tg = telegram_notifier
        self._chat_id = chat_id
        self._dlq: asyncio.Queue = asyncio.Queue(maxsize=_DLQ_MAX)

    # ------------------------------------------------------------------
    # 발송 핵심
    # ------------------------------------------------------------------

    async def _send_text(self, text: str) -> None:
        """지수 백오프 재시도 후 실패 시 DLQ에 보관."""
        from core.notifier.base import NotifyEvent, NotifyLevel

        delay = _INITIAL_RETRY_DELAY
        for attempt in range(_MAX_RETRIES):
            try:
                await self._tg.send(
                    NotifyEvent(
                        level=NotifyLevel.INFO,
                        title="",
                        body=text,
                        source="InfoNotifier",
                    )
                )
                return
            except Exception as exc:
                if attempt < _MAX_RETRIES - 1:
                    logger.warning("Telegram 발송 실패, %.0fs 후 재시도 (%d/%d): %s", delay, attempt + 1, _MAX_RETRIES, exc)
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logger.error("Telegram 발송 3회 소진 — DLQ 적재: %s", exc)
                    if not self._dlq.full():
                        await self._dlq.put(_DlqItem(text=text))
                    else:
                        logger.critical(
                            "DLQ 포화(%d/%d) — 알람 영구 유실: %.100s",
                            self._dlq.qsize(), _DLQ_MAX, text,
                        )

    async def retry_dlq(self) -> None:
        """DLQ를 소진한다 (스케줄러 5분 간격 호출)."""
        items: list[_DlqItem] = []
        while not self._dlq.empty():
            try:
                items.append(self._dlq.get_nowait())
            except asyncio.QueueEmpty:
                break

        for item in items:
            await self._send_text(item.text)

    # ------------------------------------------------------------------
    # 알람 포맷 함수
    # ------------------------------------------------------------------

    async def send_news_alert(self, item: "NewsItem", result: "FilterResult") -> None:
        """스펙 4-1절 뉴스 알람 포맷."""
        score_emoji = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "ℹ️"}.get(result.score, "ℹ️")
        action_emoji = {"매수검토": "🟢", "매도검토": "🔴", "관망": "🟡"}.get(result.action, "🟡")
        now_kst = datetime.now(tz=KST).strftime("%H:%M:%S")

        text = (
            f"{score_emoji} [{result.score}] 매크로 뉴스 알람\n\n"
            f"📰 {item.title}\n"
            f"🔗 {item.url}\n\n"
            f"📋 분석: {result.reason}\n"
            f"{action_emoji} 대응: {result.action}\n\n"
            f"⏰ {now_kst} KST"
        )
        await self._send_text(text)

    async def send_earnings_alert(self, event: "EarningsEvent") -> None:
        """스펙 4-2절 실적발표 사전 알람 포맷."""
        importance_emoji = {"🔴 최고": "🔴", "🔴 높음": "🔴", "🟡 중간": "🟡"}.get(
            event.sk_impact, "⚠️"
        )
        start_str = event.start.strftime("%Y-%m-%d %H:%M KST")

        eps = event.consensus_eps or "미정"
        sales = event.consensus_sales or "미정"

        text = (
            f"⏰ 실적발표 1시간 전 알람\n\n"
            f"🏢 {event.summary} ({event.ticker})\n"
            f"📅 {start_str} ({event.timing})\n"
            f"{importance_emoji} 중요도: {event.sk_impact}\n\n"
            f"💡 SK하이닉스 연관:\n{event.description}\n\n"
            f"📊 컨센서스:\n"
            f"  EPS 예상: {eps}\n"
            f"  매출 예상: {sales}"
        )
        await self._send_text(text)

    async def send_fx_alert(self, snapshot: "FxSnapshot") -> None:
        """스펙 4-3절 환율 급변 알람 포맷."""
        now_kst = datetime.now(tz=KST).strftime("%H:%M:%S")

        usd_chg = f"{snapshot.usdkrw_change_pct:+.2f}%"
        dxy_chg = f"{snapshot.dxy_change_pct:+.2f}%"

        usd_analysis = (
            "원화 약세 — SK하이닉스 수출 이익 증가"
            if snapshot.usdkrw_change_pct > 0
            else "원화 강세 — SK하이닉스 수출 이익 감소"
        )

        text = (
            f"💱 환율 급변 알람\n\n"
            f"USD/KRW: {snapshot.usdkrw:.2f} ({usd_chg})\n"
            f"DXY: {snapshot.dxy:.2f} ({dxy_chg})\n\n"
            f"📋 분석: {usd_analysis}\n"
            f"⏰ {now_kst} KST"
        )
        await self._send_text(text)

    async def send_fx_daily_report(self, report: "FxDailyReport") -> None:
        """스펙 4-4절 일일 환율 마감 리포트 포맷."""
        date_str = report.date.strftime("%Y-%m-%d")

        text = (
            f"📊 환율 일일 마감 리포트\n\n"
            f"💵 USD/KRW: {report.usdkrw:.2f} ({report.usdkrw_change_pct:+.2f}%)\n"
            f"📈 DXY:     {report.dxy:.2f} ({report.dxy_change_pct:+.2f}%)\n"
            f"🇯🇵 JPY/KRW: {report.jpykrw:.2f} ({report.jpykrw_change_pct:+.2f}%)\n"
            f"🇨🇳 CNY/KRW: {report.cnykrw:.2f} ({report.cnykrw_change_pct:+.2f}%)\n\n"
            f"{report.summary}\n"
            f"⏰ 기준: {date_str} 종가"
        )
        await self._send_text(text)

    async def send_morning_brief(self, events: list) -> None:
        """08:00 장전 당일 일정 브리핑."""
        if not events:
            text = "📅 오늘 주요 일정: 없음"
        else:
            lines = ["📅 오늘 주요 일정\n"]
            for ev in events:
                time_str = ev.start.strftime("%H:%M KST") if hasattr(ev, "start") else ""
                lines.append(f"• {ev.summary} {time_str}")
            text = "\n".join(lines)

        await self._send_text(text)
