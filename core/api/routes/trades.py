"""GET /trades — 체결 내역 조회."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from core.api.deps import ContainerDep
from core.api.models import FillItem, FillList

router = APIRouter()


@router.get("/trades", response_model=FillList, summary="체결 내역 조회")
async def get_trades(
    container: ContainerDep,
    count: int = Query(default=100, ge=1, le=500, description="최대 반환 건수"),
) -> FillList:
    """Toss 브로커에서 최근 체결 내역을 조회한다.

    브로커가 없으면 503을 반환한다.
    """
    broker = container.broker
    if broker is None:
        raise HTTPException(
            status_code=503,
            detail="브로커 어댑터가 초기화되지 않았습니다. Toss 환경에서만 체결 내역을 조회할 수 있습니다.",
        )

    fills = await broker.get_trades(count=count)

    items = [
        FillItem(
            symbol=f.symbol,
            price=float(f.price),
            volume=f.volume,
            timestamp=f.timestamp,
            currency=f.currency,
            side=f.side,
        )
        for f in fills
    ]
    return FillList(total=len(items), items=items)
