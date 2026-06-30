"""
국내 뉴스 RSS 수집기.

한국경제·매일경제·이데일리 RSS를 병렬 수집하고,
SQLite dedup으로 재시작 후 중복 알람을 방지한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import aiosqlite
import feedparser
import pytz

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

RSS_SOURCES = {
    "한국경제": "https://www.hankyung.com/feed/economy",
    "매일경제": "https://www.mk.co.kr/rss/30000001/",
    "이데일리": "https://www.edaily.co.kr/rss/edaily_news.xml",
}

FEED_TIMEOUT = 10  # seconds
DEDUP_TTL_HOURS = 24

_DEDUP_DB_PATH = Path.home() / ".quanteo" / "info_dedup.db"


# ---------------------------------------------------------------------------
# 데이터 타입
# ---------------------------------------------------------------------------


@dataclass
class NewsItem:
    """수집된 뉴스 아이템."""

    title: str
    url: str
    source: str
    published_kst: datetime
    raw_body: str = ""


# ---------------------------------------------------------------------------
# SQLite dedup 헬퍼
# ---------------------------------------------------------------------------


async def _init_dedup_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_urls (
                url TEXT PRIMARY KEY,
                seen_at TEXT NOT NULL
            )
            """
        )
        await db.commit()


async def _is_seen(url: str, db_path: Path) -> bool:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT 1 FROM seen_urls WHERE url = ?", (url,)
        ) as cursor:
            return await cursor.fetchone() is not None


async def _mark_seen(url: str, db_path: Path) -> None:
    now_iso = datetime.now(tz=pytz.UTC).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO seen_urls (url, seen_at) VALUES (?, ?)",
            (url, now_iso),
        )
        await db.commit()


async def _cleanup_old(db_path: Path) -> None:
    """TTL 초과 레코드 삭제."""
    from datetime import timedelta

    cutoff = (datetime.now(tz=pytz.UTC) - timedelta(hours=DEDUP_TTL_HOURS)).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM seen_urls WHERE seen_at < ?", (cutoff,))
        await db.commit()


# ---------------------------------------------------------------------------
# 피드 파싱
# ---------------------------------------------------------------------------


def _parse_entry(entry: feedparser.FeedParserDict, source: str) -> NewsItem | None:
    url = getattr(entry, "link", "") or ""
    title = getattr(entry, "title", "") or ""
    if not url or not title:
        return None

    # 발행 시각 → KST 변환
    published_kst: datetime
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        import calendar
        ts = calendar.timegm(entry.published_parsed)
        published_kst = datetime.fromtimestamp(ts, tz=pytz.UTC).astimezone(KST)
    else:
        published_kst = datetime.now(tz=KST)

    raw_body = getattr(entry, "summary", "") or ""

    return NewsItem(
        title=title,
        url=url,
        source=source,
        published_kst=published_kst,
        raw_body=raw_body,
    )


async def _fetch_one_feed(source: str, rss_url: str) -> list[NewsItem]:
    """단일 RSS 피드를 10초 타임아웃으로 수집한다."""
    try:
        loop = asyncio.get_running_loop()
        feed = await asyncio.wait_for(
            loop.run_in_executor(None, feedparser.parse, rss_url),
            timeout=FEED_TIMEOUT,
        )
        items = []
        for entry in feed.entries:
            item = _parse_entry(entry, source)
            if item:
                items.append(item)
        return items
    except TimeoutError:
        logger.warning("RSS 피드 타임아웃: %s (%s)", source, rss_url)
        return []
    except Exception as exc:
        logger.error("RSS 피드 수집 실패: %s (%s) — %s", source, rss_url, exc)
        return []


# ---------------------------------------------------------------------------
# 수집기 메인
# ---------------------------------------------------------------------------


class RssCollector:
    """국내 뉴스 RSS 병렬 수집기."""

    def __init__(
        self,
        sources: dict[str, str] | None = None,
        dedup_db_path: Path | None = None,
        claude_filter=None,
        info_notifier=None,
    ) -> None:
        self._sources = sources or RSS_SOURCES
        self._dedup_db = dedup_db_path or _DEDUP_DB_PATH
        self._filter = claude_filter
        self._notifier = info_notifier

    async def fetch(self) -> list[NewsItem]:
        """모든 RSS 피드를 병렬 수집하고 dedup 후 반환한다."""
        await _init_dedup_db(self._dedup_db)
        await _cleanup_old(self._dedup_db)

        tasks = [_fetch_one_feed(src, url) for src, url in self._sources.items()]
        results = await asyncio.gather(*tasks)
        all_items = [item for items in results for item in items]

        new_items: list[NewsItem] = []
        for item in all_items:
            if not await _is_seen(item.url, self._dedup_db):
                await _mark_seen(item.url, self._dedup_db)
                new_items.append(item)

        # Claude 필터 + 알람 발송
        if self._filter and self._notifier:
            for item in new_items:
                try:
                    result = await self._filter.classify(item.title, item.raw_body)
                    if result.score == "HIGH":
                        await self._notifier.send_news_alert(item, result)
                except Exception as exc:
                    logger.error("뉴스 필터/알람 실패: %s — %s", item.title, exc)

        return new_items
