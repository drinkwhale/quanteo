"""TossRestClient Phase 9 확장 기능 테스트.

T049 — 매수가능금액·판매가능수량·수수료
T050 — 주문 목록·단건·취소·정정
T051 — 체결 내역
T052 — 상하한가·마켓 캘린더·개장 여부
T053 — 종목 정보·유의사항
T054 — 환율
T055 — 과거 캔들
"""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.adapters.kis.throttler import FixedIntervalThrottler, ThrottlerConfig
from core.adapters.toss.auth import OAuth2Token, TossAuth
from core.adapters.toss.rest import TossRestClient


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

_FAST = ThrottlerConfig(calls_per_second=1000.0)


def _make_auth() -> TossAuth:
    auth = MagicMock(spec=TossAuth)
    token = OAuth2Token(
        access_token="tok",
        token_type="Bearer",
        expires_in=3600,
        issued_at=time.time(),
    )
    auth.get_access_token = AsyncMock(return_value=token)
    auth.refresh_on_401 = AsyncMock(return_value=token)
    return auth


def _resp(body: dict, status: int = 200) -> httpx.Response:
    resp = httpx.Response(status, json=body)
    resp.request = httpx.Request("GET", "https://openapi.tossinvest.com/")
    return resp


def _make_client(body: dict, status: int = 200) -> TossRestClient:
    """단일 응답 body를 반환하는 TossRestClient를 생성한다.

    _do_request는 self._http_client.request()를 await로 호출하므로
    http 객체의 .request 속성을 AsyncMock으로 설정해야 한다.
    """
    http = MagicMock()
    http.request = AsyncMock(return_value=_resp(body, status))
    fast = FixedIntervalThrottler(_FAST)
    client = TossRestClient(
        auth=_make_auth(),
        http_client=http,
        market_throttler=fast,
        order_throttler=fast,
    )
    client._account_seq = "12345"
    return client


def _make_client_multi(responses: list[dict]) -> TossRestClient:
    """순차적으로 다른 응답을 반환하는 TossRestClient를 생성한다."""
    http = MagicMock()
    http.request = AsyncMock(side_effect=[_resp(b) for b in responses])
    fast = FixedIntervalThrottler(_FAST)
    client = TossRestClient(
        auth=_make_auth(),
        http_client=http,
        market_throttler=fast,
        order_throttler=fast,
    )
    client._account_seq = "12345"
    return client


# ---------------------------------------------------------------------------
# T049 — 매수가능금액
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_buying_power_returns_decimal():
    client = _make_client({"result": {"currency": "KRW", "cashBuyingPower": "3500000"}})

    info = await client.get_buying_power("KRW")

    assert info.currency == "KRW"
    assert info.cash_buying_power == Decimal("3500000")


# ---------------------------------------------------------------------------
# T049 — 판매가능수량
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sellable_quantity_returns_int():
    client = _make_client({"result": {"sellableQuantity": "42"}})

    qty = await client.get_sellable_quantity("005930")

    assert qty == 42


@pytest.mark.asyncio
async def test_get_sellable_quantity_fractional_truncates():
    client = _make_client({"result": {"sellableQuantity": "10.5"}})

    qty = await client.get_sellable_quantity("AAPL")

    assert qty == 10


# ---------------------------------------------------------------------------
# T049 — 수수료
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_commissions_parses_list():
    body = {
        "result": [
            {"marketCountry": "KR", "commissionRate": "0.015", "startDate": "2026-01-01", "endDate": None},
            {"marketCountry": "US", "commissionRate": "0.020"},
        ]
    }
    client = _make_client(body)

    commissions = await client.get_commissions()

    assert len(commissions) == 2
    assert commissions[0].market_country == "KR"
    assert commissions[0].commission_rate == Decimal("0.015")
    assert commissions[0].start_date == "2026-01-01"
    assert commissions[1].market_country == "US"
    assert commissions[1].commission_rate == Decimal("0.020")


# ---------------------------------------------------------------------------
# T050 — 주문 목록
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_orders_returns_toss_orders_and_cursor():
    order_raw = {
        "orderId": "ord001",
        "symbol": "005930",
        "side": "BUY",
        "orderType": "LIMIT",
        "timeInForce": "DAY",
        "status": "PENDING",
        "quantity": "10",
        "price": "72000",
        "currency": "KRW",
        "orderedAt": "2026-06-29T10:00:00+09:00",
        "execution": {"filledQuantity": "0"},
    }
    body = {"result": {"orders": [order_raw], "hasNext": True, "nextCursor": "cursor_abc"}}
    client = _make_client(body)

    orders, cursor = await client.list_orders("OPEN")

    assert len(orders) == 1
    assert orders[0].order_id == "ord001"
    assert orders[0].symbol == "005930"
    assert orders[0].side == "BUY"
    assert orders[0].quantity == 10
    assert orders[0].price == Decimal("72000")
    assert cursor == "cursor_abc"


