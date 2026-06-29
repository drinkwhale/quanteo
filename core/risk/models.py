"""
Risk Manager 공통 타입 정의.

Signal → Order 변환 과정에서 사용하는 도메인 모델.
모든 dataclass는 frozen=True로 불변성을 보장한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from core.config.settings import Market
from core.strategy.base import Signal

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# 열거형
# ---------------------------------------------------------------------------


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class HaltLevel(StrEnum):
    """단계적 킬스위치 수준."""

    NONE = "none"      # 정상 운영
    REDUCE = "reduce"  # 신규 포지션 50% 축소 (변동성 급등)
    PAUSE = "pause"    # 신규 진입 중단, 기존 포지션 유지 (일일 손실 임박)
    KILL = "kill"      # 모든 신규 주문 차단, 손절만 허용 (한도 초과)


# ---------------------------------------------------------------------------
# 포지션 & 포트폴리오
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Position:
    """보유 포지션 스냅샷.

    Args:
        symbol: 종목 코드.
        market: 시장 구분.
        qty: 보유 수량.
        avg_price: 평균 매입 단가.
    """

    symbol: str
    market: Market
    qty: int
    avg_price: float

    @property
    def book_value(self) -> float:
        """포지션 장부가 (수량 × 평균단가). 현재 시세 기반 시장가치가 아님."""
        return self.qty * self.avg_price

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """미실현 손익률 (current_price 기준)."""
        if self.avg_price <= 0:
            return 0.0
        return (current_price - self.avg_price) / self.avg_price


@dataclass(frozen=True)
class Portfolio:
    """현재 포트폴리오 스냅샷.

    Args:
        positions: symbol → Position 매핑.
        deposit: 현금 예수금 (원).
    """

    positions: dict[str, Position] = field(default_factory=dict)
    deposit: float = 0.0

    @property
    def total_exposure(self) -> float:
        """총 주식 노출 금액 — 장부가 기준 (원)."""
        return sum(p.book_value for p in self.positions.values())

    @property
    def total_assets(self) -> float:
        """총 자산 = 예수금 + 주식 평가액."""
        return self.deposit + self.total_exposure


# ---------------------------------------------------------------------------
# 주문 & 거부
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Order:
    """Risk Manager가 생성한 주문.

    Args:
        client_order_id: 클라이언트 측 주문 ID (UUID4, 멱등성 보장).
        symbol: 종목 코드.
        market: 시장 구분.
        side: 매수/매도.
        order_type: 시장가/지정가.
        qty: 주문 수량.
        price: 주문 가격 (시장가이면 0.0).
        source_signal: 이 주문을 유발한 원본 시그널.
        created_at: 주문 생성 시각 (UTC).
    """

    symbol: str
    market: Market
    side: OrderSide
    order_type: OrderType
    qty: int
    price: float
    source_signal: Signal
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.qty < 1:
            raise ValueError(f"주문 수량은 1 이상이어야 합니다: {self.qty}")
        if self.order_type == OrderType.LIMIT and self.price <= 0:
            raise ValueError(f"지정가 주문은 양수 가격이 필요합니다: {self.price}")


@dataclass(frozen=True)
class Rejection:
    """Risk Manager가 시그널을 거부할 때 반환하는 객체.

    Args:
        signal: 거부된 원본 시그널.
        reason: 거부 사유 (로그·알림용).
    """

    signal: Signal
    reason: str
