"""
해외 뉴스 수집기.

Finnhub REST API와 Yahoo Finance RSS로 해외 기업 뉴스를 수집한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import feedparser
import httpx
import pytz

from info.news.rss_collector import NewsItem

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

FINNHUB_BASE = "https://finnhub.io/api/v1/company-news"
YAHOO_RSS_SOURCES = {
    "Yahoo Finance": "https://finance.yahoo.com/news/rss/",
}

DEFAULT_SYMBOLS = ["NVDA", "MU", "TSM", "AMD", "ASML"]

_MAX_RETRIES = 3
_SEMAPHORE_LIMIT = 10  # 60 req/min 준수 (6 req/s 목표)


class FinnhubCollector:
    """Finnhub REST API 해외 뉴스 수집기."""

    def __init__(
        self,
        api_key: str,
        symbols: list[str] | None = None,
        claude_filter=None,
        info_notifier=None,
    ) -> None:
        self._api_key = api_key
        self._symbols = symbols or DEFAULT_SYMBOLS
        self._filter = claude_filter
        self._notifier = info_notifier
        self._sem = asyncio.Semaphore(_SEMAPHORE_LIMIT)

    async def fetch(self, symbols: list[str] | None = None) -> list[NewsItem]:
        """티커별 뉴스를 병렬 수집한다."""
        targets = symbols or self._symbols
        tasks = [self._fetch_symbol(sym) for sym in targets]
        results = await asyncio.gather(*tasks)
        items = [item for items in results for item in items]

        if self._filter and self._notifier:
            for item in items:
                try:
                    result = await self._filter.classify(item.title, item.raw_body)
                    if result.score == "HIGH":
                        await self._notifier.send_news_alert(item, result)
                except Exception as exc:
                    logger.error("해외 뉴스 필터/알람 실패: %s — %s", item.title, exc)

        return items

    async def _fetch_symbol(self, symbol: str) -> list[NewsItem]:
        """단일 심볼 뉴스 수집 (지수 백오프 재시도)."""
        today = datetime.now(tz=pytz.UTC)
        week_ago = today - timedelta(days=7)
        params = {
            "symbol": symbol,
            "from": week_ago.strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "token": self._api_key,
        }

        delay = 1.0
        for attempt in range(_MAX_RETRIES):
            async with self._sem:
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.get(FINNHUB_BASE, params=params)

                    if resp.status_code == 429:
                        if attempt < _MAX_RETRIES - 1:
                            logger.warning(
                                "Finnhub 429 — %s 심볼, %.0fs 후 재시도 (%d/%d)",
                                symbol, delay, attempt + 1, _MAX_RETRIES,
                            )
                            await asyncio.sleep(delay)
                            delay *= 2
                            continue
                        else:
                            logger.warning("Finnhub 429 재시도 소진 — %s 스킵", symbol)
                            return []

                    if resp.status_code >= 500:
                        logger.warning("Finnhub 5xx — %s 스킵", symbol)
                        return []

                    resp.raise_for_status()
                    data = resp.json()

                    if not data:  # 빈 배열
                        return []

                    return [self._parse_item(entry, symbol) for entry in data if entry]

                except httpx.TimeoutException:
                    logger.warning("Finnhub 타임아웃 — %s", symbol)
                    return []
                except Exception as exc:
                    logger.error("Finnhub 수집 실패 — %s: %s", symbol, exc)
                    return []

        return []

    def _parse_item(self, entry: dict, symbol: str) -> NewsItem:
        ts = entry.get("datetime", 0)
        published = datetime.fromtimestamp(ts, tz=pytz.UTC).astimezone(KST) if ts else datetime.now(tz=KST)
        return NewsItem(
            title=entry.get("headline", ""),
            url=entry.get("url", ""),
            source=f"Finnhub/{symbol}",
            published_kst=published,
            raw_body=entry.get("summary", ""),
        )


class YahooRssCollector:
    """Yahoo Finance RSS 수집기."""

    def __init__(
        self,
        claude_filter=None,
        info_notifier=None,
    ) -> None:
        self._filter = claude_filter
        self._notifier = info_notifier

    async def fetch(self) -> list[NewsItem]:
        loop = asyncio.get_event_loop()
        items: list[NewsItem] = []

        for source, url in YAHOO_RSS_SOURCES.items():
            try:
                feed = await asyncio.wait_for(
                    loop.run_in_executor(None, feedparser.parse, url),
                    timeout=10,
                )
                for entry in feed.entries:
                    item = self._parse_entry(entry, source)
                    if item:
                        items.append(item)
            except TimeoutError:
                logger.warning("Yahoo RSS 타임아웃: %s", source)
            except Exception as exc:
                logger.error("Yahoo RSS 수집 실패: %s — %s", source, exc)

        if self._filter and self._notifier:
            for item in items:
                try:
                    result = await self._filter.classify(item.title, item.raw_body)
                    if result.score == "HIGH":
                        await self._notifier.send_news_alert(item, result)
                except Exception as exc:
                    logger.error("Yahoo 뉴스 필터/알람 실패: %s — %s", item.title, exc)

        return items

    def _parse_entry(self, entry, source: str) -> NewsItem | None:
        url = getattr(entry, "link", "") or ""
        title = getattr(entry, "title", "") or ""
        if not url or not title:
            return None

        import calendar
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            ts = calendar.timegm(entry.published_parsed)
            published = datetime.fromtimestamp(ts, tz=pytz.UTC).astimezone(KST)
        else:
            published = datetime.now(tz=KST)

        return NewsItem(
            title=title,
            url=url,
            source=source,
            published_kst=published,
            raw_body=getattr(entry, "summary", "") or "",
        )
