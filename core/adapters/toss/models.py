"""
Toss증권 어댑터 전용 도메인 타입.

KIS 어댑터와 달리 Toss API는 REST JSON 전용이므로
별도 데이터 모델을 정의해 타입 안전성을 확보한다.
모든 dataclass는 frozen=True로 불변성을 보장한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal


# ---------------------------------------------------------------------------
# T049 — 매수가능금액 · 판매가능수량 · 수수료
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuyingPowerInfo:
    """매수가능금액 정보.

    Args:
        currency: 통화 코드 (KRW, USD 등).
        cash_buying_power: 현금 기반 매수 가능 금액 (미수 미발생 기준).
    """

    currency: str
    cash_buying_power: Decimal


@dataclass(frozen=True)
class Commission:
    """수수료 정책.

    Args:
        market_country: 시장 국가 (KR, US 등).
        commission_rate: 수수료율 (%). 예: 0.015 → 0.015%.
        start_date: 수수료 적용 시작일 (None이면 무제한).
        end_date: 수수료 적용 종료일 (None이면 무제한).
    """

    market_country: str
    commission_rate: Decimal
    start_date: str | None = None
    end_date: str | None = None


# ---------------------------------------------------------------------------
# T050 — 주문 관리 (목록·단건·취소·정정)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderExecution:
    """주문 체결 정보 (Order.execution 내부 필드)."""

    # float: 해외주식(미국)은 소수점 단위 매매(fractional investing)를 지원해
    # 체결 수량이 정수가 아닐 수 있다(예: "0.000151"). int로 두면 Toss가
    # 이런 값을 내려줄 때 _parse_toss_order()에서 파싱 자체가 실패한다.
    filled_quantity: float
    avg_fill_price: Decimal | None
    fees: Decimal | None


@dataclass(frozen=True)
class TossOrder:
    """Toss 주문 상세 정보.

    Args:
        order_id: Toss 주문 식별자.
        client_order_id: 클라이언트 주문 식별자 (멱등키).
        symbol: 종목 심볼.
        side: 매수/매도 (BUY, SELL).
        order_type: 주문 유형 (LIMIT, MARKET).
        status: 주문 상태 (OrderStatus enum 값).
        quantity: 주문 수량.
        price: 지정가 (시장가이면 None).
        currency: 통화 코드.
        ordered_at: 주문 시각.
        execution: 체결 정보.
    """

    order_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    order_type: Literal["LIMIT", "MARKET"]
    status: str
    quantity: float  # 해외 fractional investing 지원 — filled_quantity와 동일한 이유
    currency: str
    ordered_at: datetime
    execution: OrderExecution
    client_order_id: str | None = None
    price: Decimal | None = None


@dataclass(frozen=True)
class OrderOperationResponse:
    """주문 취소·정정 응답.

    Args:
        order_id: 새로 발급된 주문 식별자 (원주문 ID와 다름).
    """

    order_id: str


# ---------------------------------------------------------------------------
# T051 — 체결 내역
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fill:
    """체결 내역 항목.

    Args:
        symbol: 종목 심볼.
        price: 체결가.
        volume: 체결 수량.
        timestamp: 체결 시각 (UTC).
        currency: 통화 코드.
        side: 매수/매도 (BUY, SELL). API에서 미제공 시 None.
    """

    symbol: str
    price: Decimal
    volume: int
    timestamp: datetime
    currency: str
    side: Literal["BUY", "SELL"] | None = None


# ---------------------------------------------------------------------------
# T052 — 마켓 정보 & 캘린더
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceLimits:
    """상하한가 정보.

    Args:
        symbol: 종목 심볼.
        upper_limit_price: 상한가 (가격제한 없는 시장은 None).
        lower_limit_price: 하한가 (가격제한 없는 시장은 None).
        timestamp: 데이터 시각.
        currency: 통화 코드.
    """

    symbol: str
    upper_limit_price: Decimal | None
    lower_limit_price: Decimal | None
    timestamp: datetime
    currency: str


@dataclass(frozen=True)
class MarketSession:
    """개장 세션 시간."""

    open_time: str
    close_time: str


@dataclass(frozen=True)
class KrMarketDay:
    """국내 시장 영업일 정보."""

    date: str
    is_open: bool
    open_time: str | None = None
    close_time: str | None = None


@dataclass(frozen=True)
class KrMarketCalendar:
    """국내 마켓 캘린더.

    Args:
        today: 오늘 영업일 정보.
        previous_business_day: 이전 영업일.
        next_business_day: 다음 영업일.
    """

    today: KrMarketDay
    previous_business_day: KrMarketDay
    next_business_day: KrMarketDay


@dataclass(frozen=True)
class UsMarketDay:
    """미국 시장 영업일 정보."""

    date: str
    is_open: bool
    regular_open: str | None = None
    regular_close: str | None = None


@dataclass(frozen=True)
class UsMarketCalendar:
    """미국 마켓 캘린더.

    Args:
        today: 오늘 영업일 정보.
        previous_business_day: 이전 영업일.
        next_business_day: 다음 영업일.
    """

    today: UsMarketDay
    previous_business_day: UsMarketDay
    next_business_day: UsMarketDay


# ---------------------------------------------------------------------------
# T053 — 종목 정보 & 유의사항
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StockInfo:
    """종목 기본 정보.

    Args:
        symbol: 종목 심볼.
        name: 종목명 (한글).
        english_name: 영문 종목명.
        market: 상장 시장 (KOSPI, KOSDAQ, NYSE 등).
        status: 종목 상태 (NORMAL, HALTED, DELISTED 등).
        currency: 통화 코드.
        isin_code: 국제증권식별번호.
        is_common_share: 보통주 여부.
    """

    symbol: str
    name: str
    english_name: str
    market: str
    status: str
    currency: str
    isin_code: str
    is_common_share: bool


@dataclass(frozen=True)
class StockWarning:
    """종목 유의사항.

    Args:
        warning_type: 유의사항 유형.
        start_date: 지정 시작일 (None이면 즉시 적용).
        end_date: 지정 종료일 (None이면 지속).
    """

    warning_type: str
    start_date: str | None = None
    end_date: str | None = None


# ---------------------------------------------------------------------------
# T054 — 환율
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExchangeRate:
    """환율 정보.

    Args:
        base_currency: 기준 통화 (예: USD).
        quote_currency: 표시 통화 (예: KRW).
        rate: 매수 환율 (1 baseCurrency = ? quoteCurrency).
        mid_rate: 매매기준율.
        rate_change_type: 환율 변동 방향 (RISE, FALL, UNCHANGED 등).
        valid_from: 유효 시작 시각.
        valid_until: 유효 종료 시각.
    """

    base_currency: str
    quote_currency: str
    rate: Decimal
    mid_rate: Decimal
    rate_change_type: str
    valid_from: datetime
    valid_until: datetime


# ---------------------------------------------------------------------------
# T055 — 캔들 (Toss 전용 래퍼)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TossCandle:
    """Toss API 원시 캔들 데이터.

    core.marketdata.models.Candle과 달리 Toss 전용 필드(currency)를 포함한다.
    정규화 후 core.marketdata.models.Candle로 변환한다.
    """

    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    currency: str
