"""
브로커 어댑터 추상화 레이어.

BrokerAdapter Protocol을 통해 다양한 브로커 어댑터를 교체 가능하게 한다. 현재: Toss증권.
전략·리스크·실행 레이어는 이 Protocol만 바라보면 된다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.adapters.models import BalanceInfo, PriceInfo
    from core.execution.executor import OrderAck
    from core.risk.models import Order


# ---------------------------------------------------------------------------
# 브로커 REST 추상화
# ---------------------------------------------------------------------------


@runtime_checkable
class BrokerAdapter(Protocol):
    """브로커 REST API 공통 인터페이스.

    TossRestClient 및 향후 다른 브로커 어댑터가 이 Protocol을 만족해야 한다.
    """

    async def get_price(self, symbol: str) -> PriceInfo:
        """현재가를 조회한다."""
        ...

    async def get_balance(self, symbol: str | None = None) -> BalanceInfo:
        """계좌 잔고를 조회한다.

        Args:
            symbol: 특정 종목 필터. None이면 전체 잔고.
        """
        ...

    async def place_order(self, order: Order) -> OrderAck:
        """주문을 전송하고 응답을 반환한다."""
        ...


# ---------------------------------------------------------------------------
# 시세 피드 추상화 (WebSocket 또는 REST 폴링)
# ---------------------------------------------------------------------------


@runtime_checkable
class MarketPoller(Protocol):
    """시세 피드 공통 인터페이스.

    Toss REST 폴링 기반 피드 및 향후 다른 피드가 이 Protocol을 만족해야 한다.
    Strategy Engine은 이 Protocol을 통해 피드와 상호작용한다.
    """

    def subscribe(self, symbol: str) -> None:
        """종목을 구독 등록한다."""
        ...

    async def start(self) -> None:
        """피드를 시작한다."""
        ...

    async def stop(self) -> None:
        """피드를 종료한다."""
        ...
