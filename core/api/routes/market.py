"""GET /market-status, GET /risk-metrics — 마켓 상태 및 Risk 지표 조회."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from core.api.deps import ContainerDep
from core.api.models import MarketDayStatus, MarketStatus, RiskMetrics

logger = logging.getLogger(__name__)
router = APIRouter()


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
        logger.exception("KR 마켓 캘린더 조회 실패")
        markets.append(MarketDayStatus(market="KR", is_open=False, today_date=""))

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
        logger.exception("US 마켓 캘린더 조회 실패")
        markets.append(MarketDayStatus(market="US", is_open=False, today_date=""))

    return MarketStatus(markets=markets)


@router.get("/risk-metrics", response_model=RiskMetrics, summary="Risk 지표 조회")
async def get_risk_metrics(container: ContainerDep) -> RiskMetrics:
    """Risk Manager 현재 상태와 매수가능금액을 반환한다.

    매수가능금액은 Toss 브로커가 주입된 경우에만 반환된다.
    """
    halt_level = container.risk._halt.value  # type: ignore[attr-defined]
    daily_count = container.risk._daily_order_count  # type: ignore[attr-defined]

    buying_power: float | None = None
    buying_power_currency: str | None = None

    broker = container.broker
    if broker is not None:
        try:
            bp = await broker.get_buying_power("KRW")
            buying_power = float(bp.cash_buying_power)
            buying_power_currency = bp.currency
        except Exception:
            logger.warning("매수가능금액 조회 실패 — null로 반환")

    return RiskMetrics(
        halt_level=halt_level,
        daily_order_count=daily_count,
        buying_power=buying_power,
        buying_power_currency=buying_power_currency,
    )
