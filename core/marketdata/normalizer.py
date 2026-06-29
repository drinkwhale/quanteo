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
from typing import Literal

from core.adapters.kis.rest import BalanceInfo, BalanceItem
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
