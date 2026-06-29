"""
브로커 공통 도메인 타입.

PriceInfo / BalanceInfo / BalanceItem — BrokerAdapter Protocol 반환 타입.
KIS·Toss 어댑터가 모두 이 타입을 사용해 상위 레이어와 호환된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.config.settings import Market


@dataclass
class PriceInfo:
    """현재가 조회 결과."""

    symbol: str
    current_price: float
    open_price: float
    high_price: float
    low_price: float
    volume: int
    market: Market
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class BalanceItem:
    """잔고 항목 (보유 종목 1개)."""

    symbol: str
    symbol_name: str
    qty: int
    avg_price: float
    current_price: float
    eval_amount: float
    profit_loss: float
    profit_loss_rate: float


@dataclass
class BalanceInfo:
    """잔고 조회 결과."""

    items: list[BalanceItem]
    total_eval_amount: float
    total_profit_loss: float
    deposit: float
