"""GET /orders, POST /orders/{id}/cancel, POST /orders/{id}/modify — 주문 관련 API."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from core.api.deps import ContainerDep
from core.api.models import (
    OrderCancelResponse,
    OrderItem,
    OrderList,
    OrderModifyRequest,
    OrderModifyResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_VALID_STATUSES = {"pending", "submitted", "partial", "filled", "cancelled", "rejected"}


@router.get("/orders", response_model=OrderList, summary="주문 내역 조회")
async def get_orders(
    container: ContainerDep,
    status: str | None = Query(default=None, description="주문 상태 필터 (예: submitted, filled)"),
    limit: int = Query(default=50, ge=1, le=500, description="최대 반환 건수"),
) -> OrderList:
    """StateStore에서 주문 내역을 조회한다.

    status 파라미터로 특정 상태만 필터링할 수 있다.
    """
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 상태: {status!r}")

    if status:
        sql = (
            "SELECT client_order_id, broker_order_id, symbol, market, env, side, "
            "order_type, qty, price, status, created_at, updated_at "
            "FROM orders WHERE status = ? ORDER BY created_at DESC LIMIT ?"
        )
        params: tuple = (status, limit)
    else:
        sql = (
            "SELECT client_order_id, broker_order_id, symbol, market, env, side, "
            "order_type, qty, price, status, created_at, updated_at "
            "FROM orders ORDER BY created_at DESC LIMIT ?"
        )
        params = (limit,)

    async with container.store.conn.execute(sql, params) as cursor:
        rows = await cursor.fetchall()

    items = [
        OrderItem(
            client_order_id=row["client_order_id"],
            broker_order_id=row["broker_order_id"],
            symbol=row["symbol"],
            market=row["market"],
            env=row["env"],
            side=row["side"],
            order_type=row["order_type"],
            qty=row["qty"],
            price=row["price"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]
    return OrderList(total=len(items), items=items)


@router.post("/orders/{order_id}/cancel", response_model=OrderCancelResponse, summary="주문 취소")
async def cancel_order(order_id: str, container: ContainerDep) -> OrderCancelResponse:
    """지정된 주문을 취소한다.

    Toss 브로커가 주입된 경우에만 동작한다.
    취소 성공 후 StateStore의 주문 상태를 CANCELED로 갱신한다.
    """
    broker = container.broker
    if broker is None:
        raise HTTPException(
            status_code=503,
            detail="브로커 어댑터가 초기화되지 않았습니다.",
        )

    try:
        result = await broker.cancel_order(order_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # StateStore 상태 갱신 — 브로커 취소 성공 후 DB 불일치 방지
    now = datetime.now(UTC).isoformat()
    try:
        await container.store.conn.execute(
            "UPDATE orders SET status = 'cancelled', updated_at = ? WHERE broker_order_id = ?",
            (now, order_id),
        )
        await container.store.conn.commit()
    except Exception as db_exc:
        logger.exception(
            "cancel_order DB 갱신 실패 (order_id=%s) — 브로커 취소 성공, 로컬 상태 불일치 주의",
            order_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"브로커 취소는 성공했지만 DB 갱신 실패 — 수동 확인 필요 (order_id={order_id})",
        ) from db_exc

    return OrderCancelResponse(success=True, order_id=result.order_id, message="주문 취소 완료")


@router.post("/orders/{order_id}/modify", response_model=OrderModifyResponse, summary="주문 정정")
async def modify_order(
    order_id: str,
    body: OrderModifyRequest,
    container: ContainerDep,
) -> OrderModifyResponse:
    """지정된 주문을 정정한다.

    Toss 브로커가 주입된 경우에만 동작한다.
    정정 성공 후 StateStore의 주문 상태를 갱신한다.
    """
    broker = container.broker
    if broker is None:
        raise HTTPException(
            status_code=503,
            detail="브로커 어댑터가 초기화되지 않았습니다.",
        )

    price = Decimal(str(body.price)) if body.price is not None else None

    try:
        result = await broker.modify_order(
            order_id,
            order_type=body.order_type,
            quantity=body.quantity,
            price=price,
            confirm_high_value=body.confirm_high_value,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = datetime.now(UTC).isoformat()
    try:
        if body.quantity is not None:
            await container.store.conn.execute(
                "UPDATE orders SET qty = ?, updated_at = ? WHERE broker_order_id = ?",
                (body.quantity, now, order_id),
            )
        if body.price is not None:
            await container.store.conn.execute(
                "UPDATE orders SET price = ?, updated_at = ? WHERE broker_order_id = ?",
                (str(body.price), now, order_id),
            )
        await container.store.conn.commit()
    except Exception as db_exc:
        logger.exception(
            "modify_order DB 갱신 실패 (order_id=%s) — 브로커 정정 성공, 로컬 상태 불일치 주의",
            order_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"브로커 정정은 성공했지만 DB 갱신 실패 — 수동 확인 필요 (order_id={order_id})",
        ) from db_exc

    return OrderModifyResponse(success=True, order_id=result.order_id, message="주문 정정 완료")
