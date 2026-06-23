"""
Order Executor — 주문 전송, 멱등성 보장, 체결 추적.

핵심 불변식:
- 동일 client_order_id가 중복 제출되어도 주문은 1회만 전송된다.
- 모든 주문 상태 변경은 StateStore에 영속화된다.
- 주문/체결 이벤트는 Event Bus를 통해 발행된다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from core.events.bus import EventBus
from core.events.types import Event, EventType
from core.risk.models import Order, OrderSide
from core.store.db import StateStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 응답 모델
# ---------------------------------------------------------------------------


class OrderAck:
    """KIS API 주문 응답.

    Args:
        client_order_id: 클라이언트 주문 ID (멱등키).
        kis_order_id: KIS가 발급한 주문 번호 (ODNO).
        symbol: 종목 코드.
        status: 주문 상태 ('submitted' | 'rejected').
        raw: KIS API 원시 응답.
    """

    def __init__(
        self,
        client_order_id: str,
        kis_order_id: str,
        symbol: str,
        status: str,
        raw: dict[str, Any],
    ) -> None:
        self.client_order_id = client_order_id
        self.kis_order_id = kis_order_id
        self.symbol = symbol
        self.status = status
        self.raw = raw

    def __repr__(self) -> str:
        return (
            f"OrderAck(client_order_id={self.client_order_id!r}, "
            f"kis_order_id={self.kis_order_id!r}, status={self.status!r})"
        )


# ---------------------------------------------------------------------------
# Order Executor
# ---------------------------------------------------------------------------


class OrderExecutor:
    """주문 전송·멱등성·체결 추적을 담당하는 실행기.

    사용 흐름:
        order = risk_manager.evaluate(signal, portfolio)
        ack = await executor.submit(order)

    Args:
        rest_client: KIS REST 클라이언트 (place_order 구현 필요).
        store: 주문·체결 영속화용 StateStore.
        bus: 주문 이벤트 발행용 EventBus.
    """

    def __init__(self, rest_client: Any, store: StateStore, bus: EventBus) -> None:
        self._rest = rest_client
        self._store = store
        self._bus = bus

    async def submit(self, order: Order) -> OrderAck:
        """주문을 KIS에 전송하고 DB에 영속화한다.

        멱등성: 동일 client_order_id로 재호출 시 기존 레코드를 반환한다.

        Args:
            order: Risk Manager가 승인한 주문.

        Returns:
            OrderAck: KIS 응답 요약.

        Raises:
            RuntimeError: KIS API 호출 실패 시.
        """
        # 멱등성 체크 — 이미 처리된 주문이면 DB에서 반환
        existing = await self._fetch_existing(order.client_order_id)
        if existing:
            logger.info("중복 주문 무시 (client_id=%s, status=%s)", order.client_order_id, existing["status"])
            return OrderAck(
                client_order_id=order.client_order_id,
                kis_order_id=existing["kis_order_id"] or "",
                symbol=order.symbol,
                status=existing["status"],
                raw={},
            )

        now = datetime.now(UTC).isoformat()

        # DB에 pending 상태로 저장
        await self._store.conn.execute(
            """
            INSERT INTO orders
                (client_order_id, symbol, market, env, side, order_type, qty, price, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                order.client_order_id,
                order.symbol,
                order.market.value,
                order.env.value,
                order.side.value,
                order.order_type.value,
                order.qty,
                order.price,
                now,
                now,
            ),
        )
        await self._store.conn.commit()

        # KIS API 호출
        try:
            ack = await self._rest.place_order(order)
        except Exception as exc:
            logger.error("주문 전송 실패: %s (client_id=%s)", exc, order.client_order_id)
            await self._update_status(order.client_order_id, "rejected", kis_order_id=None)
            self._bus.publish_nowait(
                Event(
                    type=EventType.ORDER_REJECTED,
                    payload={"client_order_id": order.client_order_id, "reason": str(exc)},
                    source="executor",
                )
            )
            raise

        # DB 상태 업데이트 (submitted)
        await self._update_status(order.client_order_id, "submitted", kis_order_id=ack.kis_order_id)

        # Event Bus 발행
        self._bus.publish_nowait(
            Event(
                type=EventType.ORDER_SUBMITTED,
                payload={
                    "client_order_id": order.client_order_id,
                    "kis_order_id": ack.kis_order_id,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "qty": order.qty,
                    "price": order.price,
                },
                source="executor",
            )
        )

        logger.info(
            "주문 제출: %s %s %d주 (client=%s kis=%s)",
            order.symbol,
            order.side.value,
            order.qty,
            order.client_order_id,
            ack.kis_order_id,
        )
        return ack

    async def record_fill(
        self,
        client_order_id: str,
        fill_qty: int,
        fill_price: float,
    ) -> None:
        """체결 내역을 DB에 기록하고 ORDER_FILLED 이벤트를 발행한다.

        Args:
            client_order_id: 체결된 주문의 클라이언트 ID.
            fill_qty: 체결 수량.
            fill_price: 체결 단가.
        """
        row = await self._fetch_existing(client_order_id)
        if not row:
            logger.warning("체결 기록 실패 — 주문 없음: client_id=%s", client_order_id)
            return

        now = datetime.now(UTC).isoformat()

        await self._store.conn.execute(
            """
            INSERT INTO fills (order_id, client_order_id, symbol, env, fill_qty, fill_price, filled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                client_order_id,
                row["symbol"],
                row["env"],
                fill_qty,
                fill_price,
                now,
            ),
        )
        await self._update_status(client_order_id, "filled", kis_order_id=None)

        self._bus.publish_nowait(
            Event(
                type=EventType.ORDER_FILLED,
                payload={
                    "client_order_id": client_order_id,
                    "symbol": row["symbol"],
                    "fill_qty": fill_qty,
                    "fill_price": fill_price,
                    "filled_at": now,
                },
                source="executor",
            )
        )
        logger.info(
            "체결 기록: %s %d주 @%s (client=%s)",
            row["symbol"],
            fill_qty,
            fill_price,
            client_order_id,
        )

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    async def _fetch_existing(self, client_order_id: str) -> dict | None:
        """client_order_id로 기존 주문을 조회한다."""
        async with self._store.conn.execute(
            "SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def _update_status(
        self,
        client_order_id: str,
        status: str,
        kis_order_id: str | None,
    ) -> None:
        """주문 상태를 업데이트한다."""
        now = datetime.now(UTC).isoformat()
        if kis_order_id is not None:
            await self._store.conn.execute(
                "UPDATE orders SET status = ?, kis_order_id = ?, updated_at = ? WHERE client_order_id = ?",
                (status, kis_order_id, now, client_order_id),
            )
        else:
            await self._store.conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE client_order_id = ?",
                (status, now, client_order_id),
            )
        await self._store.conn.commit()
