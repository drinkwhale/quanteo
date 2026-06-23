"""
Control API 응답 스키마 (Pydantic).

모든 엔드포인트의 응답 타입을 정의한다.
"""

from __future__ import annotations

from datetime import datetime
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
    avg_price: float
    book_value: float
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
    kis_order_id: str | None
    symbol: str
    market: str
    env: str
    side: str
    order_type: str
    qty: int
    price: float
    status: str
    created_at: str
    updated_at: str


class OrderList(BaseModel):
    """주문 목록 응답."""

    total: int
    items: list[OrderItem]


# ---------------------------------------------------------------------------
# /stream 메시지 (WebSocket)
# ---------------------------------------------------------------------------


class StreamMessage(BaseModel):
    """WebSocket 스트림 단일 메시지."""

    event_type: str
    payload: Any
    timestamp: datetime
    source: str = ""
