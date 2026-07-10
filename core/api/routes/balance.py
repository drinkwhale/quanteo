"""GET /balance — 실계좌 평가금액·평가손익 조회 (계좌 요약 카드용)."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from core.api.deps import ContainerDep
from core.api.models import BalanceInfo, BalanceItem, DayChange

logger = logging.getLogger(__name__)
router = APIRouter()

_KST = ZoneInfo("Asia/Seoul")


def _candle_date_kst(candle: object) -> date:
    """캔들 타임스탬프를 KST 날짜로 변환한다.

    국내 종목은 이 변환이 맞다고 실측으로 확인했다. 해외(미국) 종목은 Toss가
    캔들 타임스탬프를 어느 시간대로 내려주는지 실측 데이터가 없다 — 지금
    보유 종목에 해외 주식이 없어 검증하지 못했다. 해외 종목을 매수하게 되면
    _fetch_day_change가 실제로 "오늘"을 정확히 구분하는지 반드시 재검증할 것
    (개장 전 새벽 시간대에 하루 어긋날 가능성 있음).
    """
    return candle.timestamp.astimezone(_KST).date()  # type: ignore[attr-defined]


async def _fetch_day_change(broker: object, symbol: str, current_price: float) -> DayChange | None:
    """전일 종가 대비 당일 등락을 계산한다.

    한국 증시 관행상 "등락률"은 항상 전일 종가 기준이다 (당일 시가 기준이
    아니다 — 한때 API 제약 때문에 시가 기준으로 바꿨던 적이 있는데, 실제
    HTS/MTS 표준 정의와 어긋나 다시 전일 종가 기준으로 되돌렸다). 일봉
    캔들에서 "오늘(KST) 이전 날짜 중 가장 최근" 봉을 찾아 그 close_price를
    전일 종가로 쓴다. get_candles의 반환 순서가 최신·과거 어느 쪽인지 문서와
    실제 응답이 어긋나 있어(문서: 오래된→최신, 실측: 최신→오래된) 인덱스로
    추정하지 않고 날짜를 직접 비교한다.

    전일 종가 기준이므로 오늘 캔들이 아직 형성되지 않은 개장 전에도(전일
    캔들만 있으면) 계산할 수 있다 — 오늘 시가 기준이었을 때는 개장 전엔
    아예 계산이 불가능했다.

    None을 반환하는 세 가지 경우를 로그 레벨로 구분한다 — 다 같은 "실패"가
    아니다:
    - 캔들 조회 자체가 예외를 던짐 → warning (API 이상, 조사 대상)
    - 오늘 이전 날짜의 캔들이 하나도 없음 → debug (상장 첫날 등 정상 상태)
    - 전일 캔들은 있는데 close_price가 0/falsy → warning (데이터 이상, 조사 대상)
    매입가 기준 수익률로 조용히 대체하지 않고 항상 None으로 결측을 알린다.
    """
    try:
        candles = await broker.get_candles(symbol, interval="1d", count=2)  # type: ignore[attr-defined]
    except Exception:
        logger.warning("당일 등락 계산용 캔들 조회 실패: %s", symbol, exc_info=True)
        return None

    today_kst = datetime.now(_KST).date()
    prior_candles = [c for c in candles if _candle_date_kst(c) < today_kst]
    if not prior_candles:
        logger.debug("전일 이전 캔들 없음(상장 첫날 등 가능): %s", symbol)
        return None

    prev_candle = max(prior_candles, key=_candle_date_kst)
    prev_close = float(prev_candle.close_price)
    if not prev_close:
        logger.warning(
            "전일 캔들의 close_price가 비정상(0 또는 falsy): symbol=%s, close_price=%r",
            symbol,
            prev_candle.close_price,
        )
        return None

    change = float(current_price) - prev_close
    return DayChange(amount=Decimal(str(change)), rate=change / prev_close)


@router.get("/balance", response_model=BalanceInfo, summary="계좌 평가금액·평가손익 조회")
async def get_balance(container: ContainerDep) -> BalanceInfo:
    """Toss 실계좌 보유 종목의 평가금액·평가손익을 조회한다.

    position_sync가 쓰는 매입원가 기준 positions 테이블과 달리, 이 엔드포인트는
    Toss holdings API를 그대로 반영해 현재가·평가금액·평가손익까지 담고 있다.
    Toss 브로커가 주입된 경우에만 조회 가능(읽기 전용 GET이라 --with-trading
    트레이딩 게이트와 무관하게 항상 호출 가능).

    보유 종목별로 전일 종가 대비 당일 등락도 함께 계산해서 내려준다(day_change).
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
                day_change=day_change,
                market=item.market,
            )
            for item, day_change in zip(balance.items, day_changes, strict=True)
        ],
        total_eval_amount_krw=balance.total_eval_amount_krw,
        total_profit_loss_krw=balance.total_profit_loss_krw,
        deposit=balance.deposit,
    )
