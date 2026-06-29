"""
시세 데이터 정규화 모듈 — 통합 진입점.

브로커별 정규화 함수를 하나의 모듈로 통합한다.
  - KIS 파이프 포맷: normalizer_kis.py (기존 코드 보존)
  - Toss JSON 포맷: 이 파일에 정의

하위 호환을 위해 KIS 함수를 그대로 re-export한다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from core.adapters.kis.rest import BalanceInfo, BalanceItem
from core.adapters.toss.models import Fill, TossCandle
from core.marketdata.models import Candle, Tick

# KIS 정규화 함수 re-export (기존 테스트·코드 무수정 유지)
from core.marketdata.normalizer_kis import (
    normalize_domestic_quote,
    normalize_domestic_tick,
    normalize_overseas_tick,
    normalize_price_to_candle,
)

logger = logging.getLogger(__name__)

__all__ = [
    # KIS (하위 호환)
    "normalize_domestic_tick",
    "normalize_domestic_quote",
    "normalize_overseas_tick",
    "normalize_price_to_candle",
    # Toss
    "normalize_toss_price",
    "normalize_toss_holdings",
    "normalize_toss_trade",
    "normalize_toss_candle",
]


# ---------------------------------------------------------------------------
# Toss 정규화 함수
# ---------------------------------------------------------------------------


def normalize_toss_price(symbol: str, result: dict) -> Tick:
    """Toss /api/v1/prices result 항목을 Tick으로 변환한다.

    Args:
        symbol: 종목 코드.
        result: Toss API result 배열의 첫 번째 항목.

    Returns:
        Tick 인스턴스.
    """
    market_country: str = result.get("marketCountry", "KR")
    market: Literal["domestic", "overseas"] = "domestic" if market_country == "KR" else "overseas"

    raw_ts = result.get("timestamp")
    if raw_ts:
        try:
            # Toss는 ISO 8601 문자열 또는 epoch ms를 반환할 수 있다
            if isinstance(raw_ts, (int, float)):
                timestamp = datetime.fromtimestamp(raw_ts / 1000, tz=UTC)
            else:
                timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except Exception:
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
    """Toss /api/v1/trades result 항목을 Fill로 변환한다.

    Args:
        symbol: 체결 종목 심볼 (trades API가 symbol 필드를 반환하지 않을 때 대체).
        result: Toss API result 배열의 단일 항목.

    Returns:
        Fill 인스턴스.
    """
    from decimal import Decimal

    raw_ts = result.get("timestamp")
    if raw_ts:
        try:
            if isinstance(raw_ts, (int, float)):
                timestamp = datetime.fromtimestamp(raw_ts / 1000, tz=UTC)
            else:
                timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except Exception:
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
    """Toss /api/v1/candles result 항목을 Candle로 변환한다.

    Args:
        symbol: 종목 심볼.
        result: Toss API Candle 객체.
        interval: 봉 단위 문자열 ("1m", "1d").

    Returns:
        Candle 인스턴스 (core.marketdata.models.Candle).
    """
    raw_ts = result.get("timestamp")
    if raw_ts:
        try:
            if isinstance(raw_ts, (int, float)):
                timestamp = datetime.fromtimestamp(raw_ts / 1000, tz=UTC)
            else:
                timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except Exception:
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


def normalize_toss_holdings(result: dict) -> BalanceInfo:
    """Toss /api/v1/holdings result를 BalanceInfo로 변환한다.

    Args:
        result: Toss API result 객체 (items + summary 포함).

    Returns:
        BalanceInfo 인스턴스.
    """
    items: list[BalanceItem] = []
    for row in result.get("items", []):
        qty = int(row.get("quantity", 0))
        if qty == 0:
            continue
        items.append(
            BalanceItem(
                symbol=row.get("symbol", ""),
                symbol_name=row.get("name", ""),
                qty=qty,
                avg_price=float(row.get("averagePurchasePrice", 0)),
                current_price=float(row.get("currentPrice", 0)),
                eval_amount=float(row.get("marketValue", 0)),
                profit_loss=float(row.get("unrealizedGainLoss", 0)),
                profit_loss_rate=float(row.get("unrealizedGainLossRate", 0)),
            )
        )

    summary = result.get("summary", {})
    return BalanceInfo(
        items=items,
        total_eval_amount=float(summary.get("totalMarketValue", 0)),
        total_profit_loss=float(summary.get("totalUnrealizedGainLoss", 0)),
        deposit=float(summary.get("cashBalance", 0)),
    )
