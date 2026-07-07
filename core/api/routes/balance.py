"""GET /balance — 실계좌 평가금액·평가손익 조회 (계좌 요약 카드용)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from core.api.deps import ContainerDep
from core.api.models import BalanceInfo, BalanceItem

logger = logging.getLogger(__name__)
router = APIRouter()

_KST = ZoneInfo("Asia/Seoul")


async def _fetch_day_change(
    broker: object, symbol: str, current_price: float
) -> tuple[Decimal, float] | None:
    """전일 종가 대비 당일 등락(금액, 비율)을 계산한다.

    Toss holdings/현재가 API는 전일 종가를 직접 주지 않아, 일봉 캔들 2개를
    가져와 "오늘 날짜(KST)가 아닌 가장 최근 봉"을 전일 종가로 쓴다. 캔들 조회가
    실패하거나 데이터가 없으면 None — 호출부가 이걸 매입가 기준 수익률로
    잘못 대체하지 않고 결측으로 표시해야 한다(이번에 고친 버그의 재발 방지).
    """
    try:
        candles = await broker.get_candles(symbol, interval="1d", count=2)  # type: ignore[attr-defined]
    except Exception:
        logger.warning("당일 등락 계산용 캔들 조회 실패: %s", symbol, exc_info=True)
        return None

    if not candles:
        return None

    today_kst = datetime.now(_KST).date()
    prior_days = [c for c in candles if c.timestamp.astimezone(_KST).date() != today_kst]
    prev_close = float((prior_days[-1] if prior_days else candles[0]).close_price)
    if not prev_close:
        return None

    # adapter의 BalanceItem.current_price는 float, 캔들 종가는 Decimal이라 여기서
    # float으로 맞춘 뒤 응답 모델(Decimal 필드)에 넣을 때만 다시 Decimal로 감싼다.
    change = float(current_price) - prev_close
    return Decimal(str(change)), change / prev_close


@router.get("/balance", response_model=BalanceInfo, summary="계좌 평가금액·평가손익 조회")
async def get_balance(container: ContainerDep) -> BalanceInfo:
    """Toss 실계좌 보유 종목의 평가금액·평가손익을 조회한다.

    position_sync가 쓰는 매입원가 기준 positions 테이블과 달리, 이 엔드포인트는
    Toss holdings API를 그대로 반영해 현재가·평가금액·평가손익까지 담고 있다.
    Toss 브로커가 주입된 경우에만 조회 가능(읽기 전용 GET이라 --with-trading
    트레이딩 게이트와 무관하게 항상 호출 가능).

    보유 종목별로 전일 종가 대비 당일 등락도 함께 계산해서 내려준다(day_change*).
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

    day_changes = await asyncio.gather(
        *(_fetch_day_change(broker, item.symbol, item.current_price) for item in balance.items)
    )

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
                day_change=day_change[0] if day_change else None,
                day_change_rate=day_change[1] if day_change else None,
                market=item.market,
            )
            for item, day_change in zip(balance.items, day_changes, strict=True)
        ],
        total_eval_amount_krw=balance.total_eval_amount_krw,
        total_profit_loss_krw=balance.total_profit_loss_krw,
        deposit=balance.deposit,
    )
