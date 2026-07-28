"""
마켓 스톡 데이터 API — 거래대금/거래량 기준 종목 조회.

Phase 17: GET /api/market-stocks?sort_by=trading_value&limit=10
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from core.api.deps import AppContainer, ContainerDep
from core.api.models import (
    MarketStockCategory,
    MarketStockItem,
    MarketStockList,
    MarketStockSummary,
    MarketStockSummaryItem,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# SQL 주입 방지: 화이트리스트 매핑
ALLOWED_ORDER_BY = {
    "trading_value": "trading_value DESC",
    "volume": "trading_volume DESC",
    "uptrend": "change_rate DESC",
    "downtrend": "change_rate ASC",
}


async def _get_latest_timestamp(container: AppContainer) -> str:
    """market_data 테이블의 최신 타임스탬프를 조회한다.

    Raises:
        HTTPException(404): 마켓 데이터가 아직 수집되지 않음.
        HTTPException(503): DB 조회 실패(store 미오픈, I/O 오류 등).
    """
    try:
        async with container.store.conn.execute("SELECT MAX(timestamp) FROM market_data") as cursor:
            latest = await cursor.fetchone()
    except Exception as exc:
        logger.exception("마켓 데이터 최신 타임스탬프 조회 실패")
        raise HTTPException(
            status_code=503,
            detail="마켓 데이터 조회에 실패했습니다.",
        ) from exc

    if not latest or not latest[0]:
        raise HTTPException(
            status_code=404,
            detail="마켓 데이터가 없습니다",
        )

    return latest[0]


@router.get(
    "/market-stocks", response_model=MarketStockList, summary="거래대금/거래량 TOP 종목 조회"
)
async def get_market_stocks(
    container: ContainerDep,
    sort_by: Literal["trading_value", "volume", "uptrend", "downtrend"] = "trading_value",
    limit: int = Query(default=10, ge=1, le=100, description="조회할 종목 수 (1~100)"),
) -> MarketStockList:
    """거래대금/거래량 기준 TOP 종목을 조회한다.

    Args:
        sort_by: 정렬 기준
            - trading_value: 거래대금 높은 순
            - volume: 거래량 많은 순
            - uptrend: 상승률 높은 순
            - downtrend: 하락률 높은 순
        limit: 조회할 종목 수 (1~100, 기본값 10)

    Raises:
        HTTPException(404): 마켓 데이터가 없거나 조회된 종목이 없을 때
        HTTPException(503): DB 조회 실패
    """
    latest_timestamp = await _get_latest_timestamp(container)

    # 정렬 쿼리 구성 (화이트리스트 사용) — sort_by는 Literal로 이미 제한되지만
    # 향후 Literal에 값이 추가되고 화이트리스트 갱신을 누락하는 경우를 방어한다.
    order_by = ALLOWED_ORDER_BY.get(sort_by)
    if not order_by:
        raise HTTPException(
            status_code=400,
            detail="Invalid sort_by parameter",
        )

    # 데이터 조회 (안전한 매개변수화)
    query = f"""
        SELECT
            symbol, price, change_rate,
            trading_volume, trading_value, timestamp
        FROM market_data
        WHERE timestamp = ?
        ORDER BY {order_by}
        LIMIT ?
    """

    try:
        async with container.store.conn.execute(query, (latest_timestamp, limit)) as cursor:
            rows = await cursor.fetchall()
    except Exception as exc:
        logger.exception("마켓 스톡 조회 실패: sort_by=%s, limit=%s", sort_by, limit)
        raise HTTPException(
            status_code=503,
            detail="마켓 데이터 조회에 실패했습니다.",
        ) from exc

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="조회된 종목이 없습니다",
        )

    data = [
        MarketStockItem(
            symbol=row[0],
            price=row[1],
            change_rate=row[2],
            trading_volume=row[3],
            trading_value=row[4],
            timestamp=row[5],
        )
        for row in rows
    ]

    return MarketStockList(data=data, timestamp=latest_timestamp)


@router.get(
    "/market-stocks/summary",
    response_model=MarketStockSummary,
    summary="마켓 데이터 요약 (카테고리별 TOP 5)",
)
async def get_market_summary(container: ContainerDep) -> MarketStockSummary:
    """마켓 데이터 요약(거래대금·거래량·상승률 각 TOP 5)을 조회한다.

    Raises:
        HTTPException(404): 마켓 데이터가 없을 때
        HTTPException(503): DB 조회 실패
    """
    latest_timestamp = await _get_latest_timestamp(container)

    # 각 카테고리별 TOP 5
    query_template = """
        SELECT
            symbol, price, change_rate,
            trading_volume, trading_value
        FROM market_data
        WHERE timestamp = ?
        ORDER BY {} DESC
        LIMIT 5
    """

    categories = {
        "top_trading_value": ("trading_value", "거래대금"),
        "top_volume": ("trading_volume", "거래량"),
        "top_gainers": ("change_rate", "급상승"),
    }

    result_categories: dict[str, MarketStockCategory] = {}

    for key, (col, label) in categories.items():
        try:
            async with container.store.conn.execute(
                query_template.format(col),
                (latest_timestamp,),
            ) as cursor:
                rows = await cursor.fetchall()
        except Exception as exc:
            logger.exception("마켓 요약 조회 실패: category=%s", key)
            raise HTTPException(
                status_code=503,
                detail="마켓 데이터 조회에 실패했습니다.",
            ) from exc

        result_categories[key] = MarketStockCategory(
            label=label,
            stocks=[
                MarketStockSummaryItem(
                    symbol=row[0],
                    price=row[1],
                    change_rate=row[2],
                    trading_volume=row[3],
                    trading_value=row[4],
                )
                for row in rows
            ],
        )

    return MarketStockSummary(timestamp=latest_timestamp, categories=result_categories)
