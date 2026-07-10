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
    env: str  # "prod" (Toss는 항상 실전, 모의투자 환경 없음)
    market: str  # "domestic" | "overseas"
    uptime_seconds: float
    started_at: datetime | None = None


# ---------------------------------------------------------------------------
# /positions
# ---------------------------------------------------------------------------


class PositionItem(BaseModel):
    """보유 포지션 1개.

    qty는 Decimal — 해외주식(미국)은 Toss에서 소수점 단위 매매(fractional
    investing)를 지원해 정수가 아닐 수 있다. OrderItem.qty도 OrderHistorySyncFeed가
    Toss 앱에서 직접 낸 해외 fractional 주문까지 반영하면서 동일한 이유로
    float로 바뀌었다 — 더 이상 "항상 정수"가 아니다.
    """

    symbol: str
    market: str
    env: str
    qty: Decimal
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
    side: str  # "BUY" | "SELL"
    order_type: str  # "LIMIT" | "MARKET"
    qty: float  # 해외주식 fractional investing 지원 — 정수 아닐 수 있음
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
# /stock-names
# ---------------------------------------------------------------------------


class StockNameItem(BaseModel):
    """종목 심볼 → 종목명 매핑 단일 항목."""

    symbol: str
    name: str
    market: str


class StockNameList(BaseModel):
    """종목명 조회 응답. 대시보드가 심볼 코드 대신 종목명을 표시하는 데 쓴다."""

    items: list[StockNameItem]


# ---------------------------------------------------------------------------
# /indices — 주요 지수 시세 (Toss API 미지원, 외부 소스 조회)
# ---------------------------------------------------------------------------


class IndexQuoteItem(BaseModel):
    """지수 시세 1건. change_rate는 비율(fraction) — 표시 시 프론트에서 *100."""

    key: str
    label: str
    price: float
    change: float
    change_rate: float
    currency: str


class IndexQuoteResponse(BaseModel):
    """주요 지수 시세 응답."""

    items: list[IndexQuoteItem]


# ---------------------------------------------------------------------------
# /balance — 실계좌 평가금액·평가손익 (계좌 요약 카드용)
# ---------------------------------------------------------------------------


class DayChange(BaseModel):
    """전일 종가 대비 당일 등락. amount/rate는 항상 함께 존재하거나 함께
    없다(KIS 시세 조회 실패·미설정 시 둘 다 없음) — 그 불변식을 표현하려고
    독립된 nullable 필드 두 개 대신 하나의 nullable 하위 모델로 감쌌다.
    rate는 비율(fraction) — 표시 시 프론트에서 *100.
    """

    amount: Decimal
    rate: float


class BalanceItem(BaseModel):
    """보유 종목 1개의 평가 정보. Toss holdings 응답을 그대로 반영한다.

    profit_loss/profit_loss_rate는 매입가 대비 누적 손익(평가금액 기준)이고,
    day_change는 전일 종가 대비 당일 등락(현재가 기준)이다 — 두 축이 서로
    다른데 대시보드가 이를 혼동해 보여주던 버그를 고치며 추가한 필드.
    day_change의 전일 종가는 KIS 시세 조회로 얻는다(Toss 캔들 데이터가
    실측으로 부정확함이 확인돼 대체) — kis_client 미설정·조회 실패 시
    null일 수 있다(가짜 값 대신 결측 표시).
    """

    symbol: str
    symbol_name: str
    qty: Decimal
    avg_price: Decimal
    current_price: Decimal
    eval_amount: Decimal
    profit_loss: Decimal
    profit_loss_rate: float
    day_change: DayChange | None = None
    market: str  # "domestic" | "overseas"


class BalanceInfo(BaseModel):
    """계좌 전체 잔고 응답.

    total_eval_amount_krw/total_profit_loss_krw는 KRW 보유분만 합산한 값이다
    (Toss holdings 응답이 통화별로 분리되어 있어 원화 환산 없이는 USD 보유분과
    단순 합산할 수 없다). deposit(예수금)은 holdings 응답에 없어 항상 0 —
    별도 계좌 잔고 API 연동 전까지는 화면에서 노출하지 않는다.
    """

    items: list[BalanceItem]
    total_eval_amount_krw: Decimal
    total_profit_loss_krw: Decimal
    deposit: Decimal


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
