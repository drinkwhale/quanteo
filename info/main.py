"""
info 서브시스템 진입점.

InfoSystem이 모든 컴포넌트를 조립하고 라이프사이클을 관리한다.
의존성 주입 패턴 — Settings를 받아 각 컴포넌트를 내부에서 생성한다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from core.config.settings import Settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_DLQ_RETRY_INTERVAL = 300  # 5분 (초 단위)


class InfoSystem:
    """정보 수집·알람 서브시스템 (Phase 10) — 전체 컴포넌트 조립 및 라이프사이클."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._dlq_task: asyncio.Task | None = None
        self._build_components()

    def _build_components(self) -> None:
        cfg = self._settings.info

        # 컴포넌트 하나가 실패해도 "InfoSystem 초기화 실패"라는 뭉뚱그린 로그만
        # 남던 문제 — 어떤 컴포넌트가, 어떤 설정 때문에 실패했는지 여기서 먼저
        # 남기고 그대로 재발생시킨다 (호출자인 core.app.run()이 최종적으로 잡는다).
        def _build(step: str, factory):
            try:
                return factory()
            except Exception:
                logger.exception("InfoSystem 컴포넌트 초기화 실패: %s", step)
                raise

        # ── AI 필터 ────────────────────────────────────────────────────────
        def _make_claude_filter():
            from info.ai_filter.claude_filter import ClaudeFilter

            return ClaudeFilter(api_key=cfg.anthropic_api_key)

        self.claude_filter = _build(
            "ClaudeFilter (info.anthropic.api_key 확인)", _make_claude_filter
        )

        # ── Google Calendar ─────────────────────────────────────────────────
        def _make_calendar_client():
            from info.calendar.google_cal import GoogleCalendarClient

            creds_path = (
                cfg.google_calendar_credentials_path or "~/.quanteo/google/credentials.json"
            )
            return GoogleCalendarClient(credentials_path=creds_path)

        self.calendar_client = _build(
            "GoogleCalendarClient (info.google_calendar.credentials_path 확인)",
            _make_calendar_client,
        )

        # ── Telegram 노티파이어 (뉴스·환율 컴포넌트보다 먼저 생성) ───────────
        def _make_notifier():
            from core.notifier.factory import make_notifier
            from info.telegram.info_notifier import InfoNotifier

            base_notifier = make_notifier(self._settings)
            chat_id = cfg.telegram_chat_id or getattr(
                getattr(self._settings, "telegram", None), "chat_id", ""
            )
            return InfoNotifier(telegram_notifier=base_notifier, chat_id=chat_id)

        self.notifier = _build("InfoNotifier (telegram 설정 확인)", _make_notifier)

        # ── 뉴스 수집기 ────────────────────────────────────────────────────
        def _make_rss_collector():
            from info.news.rss_collector import RssCollector

            return RssCollector(claude_filter=self.claude_filter)

        self.rss_collector = _build("RssCollector", _make_rss_collector)

        def _make_finnhub_collector():
            from info.news.finnhub_collector import FinnhubCollector

            return FinnhubCollector(
                api_key=cfg.finnhub_api_key,
                claude_filter=self.claude_filter,
            )

        self.finnhub_collector = _build(
            "FinnhubCollector (info.finnhub.api_key 확인)", _make_finnhub_collector
        )

        # ── 환율 모니터 (생성자에서 notifier 주입) ─────────────────────────
        def _make_fx_monitor():
            from info.fx.rate_monitor import FxRateMonitor

            return FxRateMonitor(info_notifier=self.notifier)

        self.fx_monitor = _build("FxRateMonitor", _make_fx_monitor)

        def _make_fx_reporter():
            from info.fx.daily_report import FxDailyReporter

            return FxDailyReporter(info_notifier=self.notifier)

        self.fx_reporter = _build("FxDailyReporter", _make_fx_reporter)

        # ── 스케줄러 (모든 컴포넌트 준비 후 마지막에 생성) ─────────────────
        def _make_scheduler():
            from info.scheduler import InfoScheduler

            return InfoScheduler(system=self)

        self._scheduler = _build("InfoScheduler", _make_scheduler)

    async def start(self) -> None:
        """서브시스템 시작 (스케줄러 기동 + DLQ 재시도 루프)."""
        logger.info("InfoSystem 시작 중...")
        self._scheduler.start()
        self._dlq_task = asyncio.create_task(self._dlq_loop(), name="info-dlq-retry")
        logger.info("InfoSystem 시작 완료")

    async def stop(self) -> None:
        """서브시스템 정상 종료."""
        self._scheduler.stop()
        if self._dlq_task and not self._dlq_task.done():
            self._dlq_task.cancel()
            try:
                await self._dlq_task
            except asyncio.CancelledError:
                pass
        logger.info("InfoSystem 종료")

    async def _dlq_loop(self) -> None:
        """5분 간격으로 DLQ 적재 메시지 재발송 시도."""
        while True:
            try:
                await asyncio.sleep(_DLQ_RETRY_INTERVAL)
                await self.notifier.retry_dlq()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("DLQ 재시도 루프 오류: %s", exc)
