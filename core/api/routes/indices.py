"""GET /indices — 코스피·코스닥·나스닥 등 주요 지수 시세 조회 (외부 소스)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from core.api.models import IndexQuoteItem, IndexQuoteResponse
from core.marketdata.index_quotes import get_index_quotes

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/indices", response_model=IndexQuoteResponse, summary="주요 지수 시세 조회")
async def get_indices() -> IndexQuoteResponse:
    """코스피·코스닥·나스닥 지수 시세를 조회한다.

    Toss 브로커 주입 여부와 무관하게 항상 호출 가능하다 — Toss Open API에는
    지수 엔드포인트가 없어 외부 소스(Yahoo Finance 공개 API)에서 가져온다.
    30초 캐시가 있어 폴링해도 외부 API를 매번 호출하지 않는다.
    """
    try:
        quotes = await get_index_quotes()
    except Exception as exc:
        logger.exception("지수 시세 조회 실패")
        raise HTTPException(status_code=502, detail="지수 시세 조회에 실패했습니다.") from exc

    return IndexQuoteResponse(
        items=[
            IndexQuoteItem(
                key=q.key,
                label=q.label,
                price=q.price,
                change=q.change,
                change_rate=q.change_rate,
                currency=q.currency,
            )
            for q in quotes
        ]
    )
