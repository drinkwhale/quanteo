"""
내부 표준 시세 모델.

KIS 원시 데이터를 변환하는 최종 타입으로, 전략·리스크 모듈이 이 타입만 바라본다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class Tick:
    """실시간 체결 틱 (WebSocket 체결가 수신 시)."""

    symbol: str
    price: float
    volume: int
    timestamp: datetime
    market: Literal["domestic", "overseas"]


@dataclass(frozen=True)
class Quote:
    """실시간 호가 (WebSocket 호가 수신 시, 국내 전용)."""

    symbol: str
    bid_price: float
    ask_price: float
    bid_qty: int
    ask_qty: int
    timestamp: datetime


@dataclass(frozen=True)
class Candle:
    """OHLCV 캔들 (REST 현재가·과거 조회 시)."""

    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime
    market: Literal["domestic", "overseas"]
    interval: str = "1d"  # 1m | 5m | 1d 등
