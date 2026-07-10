"""GET /balance — 실계좌 평가금액·평가손익 조회 (계좌 요약 카드용)."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from fastapi import APIRouter, HTTPException

from core.api.deps import ContainerDep
from core.api.models import BalanceInfo, BalanceItem, DayChange
from core.config.settings import Market

logger = logging.getLogger(__name__)
router = APIRouter()


async def _fetch_day_change(
    kis_client: object | None, symbol: str, market: Market, current_price: float
) -> DayChange | None:
    """전일 종가 대비 당일 등락을 계산한다.

    한국 증시 관행상 "등락률"은 항상 전일 종가 기준이다. Toss 캔들 API
    (get_candles)의 종가 데이터를 전일 종가로 썼던 적이 있는데, 실측으로
    실제 시세와 어긋나는 사례가 확인됐다(SK하이닉스: Toss 2,253,000원 vs
    KIS·네이버 2,186,000원 — 3% 이상 차이). 그래서 전일 종가만 KIS
    실시간 시세 조회(stck_sdpr)로 대체한다.

    KIS 국내 시세 조회 엔드포인트만 검증됐다 — 해외 종목은 이 함수 범위
    밖이라(kis_client가 domestic 전용 API만 지원) market이 해외면 항상
    결측 처리한다.

    None을 반환하는 경우를 로그 레벨로 구분한다 — 다 같은 "실패"가 아니다:
    - kis_client가 아예 없음(설정 안 됨) → debug (정상적인 미설정 상태)
    - 해외 종목 → debug (KIS 조회 범위 밖, 정상 상태)
    - KIS 조회 자체가 예외를 던짐 → warning (API 이상, 조사 대상)
    매입가 기준 수익률로 조용히 대체하지 않고 항상 None으로 결측을 알린다.
    """
    if kis_client is None:
        logger.debug("KIS 클라이언트 미설정 — day_change 결측: %s", symbol)
        return None

    if market != Market.DOMESTIC:
        logger.debug("해외 종목은 KIS 전일 종가 조회 범위 밖 — day_change 결측: %s", symbol)
        return None

    try:
        prev_close = await kis_client.get_prev_close(symbol)  # type: ignore[attr-defined]
    except Exception:
        logger.warning("KIS 전일 종가 조회 실패: %s", symbol, exc_info=True)
        return None

    prev_close_f = float(prev_close)
    if not prev_close_f:
        logger.warning("KIS 전일 종가가 비정상(0 또는 falsy): symbol=%s, value=%r", symbol, prev_close)
        return None

    change = float(current_price) - prev_close_f
    return DayChange(amount=Decimal(str(change)), rate=change / prev_close_f)


@router.get("/balance", response_model=BalanceInfo, summary="계좌 평가금액·평가손익 조회")
async def get_balance(container: ContainerDep) -> BalanceInfo:
    """Toss 실계좌 보유 종목의 평가금액·평가손익을 조회한다.

    position_sync가 쓰는 매입원가 기준 positions 테이블과 달리, 이 엔드포인트는
    Toss holdings API를 그대로 반영해 현재가·평가금액·평가손익까지 담고 있다.
    Toss 브로커가 주입된 경우에만 조회 가능(읽기 전용 GET이라 --with-trading
    트레이딩 게이트와 무관하게 항상 호출 가능).

    보유 종목별로 전일 종가 대비 당일 등락도 함께 계산해서 내려준다(day_change).
    전일 종가는 KIS 시세 조회로 얻는다(container.kis_client 설정 시에만) —
    Toss 캔들 API의 종가가 실측으로 부정확함이 확인돼 대체함.
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

    kis_client = container.kis_client
    day_changes = await asyncio.gather(
        *(
            _fetch_day_change(kis_client, item.symbol, item.market, item.current_price)
            for item in balance.items
        )
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
                day_change=day_change,
                market=item.market,
            )
            for item, day_change in zip(balance.items, day_changes, strict=True)
        ],
        total_eval_amount_krw=balance.total_eval_amount_krw,
        total_profit_loss_krw=balance.total_profit_loss_krw,
        deposit=balance.deposit,
    )
