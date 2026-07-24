"""
마켓 스톡 데이터 API — 거래대금/거래량 기준 종목 조회.

Phase 17: GET /api/market-stocks?sort_by=trading_value&limit=10
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import Field
from typing import Literal

from core.api.deps import ContainerDep

router = APIRouter()

# SQL 주입 방지: 화이트리스트 매핑
ALLOWED_ORDER_BY = {
    "trading_value": "trading_value DESC",
    "volume": "trading_volume DESC",
    "uptrend": "change_rate DESC",
    "downtrend": "change_rate ASC",
}


@router.get("/market-stocks")
async def get_market_stocks(
    sort_by: Literal["trading_value", "volume", "uptrend", "downtrend"] = "trading_value",
    limit: int = Field(default=10, ge=1, le=100),
    container: ContainerDep,
) -> dict:
    """
    거래대금/거래량 기준 TOP 종목 조회.

    Args:
        sort_by: 정렬 기준
            - trading_value: 거래대금 높은 순
            - volume: 거래량 많은 순
            - uptrend: 상승률 높은 순
            - downtrend: 하락률 높은 순
        limit: 조회할 종목 수 (1~100, 기본값 10)

    Returns:
        {
            "data": [
                {
                    "symbol": "005930",
                    "price": 70500,
                    "change_rate": 0.71,
                    "trading_volume": 17500000,
                    "trading_value": 1234567890,
                    "timestamp": "2024-07-24T10:30:00"
                },
                ...
            ],
            "timestamp": "2024-07-24T10:30:00"
        }
    """
    # 최신 타임스탬프 조회
    async with container.store.conn.execute(
        "SELECT MAX(timestamp) FROM market_data"
    ) as cursor:
        latest = await cursor.fetchone()

    if not latest or not latest[0]:
        raise HTTPException(
            status_code=404,
            detail="마켓 데이터가 없습니다",
        )

    latest_timestamp = latest[0]

    # 정렬 쿼리 구성 (화이트리스트 사용)
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

    async with container.store.conn.execute(query, (latest_timestamp, limit)) as cursor:
        rows = await cursor.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="조회된 종목이 없습니다",
        )

    # 응답 구성
    data = [
        {
            "symbol": row[0],
            "price": row[1],
            "change_rate": row[2],
            "trading_volume": row[3],
            "trading_value": row[4],
            "timestamp": row[5],
        }
        for row in rows
    ]

    return {
        "data": data,
        "timestamp": latest_timestamp,
    }


@router.get("/market-stocks/summary")
async def get_market_summary(
    container: ContainerDep,
) -> dict:
    """마켓 데이터 요약 (TOP 5 각 카테고리)."""
    async with container.store.conn.execute(
        "SELECT MAX(timestamp) FROM market_data"
    ) as cursor:
        latest = await cursor.fetchone()

    if not latest or not latest[0]:
        raise HTTPException(
            status_code=404,
            detail="마켓 데이터가 없습니다",
        )

    latest_timestamp = latest[0]

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

    result = {
        "timestamp": latest_timestamp,
        "categories": {},
    }

    for key, (col, label) in categories.items():
        async with container.store.conn.execute(
            query_template.format(col),
            (latest_timestamp,),
        ) as cursor:
            rows = await cursor.fetchall()

        result["categories"][key] = {
            "label": label,
            "stocks": [
                {
                    "symbol": row[0],
                    "price": row[1],
                    "change_rate": row[2],
                    "trading_volume": row[3],
                    "trading_value": row[4],
                }
                for row in rows
            ],
        }

    return result
