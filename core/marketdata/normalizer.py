"""
시세 데이터 정규화 모듈 — Toss 전용.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from core.adapters.toss.models import Fill
from core.marketdata.models import Candle, Tick

logger = logging.getLogger(__name__)

__all__ = [
    "normalize_toss_price",
    "normalize_toss_trade",
    "normalize_toss_candle",
]


def normalize_toss_price(symbol: str, result: dict) -> Tick:
    """Toss /api/v1/prices result 항목을 Tick으로 변환한다."""
    market_country: str = result.get("marketCountry", "KR")
    market: Literal["domestic", "overseas"] = "domestic" if market_country == "KR" else "overseas"

    raw_ts = result.get("timestamp")
    if raw_ts:
        try:
            if isinstance(raw_ts, (int, float)):
                timestamp = datetime.fromtimestamp(raw_ts / 1000, tz=UTC)
            else:
                timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except Exception:
            logger.warning("normalize_toss_price: 타임스탬프 파싱 실패 (symbol=%s, raw=%r) — 현재 시각으로 대체", symbol, raw_ts)
            timestamp = datetime.now(UTC)
    else:
        timestamp = datetime.now(UTC)

    return Tick(
        symbol=symbol,
        price=float(result.get("lastPrice", 0)),
        volume=int(result.get("volume", 0)),
        timestamp=timestamp,
        market=market,
    )


def normalize_toss_trade(symbol: str, result: dict) -> Fill:
    """Toss /api/v1/trades result 항목을 Fill로 변환한다."""
    raw_ts = result.get("timestamp")
    if raw_ts:
        try:
            if isinstance(raw_ts, (int, float)):
                timestamp = datetime.fromtimestamp(raw_ts / 1000, tz=UTC)
            else:
                timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except Exception:
            logger.warning("normalize_toss_trade: 타임스탬프 파싱 실패 (symbol=%s, raw=%r) — 현재 시각으로 대체", symbol, raw_ts)
            timestamp = datetime.now(UTC)
    else:
        timestamp = datetime.now(UTC)

    return Fill(
        symbol=result.get("symbol", symbol),
        price=Decimal(str(result.get("price", "0"))),
        volume=int(Decimal(str(result.get("volume", "0")))),
        timestamp=timestamp,
        currency=result.get("currency", "KRW"),
        side=result.get("side"),
    )


def normalize_toss_candle(symbol: str, result: dict, interval: str = "1d") -> Candle:
    """Toss /api/v1/candles result 항목을 Candle로 변환한다."""
    raw_ts = result.get("timestamp")
    if raw_ts:
        try:
            if isinstance(raw_ts, (int, float)):
                timestamp = datetime.fromtimestamp(raw_ts / 1000, tz=UTC)
            else:
                timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except Exception:
            logger.warning("normalize_toss_candle: 타임스탬프 파싱 실패 (symbol=%s, raw=%r) — 현재 시각으로 대체", symbol, raw_ts)
            timestamp = datetime.now(UTC)
    else:
        timestamp = datetime.now(UTC)

    currency = result.get("currency", "KRW")
    market: Literal["domestic", "overseas"] = "domestic" if currency == "KRW" else "overseas"

    return Candle(
        symbol=symbol,
        open=float(result.get("openPrice", 0)),
        high=float(result.get("highPrice", 0)),
        low=float(result.get("lowPrice", 0)),
        close=float(result.get("closePrice", 0)),
        volume=int(float(result.get("volume", 0))),
        timestamp=timestamp,
        market=market,
        interval=interval,
    )
