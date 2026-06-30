"""
DART 공시 수집기.

OpenDartReader를 사용해 SK하이닉스(기본) 최신 공시를 조회한다.
유상증자·전환사채·주요사항보고서 등 중요 공시는 HIGH 강제 처리.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import pytz

from info.news.rss_collector import NewsItem

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

# 중요 공시 유형 코드 (DART 기준)
IMPORTANT_REPORT_TYPES = {
    "유상증자결정",
    "전환사채권발행결정",
    "주요사항보고서",
    "대규모내부거래관련이사회결의",
    "주식관련사채권발행결정",
}

SK_HYNIX_CORP_CODE = "00164779"


class DartCollector:
    """DART 공시 수집기."""

    def __init__(
        self,
        api_key: str,
        info_notifier=None,
    ) -> None:
        self._api_key = api_key
        self._notifier = info_notifier

    async def fetch(self, corp_code: str = SK_HYNIX_CORP_CODE) -> list[NewsItem]:
        """최신 공시를 조회하고 중요 유형은 HIGH 강제로 알람 발송한다."""
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, self._fetch_sync, corp_code)
        except Exception as exc:
            logger.error("DART 공시 조회 실패: %s", exc)
            return []

        # 중요 공시 → HIGH 강제 알람
        if self._notifier:
            for item in items:
                try:
                    from info.ai_filter.claude_filter import FilterResult

                    result = FilterResult(
                        score="HIGH",
                        reason="DART 공시 — 중요도 HIGH 강제",
                        action="매수검토",
                    )
                    await self._notifier.send_news_alert(item, result)
                except Exception as exc:
                    logger.error("DART 알람 발송 실패: %s — %s", item.title, exc)

        return items

    def _fetch_sync(self, corp_code: str) -> list[NewsItem]:
        """OpenDartReader 동기 호출 (executor에서 실행)."""
        from opendartreader import OpenDartReader

        dart = OpenDartReader(self._api_key)

        today = datetime.now(tz=KST).strftime("%Y%m%d")
        week_ago = (datetime.now(tz=KST) - timedelta(days=7)).strftime("%Y%m%d")

        raw = dart.list(corp_code, bgn_de=week_ago, end_de=today)
        if raw is None or len(raw) == 0:
            return []

        items: list[NewsItem] = []
        for _, row in raw.iterrows():
            report_nm = str(row.get("report_nm", ""))
            if not any(rtype in report_nm for rtype in IMPORTANT_REPORT_TYPES):
                continue

            rcept_dt = str(row.get("rcept_dt", ""))
            try:
                pub_dt = datetime.strptime(rcept_dt, "%Y%m%d").replace(tzinfo=KST)
            except ValueError:
                pub_dt = datetime.now(tz=KST)

            rcp_no = str(row.get("rcept_no", ""))
            url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp_no}"

            items.append(
                NewsItem(
                    title=report_nm,
                    url=url,
                    source="DART",
                    published_kst=pub_dt,
                    raw_body=f"공시번호: {rcp_no}",
                )
            )

        return items
