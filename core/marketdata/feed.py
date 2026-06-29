"""
MarketDataFeed — 브로커 어댑터 기반 시세 데이터 공급 컨테이너.

브로커에 따라 두 가지 동작 모드를 지원한다:
  - KIS: KisWsClientFeed (feed_kis.py) — WebSocket 실시간 수신
  - Toss: PollingFeed (이 파일) — REST 폴링 방식 (WebSocket 미지원)

StrategyEngine은 subscribe() / start() / stop() 인터페이스만 바라보므로
브로커 교체 시 Strategy Engine 코드를 수정할 필요가 없다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from core.marketdata.models import Tick

logger = logging.getLogger(__name__)

TickHandler = Callable[[Tick], None]


# ---------------------------------------------------------------------------
# REST 폴링 기반 피드 (Toss 어댑터용)
# ---------------------------------------------------------------------------


class MarketDataFeed:
    """REST 폴링 방식 시세 피드.

    BrokerAdapter의 get_price()를 주기적으로 호출해 Tick을 생성한다.
    Toss API는 WebSocket을 미지원하므로 이 방식을 사용한다.

    Args:
        rest_client: BrokerAdapter Protocol을 만족하는 REST 클라이언트.
        poll_interval: 폴링 주기 (초). 기본값 2.0.
    """

    def __init__(
        self,
        rest_client: object,  # BrokerAdapter Protocol — 런타임 임포트 순환 방지용
        poll_interval: float = 2.0,
    ) -> None:
        self._rest = rest_client
        self._poll_interval = poll_interval
        self._symbols: set[str] = set()
        self._tick_handlers: list[TickHandler] = []
        self._running = False
        self._stop_event = asyncio.Event()

    def subscribe(self, symbol: str) -> None:
        """종목을 구독 등록한다.

        폴링 루프가 실행 중일 때 호출해도 다음 폴링 주기부터 반영된다.
        """
        self._symbols.add(symbol)
        logger.debug("Toss 폴링 구독 추가: %s (총 %d종목)", symbol, len(self._symbols))

    def on_tick(self, handler: TickHandler) -> None:
        """Tick 수신 핸들러를 등록한다."""
        self._tick_handlers.append(handler)

    async def start(self) -> None:
        """폴링 루프를 시작한다 (MarketPoller Protocol)."""
        await self.run()

    async def run(self) -> None:
        """폴링 루프 실행 — stop()이 호출될 때까지 지속."""
        self._running = True
        self._stop_event.clear()
        logger.info(
            "Toss REST 폴링 시작 (interval=%.1fs)", self._poll_interval
        )

        while not self._stop_event.is_set():
            if self._symbols:
                await self._poll_once()
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=self._poll_interval,
                )
                break  # stop_event 수신 시 종료
            except asyncio.TimeoutError:
                pass  # 정상 폴링 주기 완료, 계속 진행

        self._running = False
        logger.info("Toss REST 폴링 종료")

    async def stop(self) -> None:
        """폴링 루프를 종료한다."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # 폴링 실행
    # ------------------------------------------------------------------

    async def _poll_once(self) -> None:
        """등록된 모든 종목에 대해 현재가를 조회하고 Tick을 생성한다.

        Toss API는 콤마 구분으로 배치 조회를 지원하지만,
        get_price() 인터페이스가 단일 종목이므로 종목별로 호출한다.
        배치 최적화는 T042 확장 시 고려한다.
        """
        for symbol in list(self._symbols):
            try:
                price_info = await self._rest.get_price(symbol)  # type: ignore[attr-defined]
                tick = Tick(
                    symbol=symbol,
                    price=price_info.current_price,
                    volume=price_info.volume,
                    timestamp=datetime.now(UTC),
                    market="domestic" if price_info.market.value == "domestic" else "overseas",
                )
                for handler in self._tick_handlers:
                    handler(tick)
            except Exception as exc:
                logger.warning("Toss 폴링 오류 (%s): %s", symbol, exc)