@pytest.mark.asyncio
async def test_list_orders_no_next_page_returns_none_cursor():
    body = {"result": {"orders": [], "hasNext": False}}
    client = _make_client(body)

    _, cursor = await client.list_orders("CLOSED")

    assert cursor is None


# ---------------------------------------------------------------------------
# T050 — 주문 취소
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_order_returns_operation_response():
    client = _make_client({"result": {"orderId": "cancel_ord_001"}})

    resp = await client.cancel_order("ord001")

    assert resp.order_id == "cancel_ord_001"


@pytest.mark.asyncio
async def test_cancel_order_409_falls_back_to_get_order():
    """409 TossConflictError 시 get_order로 재조회해 orderId를 반환한다."""
    from core.adapters.toss.rest import TossConflictError

    client = _make_client({})

    with patch.object(client, "_request_order", side_effect=TossConflictError("409 충돌")):
        with patch.object(client, "get_order", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = type("O", (), {"order_id": "fallback_id"})()
            resp = await client.cancel_order("ord001")
            assert resp.order_id == "fallback_id"
            mock_get.assert_awaited_once_with("ord001")


# ---------------------------------------------------------------------------
# T050 — 주문 정정
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_modify_order_sends_correct_body():
    captured: list[dict] = []

    async def _fake_request_order(method: str, path: str, *, params=None, json=None) -> dict:
        captured.append({"method": method, "path": path, "json": json})
        return {"result": {"orderId": "mod_ord_001"}}

    client = _make_client({})
    client._request_order = _fake_request_order  # type: ignore

    resp = await client.modify_order(
        "ord001", order_type="LIMIT", quantity=5, price=Decimal("71000")
    )

    assert resp.order_id == "mod_ord_001"
    assert captured[0]["json"]["orderType"] == "LIMIT"
    assert captured[0]["json"]["quantity"] == 5
    assert captured[0]["json"]["price"] == "71000"


# ---------------------------------------------------------------------------
# T051 — 체결 내역
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_trades_parses_fills():
    body = {
        "result": [
            {"price": "72000", "volume": "10", "timestamp": "2026-06-29T10:30:00+09:00", "currency": "KRW"},
            {"price": "72100", "volume": "5", "timestamp": "2026-06-29T10:31:00+09:00", "currency": "KRW"},
        ]
    }
    client = _make_client(body)

    fills = await client.get_trades(count=10)

    assert len(fills) == 2
    assert fills[0].price == Decimal("72000")
    assert fills[0].volume == 10
    assert fills[1].volume == 5


# ---------------------------------------------------------------------------
# T052 — 상하한가
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_price_limits_parses_correctly():
    body = {
        "result": {
            "timestamp": "2026-06-29T09:00:00+09:00",
            "upperLimitPrice": "93000",
            "lowerLimitPrice": "50400",
            "currency": "KRW",
        }
    }
    client = _make_client(body)

    limits = await client.get_price_limits("005930")

    assert limits.symbol == "005930"
    assert limits.upper_limit_price == Decimal("93000")
    assert limits.lower_limit_price == Decimal("50400")
    assert limits.currency == "KRW"


@pytest.mark.asyncio
async def test_get_price_limits_no_limit_market_returns_none():
    """미국 주식처럼 가격제한이 없는 시장은 None을 반환한다."""
    client = _make_client({"result": {"timestamp": "2026-06-29T09:00:00Z", "currency": "USD"}})

    limits = await client.get_price_limits("AAPL")

    assert limits.upper_limit_price is None
    assert limits.lower_limit_price is None


# ---------------------------------------------------------------------------
# T052 — 마켓 캘린더 & 개장 여부
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_market_calendar_kr_is_open():
    body = {
        "result": {
            "today": {"date": "2026-06-29", "integrated": {"open": "09:00", "close": "15:30"}},
            "previousBusinessDay": {"date": "2026-06-26", "integrated": {"open": "09:00", "close": "15:30"}},
            "nextBusinessDay": {"date": "2026-06-30", "integrated": None},
        }
    }
    client = _make_client(body)

    cal = await client.get_market_calendar_kr()

    assert cal.today.is_open is True
    assert cal.today.date == "2026-06-29"
    assert cal.today.open_time == "09:00"


@pytest.mark.asyncio
async def test_get_market_calendar_kr_closed_day():
    body = {
        "result": {
            "today": {"date": "2026-06-28", "integrated": None},
            "previousBusinessDay": {"date": "2026-06-26", "integrated": None},
            "nextBusinessDay": {"date": "2026-06-29", "integrated": None},
        }
    }
    client = _make_client(body)

    cal = await client.get_market_calendar_kr()

    assert cal.today.is_open is False


@pytest.mark.asyncio
async def test_is_market_open_kr_returns_bool():
    body = {
        "result": {
            "today": {"date": "2026-06-29", "integrated": {"open": "09:00", "close": "15:30"}},
            "previousBusinessDay": {"date": "2026-06-26", "integrated": None},
            "nextBusinessDay": {"date": "2026-06-30", "integrated": None},
        }
    }
    client = _make_client(body)

    result = await client.is_market_open("KR")

    assert result is True


# ---------------------------------------------------------------------------
# T053 — 종목 정보
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stocks_parses_stock_info():
    body = {
        "result": [
            {
                "symbol": "005930",
                "name": "삼성전자",
                "englishName": "SamsungElec",
                "isinCode": "KR7005930003",
                "market": "KOSPI",
                "securityType": "STOCK",
                "isCommonShare": True,
                "status": "NORMAL",
                "currency": "KRW",
                "sharesOutstanding": "5969782550",
            }
        ]
    }
    client = _make_client(body)

    stocks = await client.get_stocks(["005930"])

    assert len(stocks) == 1
    assert stocks[0].symbol == "005930"
    assert stocks[0].name == "삼성전자"
    assert stocks[0].market == "KOSPI"
    assert stocks[0].currency == "KRW"
    assert stocks[0].is_common_share is True


@pytest.mark.asyncio
async def test_get_stock_warnings_returns_warning_list():
    body = {
        "result": [
            {"warningType": "INVESTMENT_WARNING", "startDate": "2026-06-01", "endDate": None},
        ]
    }
    client = _make_client(body)

    warnings = await client.get_stock_warnings("005930")

    assert len(warnings) == 1
    assert warnings[0].warning_type == "INVESTMENT_WARNING"
    assert warnings[0].start_date == "2026-06-01"


@pytest.mark.asyncio
async def test_get_stock_warnings_empty_when_no_warnings():
    client = _make_client({"result": []})

    warnings = await client.get_stock_warnings("005930")

    assert warnings == []


# ---------------------------------------------------------------------------
# T054 — 환율
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_exchange_rate_parses_correctly():
    body = {
        "result": {
            "baseCurrency": "USD",
            "quoteCurrency": "KRW",
            "rate": "1380.5",
            "midRate": "1375.0",
            "basisPoint": "5.5",
            "rateChangeType": "RISE",
            "validFrom": "2026-06-29T09:00:00+09:00",
            "validUntil": "2026-06-29T18:00:00+09:00",
        }
    }
    client = _make_client(body)
    client.__class__._exchange_rate_cache = {}

    rate = await client.get_exchange_rate("USD", "KRW")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == Decimal("1380.5")
    assert rate.mid_rate == Decimal("1375.0")
    assert rate.rate_change_type == "RISE"


@pytest.mark.asyncio
async def test_get_exchange_rate_uses_cache_on_second_call():
    """두 번째 호출은 캐시에서 반환하며 HTTP 요청을 1회만 발생시킨다."""
    body = {
        "result": {
            "baseCurrency": "USD",
            "quoteCurrency": "KRW",
            "rate": "1380.5",
            "midRate": "1375.0",
            "basisPoint": "5.5",
            "rateChangeType": "RISE",
            "validFrom": "2026-06-29T09:00:00+09:00",
            "validUntil": "2026-06-29T18:00:00+09:00",
        }
    }
    client = _make_client(body)
    client.__class__._exchange_rate_cache = {}

    await client.get_exchange_rate("USD", "KRW")
    await client.get_exchange_rate("USD", "KRW")

    # http.request는 캐시 덕분에 1회만 호출
    assert client._http_client.request.call_count == 1  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# T055 — 과거 캔들
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_candles_parses_candle_list():
    body = {
        "result": {
            "candles": [
                {
                    "timestamp": "2026-06-28T09:00:00+09:00",
                    "openPrice": "71600",
                    "highPrice": "72300",
                    "lowPrice": "71500",
                    "closePrice": "72100",
                    "volume": "1000000",
                    "currency": "KRW",
                },
                {
                    "timestamp": "2026-06-29T09:00:00+09:00",
                    "openPrice": "72100",
                    "highPrice": "72800",
                    "lowPrice": "71900",
                    "closePrice": "72500",
                    "volume": "1200000",
                    "currency": "KRW",
                },
            ]
        }
    }
    client = _make_client(body)

    candles = await client.get_candles("005930", "1d", count=2)

    assert len(candles) == 2
    assert candles[0].open_price == Decimal("71600")
    assert candles[0].close_price == Decimal("72100")
    assert candles[0].volume == 1_000_000
    assert candles[1].close_price == Decimal("72500")


# ---------------------------------------------------------------------------
# normalizer — normalize_toss_trade / normalize_toss_candle
# ---------------------------------------------------------------------------


def test_normalize_toss_trade():
    from core.marketdata.normalizer import normalize_toss_trade

    result = {
        "price": "72000",
        "volume": "10",
        "timestamp": "2026-06-29T10:30:00+09:00",
        "currency": "KRW",
        "symbol": "005930",
    }
    fill = normalize_toss_trade("005930", result)
    assert fill.symbol == "005930"
    assert fill.price == Decimal("72000")
    assert fill.volume == 10
    assert fill.currency == "KRW"


def test_normalize_toss_candle_domestic():
    from core.marketdata.normalizer import normalize_toss_candle

    result = {
        "timestamp": "2026-06-29T09:00:00+09:00",
        "openPrice": "71600",
        "highPrice": "72300",
        "lowPrice": "71500",
        "closePrice": "72100",
        "volume": "1000000",
        "currency": "KRW",
    }
    candle = normalize_toss_candle("005930", result, interval="1d")
    assert candle.symbol == "005930"
    assert candle.open == 71600.0
    assert candle.close == 72100.0
    assert candle.market == "domestic"
    assert candle.interval == "1d"


def test_normalize_toss_candle_overseas():
    from core.marketdata.normalizer import normalize_toss_candle

    result = {
        "timestamp": "2026-06-29T09:00:00Z",
        "openPrice": "180.5",
        "highPrice": "182.0",
        "lowPrice": "180.0",
        "closePrice": "181.5",
        "volume": "5000",
        "currency": "USD",
    }
    candle = normalize_toss_candle("AAPL", result, interval="1m")
    assert candle.market == "overseas"
    assert candle.interval == "1m"


# ---------------------------------------------------------------------------
# T050 — place_order 추가 커버리지
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_place_order_limit_buy():
    """LIMIT 매수 주문을 Toss에 전송하고 OrderAck을 반환한다."""
    from core.risk.models import OrderSide, OrderType

    order = MagicMock()
    order.client_order_id = "cl-001"
    order.symbol = "005930"
    order.qty = 10
    order.price = Decimal("72000")
    order.side = OrderSide.BUY
    order.order_type = OrderType.LIMIT

    body = {"result": {"orderId": "toss-order-001"}}
    client = _make_client(body)
    ack = await client.place_order(order)

    assert ack.broker_order_id == "toss-order-001"
    assert ack.client_order_id == "cl-001"
    assert ack.symbol == "005930"
    assert ack.status == "submitted"


@pytest.mark.asyncio
async def test_place_order_missing_order_id_raises():
    """Toss 응답에 orderId가 없으면 RuntimeError가 발생한다."""
    from core.risk.models import OrderSide, OrderType

    order = MagicMock()
    order.client_order_id = "cl-002"
    order.symbol = "005930"
    order.qty = 5
    order.price = Decimal("0")
    order.side = OrderSide.BUY
    order.order_type = OrderType.MARKET

    body = {"result": {}}  # orderId 없음
    client = _make_client(body)
    with pytest.raises(RuntimeError, match="orderId"):
        await client.place_order(order)


@pytest.mark.asyncio
async def test_cancel_order_409_fallback():
    """409 TossConflictError 발생 시 get_order로 재조회해 OrderOperationResponse를 반환한다."""
    from core.adapters.toss.rest import TossConflictError  # noqa: F401

    conflict_resp = httpx.Response(409, json={"error": {"code": "request-in-progress"}})
    conflict_resp.request = httpx.Request("POST", "https://openapi.tossinvest.com/")

    order_body = {
        "result": {
            "orderId": "toss-001",
            "status": "PENDING",
            "symbol": "005930",
            "side": "BUY",
            "orderType": "LIMIT",
            "quantity": 10,
            "price": "72000",
            "orderedAt": "2026-06-29T09:00:00Z",
            "execution": {},
        }
    }
    order_resp = _resp(order_body)

    http = MagicMock()
    http.request = AsyncMock(side_effect=[conflict_resp, order_resp])
    fast = FixedIntervalThrottler(_FAST)
    client = TossRestClient(
        auth=_make_auth(),
        http_client=http,
        market_throttler=fast,
        order_throttler=fast,
    )
    client._account_seq = "12345"

    result = await client.cancel_order("toss-001")
    assert result.order_id == "toss-001"
