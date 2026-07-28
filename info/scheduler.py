"""
info 서브시스템 APScheduler 스케줄러.

AsyncIOScheduler(timezone="Asia/Seoul") 기반으로 7개 잡을 등록한다.
잡 내부 예외는 try/except로 격리하여 스케줄러 중단을 방지한다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import time
from typing import TYPE_CHECKING

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from info.main import InfoSystem

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

# 국내 장 운영 시간
_MARKET_OPEN = time(9, 0)
_MARKET_CLOSE = time(15, 30)
# 미국 장(KST 기준)
_US_SESSION_START = time(22, 0)
_US_SESSION_END = time(6, 0)

# 뉴스 폴링(국내 RSS·미국 뉴스·모닝브리핑 뉴스 파트)이 Claude API를 과도하게
# 호출해 비용이 급증했다 — CRITICAL_KEYWORDS(info/ai_filter/claude_filter.py)
# 사전 필터가 지나치게 광범위해 신규 기사 대부분이 실제 호출로 이어짐.
# 재검토 전까지 이 플래그 하나로 뉴스 관련 3개 잡 본문을 전부 비활성화한다
# (잡 등록 자체는 유지 — 재활성화는 이 값을 True로 되돌리기만 하면 된다).
_NEWS_POLLING_ENABLED = False


def _in_kr_market_hours() -> bool:
    from datetime import datetime
    now_time = datetime.now(KST).time()
    return _MARKET_OPEN <= now_time <= _MARKET_CLOSE


def _in_us_session() -> bool:
    from datetime import datetime
    now_time = datetime.now(KST).time()
    return now_time >= _US_SESSION_START or now_time <= _US_SESSION_END


class InfoScheduler:
    """APScheduler 기반 정보 수집·알람 스케줄러 (7개 잡, 뉴스 관련 3개는 플래그로 비활성)."""

    def __init__(self, system: "InfoSystem") -> None:
        self._system = system
        self._scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
        self._register_jobs()

    def _register_jobs(self) -> None:
        kst = "Asia/Seoul"
        defaults: dict = {"misfire_grace_time": 60, "coalesce": True}

        # ① 08:00 KST — 당일 일정 브리핑 (뉴스 파트는 _NEWS_POLLING_ENABLED로 가드)
        self._scheduler.add_job(
            self._job_morning_brief,
            CronTrigger(hour=8, minute=0, timezone=kst),
            id="morning_brief",
            **defaults,
        )

        # ② 5분 간격 (09:00~15:30 내부 가드) — 국내 RSS 폴링
        # (_NEWS_POLLING_ENABLED=False면 잡은 등록되되 본문에서 즉시 반환)
        self._scheduler.add_job(
            self._job_domestic_rss,
            IntervalTrigger(minutes=5, timezone=kst),
            id="domestic_rss",
            **defaults,
        )

        # ③ 30분 간격 (09:00~15:30 내부 가드) — USD/KRW 환율 체크
        self._scheduler.add_job(
            self._job_fx_check,
            IntervalTrigger(minutes=30, timezone=kst),
            id="fx_check",
            **defaults,
        )

        # ④ 15:30 KST — 오늘 미국 장후 실적 예정 종목 Telegram 발송
        self._scheduler.add_job(
            self._job_us_earnings_alert,
            CronTrigger(hour=15, minute=30, timezone=kst),
            id="us_earnings_alert",
            **defaults,
        )

        # ⑤ 16:00 KST — 환율 일일 마감 리포트
        self._scheduler.add_job(
            self._job_fx_daily_report,
            CronTrigger(hour=16, minute=0, timezone=kst),
            id="fx_daily_report",
            **defaults,
        )

        # ⑥ 10분 간격 (22:00~06:00 내부 가드) — 미국 뉴스 폴링
        # (_NEWS_POLLING_ENABLED=False면 잡은 등록되되 본문에서 즉시 반환)
        self._scheduler.add_job(
            self._job_us_news,
            IntervalTrigger(minutes=10, timezone=kst),
            id="us_news",
            **defaults,
        )

        # ⑦ 매월 1일 00:00 KST — 다음 달 캘린더 자동 저장
        self._scheduler.add_job(
            self._job_monthly_calendar,
            CronTrigger(day=1, hour=0, minute=0, timezone=kst),
            id="monthly_calendar",
            **defaults,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 내부 헬퍼
    # ──────────────────────────────────────────────────────────────────────────

    async def _escalate(self, job_name: str, exc: Exception) -> None:
        """잡 오류를 Telegram으로 베스트에포트 에스컬레이션한다."""
        try:
            await self._system.notifier._send_text(
                f"⚠️ [InfoScheduler] {job_name} 잡 오류: {exc}"
            )
        except Exception:
            pass  # 에스컬레이션 자체 실패는 무시

    async def _notify_news_polling_disabled(self) -> None:
        """뉴스 폴링이 비활성 상태로 기동됐음을 Telegram으로 1회 알린다(베스트에포트).

        로그만으로는 "뉴스가 없어서 조용한 것"과 "기능이 꺼져서 조용한 것"을
        구분할 수 없어, 기동 시점에 운영자에게 명시적으로 알린다.
        """
        try:
            await self._system.notifier._send_text(
                "ℹ️ [InfoScheduler] 뉴스 폴링(국내 RSS·미국 뉴스·모닝브리핑 뉴스 파트) "
                "비활성 상태로 기동됨 — Claude API 비용 급증으로 임시 비활성화됨"
                "(_NEWS_POLLING_ENABLED=False). CRITICAL_KEYWORDS 재검토 후 재활성화 예정."
            )
        except Exception:
            pass  # 알림 자체 실패는 무시

    # ──────────────────────────────────────────────────────────────────────────
    # 잡 구현
    # ──────────────────────────────────────────────────────────────────────────

    async def _job_morning_brief(self) -> None:
        """① 08:00 KST: 장전 뉴스 수집 + 당일 일정 브리핑.

        뉴스 수집·Claude 분류 파트는 _NEWS_POLLING_ENABLED가 False면 스킵된다
        (②/⑥과 동일 사유 — Claude API 비용 급증).
        """
        try:
            sys = self._system
            if _NEWS_POLLING_ENABLED:
                items = await sys.rss_collector.fetch()
                for item in items:
                    result = await sys.claude_filter.classify(item.title, item.raw_body)
                    if result.score in ("HIGH", "CRITICAL"):
                        await sys.notifier.send_news_alert(item, result)
            from info.calendar.earnings_data import next_events as next_earn
            from info.calendar.macro_events import next_macro_events
            today_events = next_earn(days=1) + next_macro_events(days=1)
            await sys.notifier.send_morning_brief(today_events)
        except Exception as exc:
            logger.error("morning_brief 잡 오류: %s", exc, exc_info=True)
            await self._escalate("morning_brief", exc)

    async def _job_domestic_rss(self) -> None:
        """② 5분 간격 (09:00~15:30): 국내 RSS 폴링 + HIGH 알람.

        _NEWS_POLLING_ENABLED가 False면 즉시 반환한다(Claude API 비용 급증으로 비활성화).
        """
        if not _NEWS_POLLING_ENABLED:
            return
        if not _in_kr_market_hours():
            return
        try:
            sys = self._system
            items = await sys.rss_collector.fetch()
            for item in items:
                result = await sys.claude_filter.classify(item.title, item.raw_body)
                if result.score == "HIGH":
                    await sys.notifier.send_news_alert(item, result)
        except Exception as exc:
            logger.error("domestic_rss 잡 오류: %s", exc, exc_info=True)

    async def _job_fx_check(self) -> None:
        """③ 30분 간격 (09:00~15:30): USD/KRW 환율 급변 체크."""
        if not _in_kr_market_hours():
            return
        try:
            await self._system.fx_monitor.check_and_alert()
        except Exception as exc:
            logger.error("fx_check 잡 오류: %s", exc, exc_info=True)

    async def _job_us_earnings_alert(self) -> None:
        """④ 15:30 KST: 오늘 미국 장후 실적 예정 종목 Telegram 발송."""
        try:
            from info.calendar.earnings_data import today_us_earnings
            events = today_us_earnings()
            if not events:
                logger.debug("오늘 미국 장후 실적 발표 없음 — 알람 스킵")
                return
            for ev in events:
                await self._system.notifier.send_earnings_alert(ev)
        except Exception as exc:
            logger.error("us_earnings_alert 잡 오류: %s", exc, exc_info=True)

    async def _job_fx_daily_report(self) -> None:
        """⑤ 16:00 KST: 환율 일일 마감 리포트 발송."""
        try:
            report = await self._system.fx_reporter.generate()
            await self._system.notifier.send_fx_daily_report(report)
        except Exception as exc:
            logger.error("fx_daily_report 잡 오류: %s", exc, exc_info=True)
            await self._escalate("fx_daily_report", exc)

    async def _job_us_news(self) -> None:
        """⑥ 10분 간격 (22:00~06:00): 미국 뉴스 폴링 (Finnhub·Yahoo).

        _NEWS_POLLING_ENABLED가 False면 즉시 반환한다(Claude API 비용 급증으로 비활성화).
        """
        if not _NEWS_POLLING_ENABLED:
            return
        if not _in_us_session():
            return
        try:
            sys = self._system
            items = await sys.finnhub_collector.fetch()
            for item in items:
                result = await sys.claude_filter.classify(item.title, item.raw_body)
                if result.score in ("HIGH", "CRITICAL"):
                    await sys.notifier.send_news_alert(item, result)
        except Exception as exc:
            logger.error("us_news 잡 오류: %s", exc, exc_info=True)

    async def _job_monthly_calendar(self) -> None:
        """⑦ 매월 1일 00:00 KST: 다음 달 캘린더 이벤트 자동 저장."""
        try:
            from info.calendar.earnings_data import next_events as next_earn
            from info.calendar.macro_events import next_macro_events
            events = next_earn(days=40) + next_macro_events(days=40)
            if events:
                await self._system.calendar_client.bulk_add(events)
                logger.info("다음 달 캘린더 이벤트 %d개 저장 완료", len(events))
        except Exception as exc:
            logger.error("monthly_calendar 잡 오류: %s", exc, exc_info=True)

    # ──────────────────────────────────────────────────────────────────────────
    # 라이프사이클
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._scheduler.start()
        logger.info(
            "InfoScheduler 시작 (잡 7개 등록, 뉴스 폴링 %s)",
            "활성" if _NEWS_POLLING_ENABLED else "비활성",
        )
        if not _NEWS_POLLING_ENABLED:
            asyncio.create_task(self._notify_news_polling_disabled())

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("InfoScheduler 종료")

    @property
    def scheduler(self) -> AsyncIOScheduler:
        return self._scheduler
