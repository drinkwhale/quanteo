"""GET /orders — 주문 내역 조회."""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api.deps import ContainerDep
from core.api.models import OrderItem, OrderList

router = APIRouter()

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
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"유효하지 않은 상태: {status!r}")

    if status:
        sql = (
            "SELECT client_order_id, kis_order_id, symbol, market, env, side, "
            "order_type, qty, price, status, created_at, updated_at "
            "FROM orders WHERE status = ? ORDER BY created_at DESC LIMIT ?"
        )
        params: tuple = (status, limit)
    else:
        sql = (
            "SELECT client_order_id, kis_order_id, symbol, market, env, side, "
            "order_type, qty, price, status, created_at, updated_at "
            "FROM orders ORDER BY created_at DESC LIMIT ?"
        )
        params = (limit,)

    async with container.store.conn.execute(sql, params) as cursor:
        rows = await cursor.fetchall()

    items = [
        OrderItem(
            client_order_id=row["client_order_id"],
            kis_order_id=row["kis_order_id"],
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
