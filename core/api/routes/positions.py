"""GET /positions — 보유 포지션 목록 조회."""

from __future__ import annotations

from fastapi import APIRouter

from core.api.deps import ContainerDep
from core.api.models import PositionItem, PositionList

router = APIRouter()


@router.get("/positions", response_model=PositionList, summary="보유 포지션 조회")
async def get_positions(container: ContainerDep) -> PositionList:
    """StateStore에서 현재 보유 포지션을 읽어 반환한다."""
    async with container.store.conn.execute(
        "SELECT symbol, market, env, qty, avg_price, opened_at, updated_at "
        "FROM positions WHERE qty > 0 ORDER BY updated_at DESC"
    ) as cursor:
        rows = await cursor.fetchall()

    items = [
        PositionItem(
            symbol=row["symbol"],
            market=row["market"],
            env=row["env"],
            qty=row["qty"],
            avg_price=row["avg_price"],
            book_value=row["qty"] * row["avg_price"],
            opened_at=row["opened_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]
    return PositionList(total=len(items), items=items)
