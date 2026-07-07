"""GET /balance — 실계좌 평가금액·평가손익 조회 (계좌 요약 카드용)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from core.api.deps import ContainerDep
from core.api.models import BalanceInfo, BalanceItem

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/balance", response_model=BalanceInfo, summary="계좌 평가금액·평가손익 조회")
async def get_balance(container: ContainerDep) -> BalanceInfo:
    """Toss 실계좌 보유 종목의 평가금액·평가손익을 조회한다.

    position_sync가 쓰는 매입원가 기준 positions 테이블과 달리, 이 엔드포인트는
    Toss holdings API를 그대로 반영해 현재가·평가금액·평가손익까지 담고 있다.
    Toss 브로커가 주입된 경우에만 조회 가능(읽기 전용 GET이라 --with-trading
    트레이딩 게이트와 무관하게 항상 호출 가능).
    """
    broker = container.broker
    if broker is None:
        raise HTTPException(
            status_code=503,
            detail="브로커 어댑터가 초기화되지 않았습니다. Toss 환경에서만 잔고를 조회할 수 있습니다.",
        )

    try:
        balance = await broker.get_balance()
    except Exception as exc:
        logger.exception("계좌 잔고 조회 실패")
        raise HTTPException(status_code=502, detail="계좌 잔고 조회에 실패했습니다.") from exc

    return BalanceInfo(
        items=[
            BalanceItem(
                symbol=item.symbol,
                symbol_name=item.symbol_name,
                qty=item.qty,
                avg_price=item.avg_price,
                current_price=item.current_price,
                eval_amount=item.eval_amount,
                profit_loss=item.profit_loss,
                profit_loss_rate=item.profit_loss_rate,
                market=item.market,
            )
            for item in balance.items
        ],
        total_eval_amount_krw=balance.total_eval_amount_krw,
        total_profit_loss_krw=balance.total_profit_loss_krw,
        deposit=balance.deposit,
    )
