"""GET /market-status, GET /stock-names, GET /risk-metrics — 마켓·종목·Risk 지표 조회."""

from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from core.api.deps import ContainerDep
from core.api.models import (
    MarketDayStatus,
    MarketStatus,
    RiskMetrics,
    StockNameItem,
    StockNameList,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Toss Stock Info API 제약: 콤마 구분 최대 200건 (specs/tossinvest/stock-info.json)
MAX_STOCK_SYMBOLS = 200


@router.get("/market-status", response_model=MarketStatus, summary="마켓 개장 상태 조회")
async def get_market_status(container: ContainerDep) -> MarketStatus:
    """국내(KR)·해외(US) 마켓 개장 여부와 캘린더 정보를 반환한다.

    Toss 브로커 어댑터가 주입된 경우에만 실시간 정보를 반환한다.
    브로커가 없으면 503을 반환한다.
    """
    broker = container.broker
    if broker is None:
        raise HTTPException(
            status_code=503,
            detail="브로커 어댑터가 초기화되지 않았습니다. Toss 환경에서만 마켓 캘린더를 조회할 수 있습니다.",
        )

    markets: list[MarketDayStatus] = []

    try:
        kr_cal = await broker.get_market_calendar_kr()
        today = kr_cal.today
        markets.append(
            MarketDayStatus(
                market="KR",
                is_open=today.is_open,
                today_date=today.date,
                open_time=today.open_time,
                close_time=today.close_time,
            )
        )
    except Exception:
        logger.exception("KR 마켓 캘린더 조회 실패 — is_stale=True로 반환")
        markets.append(MarketDayStatus(market="KR", is_open=False, today_date="", is_stale=True))

    try:
        us_cal = await broker.get_market_calendar_us()
        today_us = us_cal.today
        markets.append(
            MarketDayStatus(
                market="US",
                is_open=today_us.is_open,
                today_date=today_us.date,
                open_time=today_us.regular_open,
                close_time=today_us.regular_close,
            )
        )
    except Exception:
        logger.exception("US 마켓 캘린더 조회 실패 — is_stale=True로 반환")
        markets.append(MarketDayStatus(market="US", is_open=False, today_date="", is_stale=True))

    return MarketStatus(markets=markets)


@router.get("/stock-names", response_model=StockNameList, summary="종목명 조회")
async def get_stock_names(
    container: ContainerDep,
    symbols: str = Query(..., description="콤마로 구분된 종목 심볼 목록 (예: 005930,AAPL)"),
) -> StockNameList:
    """종목 심볼에 대응하는 한글 종목명을 조회한다.

    Toss 브로커가 주입된 경우에만 조회 가능. 종목 참조 정보는 영업일 단위로
    갱신되므로 화면·세션 진입 시점에 한 번만 호출해 클라이언트에서 캐시해
    사용하기를 권장한다(짧은 주기 폴링 금지).
    """
    broker = container.broker
    if broker is None:
        raise HTTPException(
            status_code=503,
            detail="브로커 어댑터가 초기화되지 않았습니다. Toss 환경에서만 종목명을 조회할 수 있습니다.",
        )

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return StockNameList(items=[])

    if len(symbol_list) > MAX_STOCK_SYMBOLS:
        logger.warning(
            "종목명 조회 요청이 최대 건수(%d)를 초과해 %d건으로 잘랐습니다.",
            MAX_STOCK_SYMBOLS,
            MAX_STOCK_SYMBOLS,
        )
        symbol_list = symbol_list[:MAX_STOCK_SYMBOLS]

    try:
        stocks = await broker.get_stocks(symbol_list)
    except Exception as exc:
        logger.exception("종목명 조회 실패")
        raise HTTPException(status_code=502, detail="종목명 조회에 실패했습니다.") from exc

    return StockNameList(
        items=[StockNameItem(symbol=s.symbol, name=s.name, market=s.market) for s in stocks]
    )


@router.get("/risk-metrics", response_model=RiskMetrics, summary="Risk 지표 조회")
async def get_risk_metrics(container: ContainerDep) -> RiskMetrics:
    """Risk Manager 현재 상태와 매수가능금액을 반환한다.

    매수가능금액은 Toss 브로커가 주입된 경우에만 반환된다.
    """
    halt_level = container.risk._halt.value  # type: ignore[attr-defined]
    daily_count = container.risk._daily_order_count  # type: ignore[attr-defined]

    buying_power: Decimal | None = None
    buying_power_currency: str | None = None

    broker = container.broker
    if broker is not None:
        try:
            bp = await broker.get_buying_power("KRW")
            buying_power = bp.cash_buying_power
            buying_power_currency = bp.currency
        except Exception:
            logger.exception("매수가능금액 조회 실패 — null로 반환")

    return RiskMetrics(
        halt_level=halt_level,
        daily_order_count=daily_count,
        buying_power=buying_power,
        buying_power_currency=buying_power_currency,
    )
