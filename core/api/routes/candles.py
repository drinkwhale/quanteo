"""GET /candles — 캔들 차트 데이터 조회."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from core.api.deps import ContainerDep
from core.api.models import CandleItem, CandleList

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/candles", response_model=CandleList, summary="캔들 데이터 조회")
async def get_candles(
    container: ContainerDep,
    symbol: str = Query(..., description="종목 심볼 (예: 005930, AAPL)"),
    interval: Literal["1m", "1d"] = Query("1d", description="캔들 간격 (1분봉: 1m, 일봉: 1d)"),
    count: int = Query(100, ge=1, le=200, description="조회할 캔들 수 (1~200)"),
    before: str | None = Query(None, description="조회 기준 일시 (ISO 8601, 선택)"),
    adjusted: bool = Query(True, description="수정주가 여부"),
) -> CandleList:
    """캔들 차트 데이터를 조회한다.

    Toss API `GET /api/v1/candles`의 프록시 엔드포인트로, 지정된 종목의 OHLCV 데이터를 반환한다.
    현재 지원하는 interval은 1분봉(1m)과 일봉(1d)이다.

    Args:
        symbol: 종목 심볼 (예: 005930, AAPL)
        interval: 캔들 간격 (1m=1분봉, 1d=일봉)
        count: 조회할 캔들 수 (1~200, 기본 100)
        before: 조회 기준 일시 (ISO 8601 형식, 선택)
        adjusted: 수정주가 여부 (기본 True)

    Raises:
        HTTPException(503): 브로커 어댑터가 초기화되지 않았을 때
        HTTPException(502): 어댑터가 캔들 조회에 실패했을 때

    Returns:
        CandleList: 캔들 데이터 목록
    """
    broker = container.broker
    if broker is None:
        raise HTTPException(
            status_code=503,
            detail="브로커 어댑터가 초기화되지 않았습니다.",
        )

    try:
        candles = await broker.get_candles(
            symbol=symbol,
            interval=interval,
            count=count,
            before=before,
            adjusted=adjusted,
        )
        items = [
            CandleItem(
                timestamp=c.timestamp,
                open=float(c.open),
                high=float(c.high),
                low=float(c.low),
                close=float(c.close),
                volume=float(c.volume),
            )
            for c in candles
        ]
        return CandleList(items=items)
    except Exception as e:
        logger.exception(f"캔들 조회 실패: {symbol} {interval}")
        raise HTTPException(
            status_code=502,
            detail=f"캔들 조회 중 오류가 발생했습니다: {str(e)}",
        )
