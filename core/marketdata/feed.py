"""
MarketDataFeed — 시세 데이터 공급 컨테이너.

WebSocket 수신 메시지를 정규화해서 구독자에게 전달하는 중간 계층.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable

from core.adapters.kis.ws import KisWsClient, WsMessage
from core.adapters.kis.tr_ids import get_tr_ids
from core.config.settings import Env, Market
from core.marketdata.models import Candle, Quote, Tick
from core.marketdata.normalizer import (
    normalize_domestic_quote,
    normalize_domestic_tick,
    normalize_overseas_tick,
)

logger = logging.getLogger(__name__)

TickHandler = Callable[[Tick], None]
QuoteHandler = Callable[[Quote], None]


class MarketDataFeed:
    """시세 데이터 공급자.

    KisWsClient 위에서 동작하며, 수신 메시지를 Tick/Quote로 정규화해
    등록된 핸들러에 전달한다.

    Args:
        ws_client: KisWsClient 인스턴스.
        env: 투자 환경.
        market: 대상 시장.
    """

    def __init__(
        self,
        ws_client: KisWsClient,
        env: Env = Env.VPS,
        market: Market = Market.DOMESTIC,
    ) -> None:
        self._ws = ws_client
        self._env = env
        self._market = market
        self._tr_ids = get_tr_ids(env, market)

        self._tick_handlers: list[TickHandler] = []
        self._quote_handlers: list[QuoteHandler] = []
        self._symbol_map: dict[str, str] = {}  # tr_key → symbol

        # on_message 콜백 연결
        self._ws.on_message = self._on_ws_message

    def subscribe(self, symbol: str, price: bool = True, quote: bool = False) -> None:
        """종목을 구독 등록한다."""
        if price:
            self._ws.subscribe_price(symbol)
            self._symbol_map[symbol] = symbol
        if quote and self._market == Market.DOMESTIC:
            self._ws.subscribe_quote(symbol)

    def on_tick(self, handler: TickHandler) -> None:
        """Tick 수신 핸들러를 등록한다."""
        self._tick_handlers.append(handler)

    def on_quote(self, handler: QuoteHandler) -> None:
        """Quote 수신 핸들러를 등록한다."""
        self._quote_handlers.append(handler)

    async def run(self) -> None:
        """WebSocket 수신 루프를 시작한다."""
        await self._ws.run()

    async def stop(self) -> None:
        """수신 루프를 종료한다."""
        await self._ws.stop()

    def _on_ws_message(self, msg: WsMessage) -> None:
        """WebSocket 메시지를 받아 정규화 후 핸들러로 전달한다."""
        tr_id = msg.tr_id
        symbol = msg.tr_key

        if tr_id == self._tr_ids.ws_price:
            if self._market == Market.DOMESTIC:
                tick = normalize_domestic_tick(symbol, msg.data_body)
            else:
                tick = normalize_overseas_tick(symbol, msg.data_body)
            if tick:
                for h in self._tick_handlers:
                    h(tick)

        elif tr_id == self._tr_ids.ws_quote:
            quote = normalize_domestic_quote(symbol, msg.data_body)
            if quote:
                for h in self._quote_handlers:
                    h(quote)
