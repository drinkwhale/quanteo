"""MarketDataFeed (REST 폴링) 테스트."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.adapters.kis.rest import PriceInfo
from core.config.settings import Market
from core.marketdata.feed import MarketDataFeed
from core.marketdata.models import Tick


def _make_rest_client(price: float = 75000.0) -> MagicMock:
    price_info = PriceInfo(
        symbol="005930",
        current_price=price,
        open_price=74000.0,
        high_price=76000.0,
        low_price=73000.0,
        volume=100000,
        market=Market.DOMESTIC,
        raw={},
    )
    client = MagicMock()
    client.get_price = AsyncMock(return_value=price_info)
    return client


# ---------------------------------------------------------------------------
# subscribe
# ---------------------------------------------------------------------------


def test_subscribe_adds_symbol():
    client = _make_rest_client()
    feed = MarketDataFeed(rest_client=client, poll_interval=0.1)

    feed.subscribe("005930")
    feed.subscribe("000660")

    assert "005930" in feed._symbols
    assert "000660" in feed._symbols


# ---------------------------------------------------------------------------
# 폴링 루프 — Tick 핸들러 호출 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_once_calls_tick_handler():
    client = _make_rest_client(price=75000.0)
    feed = MarketDataFeed(rest_client=client, poll_interval=0.05)
    feed.subscribe("005930")

    received: list[Tick] = []
    feed.on_tick(received.append)

    await feed._poll_once()

    assert len(received) == 1
    assert received[0].symbol == "005930"
    assert received[0].price == 75000.0


@pytest.mark.asyncio
async def test_run_calls_handler_at_least_twice():
    """폴링 루프가 interval 주기로 핸들러를 반복 호출하는지 검증."""
    client = _make_rest_client()
    feed = MarketDataFeed(rest_client=client, poll_interval=0.05)
    feed.subscribe("005930")

    received: list[Tick] = []
    feed.on_tick(received.append)

    async def _run_then_stop() -> None:
        await asyncio.sleep(0.15)
        await feed.stop()

    await asyncio.gather(feed.run(), _run_then_stop())

    assert len(received) >= 2


@pytest.mark.asyncio
async def test_run_stops_cleanly():
    client = _make_rest_client()
    feed = MarketDataFeed(rest_client=client, poll_interval=0.05)
    feed.subscribe("005930")
    feed.on_tick(lambda t: None)

    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0.1)
    await feed.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert not feed._running


@pytest.mark.asyncio
async def test_poll_error_does_not_crash_loop():
    """개별 종목 조회 오류가 발생해도 루프가 멈추지 않아야 한다."""
    client = MagicMock()
    client.get_price = AsyncMock(side_effect=RuntimeError("API 오류"))

    feed = MarketDataFeed(rest_client=client, poll_interval=0.05)
    feed.subscribe("BADTICKER")
    feed.on_tick(lambda t: None)

    # 오류 발생해도 TimeoutError 없이 정상 종료
    async def _stop() -> None:
        await asyncio.sleep(0.15)
        await feed.stop()

    await asyncio.gather(feed.run(), _stop())
