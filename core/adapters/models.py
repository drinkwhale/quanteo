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
    """잔고 항목 (보유 종목 1개).

    qty는 float이다 — 해외주식(미국)은 Toss에서 소수점 단위 매매(fractional
    investing)를 지원해 정수가 아닐 수 있다.
    """

    symbol: str
    symbol_name: str
    qty: float
    avg_price: float
    current_price: float
    eval_amount: float
    profit_loss: float
    profit_loss_rate: float
    market: Market


@dataclass
class BalanceInfo:
    """잔고 조회 결과.

    total_*_krw는 KRW 통화 보유분만 합산한 값이다 — Toss holdings 응답이
    통화별로 분리해서 내려주기 때문에(원화 환산 없이는 단순 합산 불가),
    해외주식(USD) 평가금액은 포함하지 않는다. 계좌 전체 통화 혼합 평가액이
    필요하면 items를 종목별로 순회해 환율을 적용해야 한다.
    """

    items: list[BalanceItem]
    total_eval_amount_krw: float
    total_profit_loss_krw: float
    deposit: float
