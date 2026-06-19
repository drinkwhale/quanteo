"""
KIS WebSocket 어댑터 — 실시간 시세·체결 구독.

참조: open-trading-api/examples_user/domestic_stock/websocket_domestic_stock.py
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from core.adapters.kis.auth import KisAuth
from core.adapters.kis.tr_ids import get_tr_ids, get_ws_domain
from core.config.settings import Env, Market

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 수신 메시지 타입
# ---------------------------------------------------------------------------


@dataclass
class WsMessage:
    """WebSocket 수신 메시지."""

    tr_id: str
    tr_key: str  # 종목코드 등 구독 키
    data_body: str  # 파이프(|) 구분 원시 문자열
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 구독 핸들러 타입
# ---------------------------------------------------------------------------

MessageHandler = Callable[[WsMessage], None]


# ---------------------------------------------------------------------------
# KIS WebSocket 클라이언트
# ---------------------------------------------------------------------------


class KisWsClient:
    """KIS 실시간 WebSocket 클라이언트.

    구독(subscribe)하고 싶은 종목·채널을 등록하면 수신 메시지를 핸들러로 전달한다.

    Args:
        auth: KisAuth 인스턴스.
        env: 투자 환경.
        market: 대상 시장.
        on_message: 메시지 수신 콜백 (동기 함수).
        reconnect_delay: 재연결 대기 시간(초).
    """

    def __init__(
        self,
        auth: KisAuth,
        env: Env = Env.VPS,
        market: Market = Market.DOMESTIC,
        on_message: MessageHandler | None = None,
        reconnect_delay: float = 5.0,
    ) -> None:
        self.auth = auth
        self.env = env
        self.market = market
        self.on_message = on_message
        self.reconnect_delay = reconnect_delay
        self._tr_ids = get_tr_ids(env, market)
        self._ws_url = get_ws_domain(env)
        self._subscriptions: list[tuple[str, str]] = []  # (tr_id, tr_key) 목록
        self._conn: ClientConnection | None = None
        self._running = False

    # ------------------------------------------------------------------
    # 구독 등록
    # ------------------------------------------------------------------

    def subscribe_price(self, symbol: str) -> None:
        """실시간 체결가 구독 등록."""
        self._subscriptions.append((self._tr_ids.ws_price, symbol))

    def subscribe_quote(self, symbol: str) -> None:
        """실시간 호가 구독 등록 (국내만 지원)."""
        if self._tr_ids.ws_quote is None:
            raise ValueError(f"호가 구독은 {self.market.value} 시장에서 지원되지 않습니다.")
        self._subscriptions.append((self._tr_ids.ws_quote, symbol))

    def subscribe_fill(self, symbol: str) -> None:
        """실시간 체결통보 구독 등록 (국내만 지원)."""
        if self._tr_ids.ws_fill is None:
            raise ValueError(f"체결통보 구독은 {self.market.value} 시장에서 지원되지 않습니다.")
        self._subscriptions.append((self._tr_ids.ws_fill, symbol))

    # ------------------------------------------------------------------
    # 연결 및 수신 루프
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """WebSocket에 연결하고 메시지를 수신한다. 끊기면 자동 재연결."""
        self._running = True
        while self._running:
            try:
                await self._connect_and_receive()
            except Exception as exc:
                if not self._running:
                    break
                logger.warning("WS 연결 끊김, %ss 후 재연결: %s", self.reconnect_delay, exc)
                await asyncio.sleep(self.reconnect_delay)

    async def stop(self) -> None:
        """수신 루프를 종료한다."""
        self._running = False
        if self._conn:
            await self._conn.close()

    async def _connect_and_receive(self) -> None:
        ws_key = await self.auth.get_websocket_key()
        logger.info("WS 연결 시도: %s", self._ws_url)

        async with websockets.connect(self._ws_url) as conn:
            self._conn = conn
            logger.info("WS 연결 완료")

            # 구독 요청 전송
            for tr_id, tr_key in self._subscriptions:
                await self._send_subscribe(conn, ws_key.key, tr_id, tr_key)

            # 메시지 수신
            async for raw_msg in conn:
                if not self._running:
                    break
                self._handle_raw(raw_msg)

    async def _send_subscribe(
        self, conn: ClientConnection, ws_key: str, tr_id: str, tr_key: str
    ) -> None:
        payload = {
            "header": {
                "approval_key": ws_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": tr_key,
                }
            },
        }
        await conn.send(json.dumps(payload))
        logger.debug("WS 구독 요청: tr_id=%s tr_key=%s", tr_id, tr_key)

    def _handle_raw(self, raw: str | bytes) -> None:
        """수신 메시지를 파싱하고 콜백을 호출한다."""
        text = raw if isinstance(raw, str) else raw.decode("utf-8")

        # PINGPONG 무시
        if text.startswith("0|") or text.startswith("1|"):
            parts = text.split("|", 3)
            if len(parts) < 4:
                return
            tr_id = parts[1]
            tr_key_and_body = parts[2] if len(parts) > 2 else ""
            data_body = parts[3] if len(parts) > 3 else ""
            msg = WsMessage(tr_id=tr_id, tr_key=tr_key_and_body, data_body=data_body)
        else:
            # JSON 응답 (구독 확인, 에러 등)
            try:
                data: dict[str, Any] = json.loads(text)
            except json.JSONDecodeError:
                logger.debug("WS 파싱 불가 메시지: %s", text[:80])
                return
            header = data.get("header", {})
            tr_id = header.get("tr_id", "")
            tr_key = header.get("tr_key", "")
            msg = WsMessage(tr_id=tr_id, tr_key=tr_key, data_body="", raw=data)
            rt_cd = data.get("body", {}).get("rt_cd")
            if rt_cd and rt_cd != "0":
                logger.warning("WS 에러 응답: %s", data.get("body", {}).get("msg1", ""))
                return

        if self.on_message:
            try:
                self.on_message(msg)
            except Exception as exc:
                logger.error("on_message 콜백 예외: %s", exc)

    # ------------------------------------------------------------------
    # AsyncIterator 인터페이스 (선택적 사용)
    # ------------------------------------------------------------------

    async def messages(self) -> AsyncIterator[WsMessage]:
        """수신 메시지를 async generator로 yield한다 (단일 연결, 재연결 없음)."""
        ws_key = await self.auth.get_websocket_key()
        async with websockets.connect(self._ws_url) as conn:
            self._conn = conn
            for tr_id, tr_key in self._subscriptions:
                await self._send_subscribe(conn, ws_key.key, tr_id, tr_key)
            async for raw_msg in conn:
                text = raw_msg if isinstance(raw_msg, str) else raw_msg.decode("utf-8")
                if text.startswith("0|") or text.startswith("1|"):
                    parts = text.split("|", 3)
                    if len(parts) >= 4:
                        yield WsMessage(
                            tr_id=parts[1], tr_key=parts[2], data_body=parts[3]
                        )
