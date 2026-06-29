"""
Control API 응답 스키마 (Pydantic).

모든 엔드포인트의 응답 타입을 정의한다.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------


class ApiResponse(BaseModel):
    """단순 성공/실패 응답 래퍼."""

    success: bool
    message: str = ""


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------


class BotStatus(BaseModel):
    """봇 상태 스냅샷."""

    running: bool
    halt_level: str  # "none" | "reduce" | "pause" | "kill"
    env: str         # "vps" | "prod"
    market: str      # "domestic" | "overseas"
    uptime_seconds: float
    started_at: datetime | None = None


# ---------------------------------------------------------------------------
# /positions
# ---------------------------------------------------------------------------


class PositionItem(BaseModel):
    """보유 포지션 1개."""

    symbol: str
    market: str
    env: str
    qty: int
    avg_price: Decimal
    book_value: Decimal
    opened_at: str
    updated_at: str


class PositionList(BaseModel):
    """포지션 목록 응답."""

    total: int
    items: list[PositionItem]


# ---------------------------------------------------------------------------
# /orders
# ---------------------------------------------------------------------------


class OrderItem(BaseModel):
    """주문 1건."""

    client_order_id: str
    broker_order_id: str | None
    symbol: str
    market: str
    env: str
    side: str   # "BUY" | "SELL"
    order_type: str  # "LIMIT" | "MARKET"
    qty: int
    price: Decimal
    status: str
    created_at: str
    updated_at: str


class OrderList(BaseModel):
    """주문 목록 응답."""

    total: int
    items: list[OrderItem]


# ---------------------------------------------------------------------------
# /orders 취소·정정 요청
# ---------------------------------------------------------------------------


class OrderCancelResponse(BaseModel):
    """주문 취소 응답."""

    success: bool
    order_id: str
    message: str = ""


class OrderModifyRequest(BaseModel):
    """주문 정정 요청 바디."""

    order_type: str  # LIMIT | MARKET
    quantity: int | None = None
    price: Decimal | None = None
    confirm_high_value: bool = False


class OrderModifyResponse(BaseModel):
    """주문 정정 응답."""

    success: bool
    order_id: str
    message: str = ""


# ---------------------------------------------------------------------------
# /trades
# ---------------------------------------------------------------------------


class FillItem(BaseModel):
    """체결 내역 1건."""

    symbol: str
    price: Decimal
    volume: int
    timestamp: datetime
    currency: str
    side: str | None = None  # "BUY" | "SELL"


class FillList(BaseModel):
    """체결 내역 목록 응답."""

    total: int
    items: list[FillItem]


# ---------------------------------------------------------------------------
# /market-status
# ---------------------------------------------------------------------------


class MarketDayStatus(BaseModel):
    """단일 시장 당일 개장 상태."""

    market: str  # KR | US
    is_open: bool
    today_date: str
    open_time: str | None = None
    close_time: str | None = None
    is_stale: bool = False  # True이면 캘린더 API 조회 실패 — 데이터 신뢰 불가


class MarketStatus(BaseModel):
    """국내·해외 마켓 개장 상태 응답."""

    markets: list[MarketDayStatus]


# ---------------------------------------------------------------------------
# /risk-metrics
# ---------------------------------------------------------------------------


class RiskMetrics(BaseModel):
    """Risk Manager 현재 지표 스냅샷."""

    halt_level: str
    daily_order_count: int
    buying_power: Decimal | None = None
    buying_power_currency: str | None = None


# ---------------------------------------------------------------------------
# /stream 메시지 (WebSocket)
# ---------------------------------------------------------------------------


class StreamMessage(BaseModel):
    """WebSocket 스트림 단일 메시지."""

    event_type: str
    payload: Any
    timestamp: datetime
    source: str = ""
