"""
주요 지수·환율(코스피·코스닥·나스닥·달러·엔화) 시세 조회.

Toss Open API는 개별 종목 시세만 제공하고 지수·해외 환율은 조회할 수 없다
(specs/tossinvest/ 어디에도 그런 엔드포인트가 없음 — USD/KRW만 자체 제공하지만
이 모듈은 지수와 같은 화면에 한 번에 보여주기 위해 통일된 소스를 쓴다). 이
모듈은 프로젝트가 이미 환율 조회(info/fx/rate_monitor.py)에 쓰는 yfinance로
가져온다 — Toss 인증·계좌와 무관하게 항상 동작하는 순수 외부 조회다.

yfinance는 동기 라이브러리라 run_in_executor로 스레드에서 돌린다 — rate_monitor.py와
동일 패턴. 비공식 소스라 스키마가 예고 없이 바뀔 수 있어, 실패한 항목만 조용히
빠지고(다른 항목은 정상 반환) 전체가 죽지는 않는다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 30.0

# yfinance 티커 매핑. 화면에 보여줄 항목을 늘리려면 여기만 추가.
# multiplier: 엔화처럼 "100엔당" 단위로 관례상 표시하는 경우에만 1이 아님.
INDEX_TICKERS: dict[str, dict[str, object]] = {
    "^KS11": {"key": "kospi", "label": "코스피", "currency": "KRW"},
    "^KQ11": {"key": "kosdaq", "label": "코스닥", "currency": "KRW"},
    "^IXIC": {"key": "nasdaq", "label": "나스닥", "currency": "USD"},
    "USDKRW=X": {"key": "usdkrw", "label": "달러/원", "currency": "KRW"},
    "JPYKRW=X": {
        "key": "jpykrw",
        "label": "엔/원(100엔)",
        "currency": "KRW",
        "multiplier": 100,
    },
}


@dataclass(frozen=True)
class IndexQuote:
    """지수 시세 1건.

    change_rate는 비율(fraction, 예: -0.0045)이다 — 대시보드 전체 컨벤션과
    맞춰 표시 시점에 한 번만 *100 한다 (lib/format.ts의 fmtPnl과 동일 규칙).
    """

    key: str
    label: str
    price: float
    change: float
    change_rate: float
    currency: str


_cache: tuple[float, list[IndexQuote]] | None = None


def _fetch_sync(tickers: dict[str, dict[str, object]]) -> list[IndexQuote]:
    """yfinance 동기 조회 — info/fx/rate_monitor.py의 _fetch_sync와 동일 패턴."""
    import yfinance as yf

    quotes: list[IndexQuote] = []
    for symbol, meta in tickers.items():
        try:
            info = yf.Ticker(symbol).fast_info
            multiplier = float(meta.get("multiplier", 1))
            price = float(info["lastPrice"]) * multiplier
            prev_close = float(info["previousClose"]) * multiplier
            change = price - prev_close
            change_rate = change / prev_close if prev_close else 0.0
            quotes.append(
                IndexQuote(
                    key=str(meta["key"]),
                    label=str(meta["label"]),
                    price=price,
                    change=change,
                    change_rate=change_rate,
                    currency=str(meta["currency"]),
                )
            )
        except Exception:
            logger.warning("시세 조회 실패 — 이 항목만 제외하고 계속: %s", symbol, exc_info=True)
    return quotes


async def get_index_quotes(
    tickers: dict[str, dict[str, object]] | None = None,
    *,
    use_cache: bool = True,
) -> list[IndexQuote]:
    """주요 지수 시세를 조회한다.

    30초 TTL 인메모리 캐시를 쓴다 — 대시보드가 짧은 주기로 폴링해도 외부 API를
    매번 때리지 않는다. 지수는 실시간 트레이딩에 쓰는 게 아니라 참고용이라
    이 정도 지연은 문제되지 않는다.
    """
    global _cache

    tickers = tickers or INDEX_TICKERS
    now = time.monotonic()
    if use_cache and _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1]

    loop = asyncio.get_running_loop()
    quotes = await loop.run_in_executor(None, _fetch_sync, tickers)

    if quotes:
        _cache = (now, quotes)
    return quotes
