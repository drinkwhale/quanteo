"""TossRestClient — 현재가·잔고·주문 테스트 (httpx mock 사용)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from core.adapters.toss.auth import OAuth2Token, TossAuth
from core.adapters.toss.rest import TossRestClient
from core.adapters.throttler import FixedIntervalThrottler, ThrottlerConfig
from core.config.settings import TossCredentials
from core.config.settings import Market
from core.risk.models import Order, OrderSide, OrderType
from core.strategy.base import Signal, SignalSide


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

DUMMY_CREDS = TossCredentials(
    client_id="test-client",
    client_secret="test-secret",  # type: ignore[arg-type]
)

_FAST_THROTTLER_CONFIG = ThrottlerConfig(calls_per_second=1000.0)


def _make_auth() -> TossAuth:
    auth = MagicMock(spec=TossAuth)
    token = OAuth2Token(
        access_token="test_token",
        token_type="Bearer",
        expires_in=3600,
        issued_at=time.time(),
    )
    auth.get_access_token = AsyncMock(return_value=token)
    auth.refresh_on_401 = AsyncMock(return_value=token)
    return auth


def _make_client(http_client: AsyncMock) -> TossRestClient:
    fast = FixedIntervalThrottler(_FAST_THROTTLER_CONFIG)
    return TossRestClient(
        auth=_make_auth(),
        http_client=http_client,
        market_throttler=fast,
        order_throttler=fast,
    )


def _mock_resp(status: int, body: dict) -> httpx.Response:
    resp = httpx.Response(status, json=body)
    resp.request = httpx.Request("GET", "https://openapi.tossinvest.com/")
    return resp


# ---------------------------------------------------------------------------
# initialize — accountSeq 획득
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_sets_account_seq():
    http = AsyncMock()
    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": [{"accountSeq": 42, "accountName": "주식계좌"}]
    }))
    client = _make_client(http)
    await client.initialize()
    assert client._account_seq == "42"


@pytest.mark.asyncio
async def test_initialize_raises_when_no_accounts():
    http = AsyncMock()
    http.request = AsyncMock(return_value=_mock_resp(200, {"result": []}))
    client = _make_client(http)
    with pytest.raises(RuntimeError, match="계좌 목록이 비어있습니다"):
        await client.initialize()


# ---------------------------------------------------------------------------
# get_price
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_price_returns_price_info():
    http = AsyncMock()
    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": [{
            "symbol": "005930",
            "lastPrice": "75000",
            "openPrice": "74000",
            "highPrice": "76000",
            "lowPrice": "73500",
            "volume": "123456",
            "marketCountry": "KR",
        }]
    }))
    client = _make_client(http)

    price = await client.get_price("005930")

    assert price.symbol == "005930"
    assert price.current_price == 75000.0
    assert price.volume == 123456


@pytest.mark.asyncio
async def test_get_price_raises_when_empty_result():
    http = AsyncMock()
    http.request = AsyncMock(return_value=_mock_resp(200, {"result": []}))
    client = _make_client(http)
    with pytest.raises(RuntimeError, match="현재가 조회 결과 없음"):
        await client.get_price("999999")


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------


def _holding_item(
    symbol: str,
    name: str,
    qty: str,
    avg_price: str,
    last_price: str,
    market_value: str,
    profit_loss: str,
    profit_loss_rate: str,
    country: str = "KR",
) -> dict:
    """specs/tossinvest/asset.json #HoldingsItem 형태의 mock 항목 (실제 API 응답 shape)."""
    return {
        "symbol": symbol,
        "name": name,
        "marketCountry": country,
        "currency": "KRW" if country == "KR" else "USD",
        "quantity": qty,
        "lastPrice": last_price,
        "averagePurchasePrice": avg_price,
        "marketValue": {"purchaseAmount": avg_price, "amount": market_value, "amountAfterCost": market_value},
        "profitLoss": {
            "amount": profit_loss,
            "amountAfterCost": profit_loss,
            "rate": profit_loss_rate,
            "rateAfterCost": profit_loss_rate,
        },
    }


@pytest.mark.asyncio
async def test_get_balance_returns_balance_info():
    http = AsyncMock()
    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": [{"accountSeq": 1}]
    }))
    client = _make_client(http)
    await client.initialize()

    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": {
            "totalPurchaseAmount": {"krw": "700000", "usd": None},
            "marketValue": {"amount": {"krw": "750000", "usd": None}, "amountAfterCost": {"krw": "750000", "usd": None}},
            "profitLoss": {
                "amount": {"krw": "50000", "usd": None},
                "amountAfterCost": {"krw": "50000", "usd": None},
                "rate": "0.0714",
                "rateAfterCost": "0.0714",
            },
            "dailyProfitLoss": {"amount": {"krw": "0", "usd": None}, "rate": "0"},
            "items": [
                _holding_item("005930", "삼성전자", "10", "70000", "75000", "750000", "50000", "0.0714"),
            ],
        }
    }))

    balance = await client.get_balance()

    assert len(balance.items) == 1
    assert balance.items[0].symbol == "005930"
    assert balance.items[0].qty == 10
    assert balance.items[0].current_price == 75000.0
    assert balance.items[0].eval_amount == 750000.0
    assert balance.items[0].profit_loss == 50000.0
    assert balance.items[0].market == Market.DOMESTIC
    assert balance.total_eval_amount == 750000.0
    assert balance.total_profit_loss == 50000.0
    # holdings 응답에는 예수금이 없다 — 별도 API 연동 전까지 0 고정
    assert balance.deposit == 0.0


@pytest.mark.asyncio
async def test_get_balance_filters_by_symbol():
    http = AsyncMock()
    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": [{"accountSeq": 1}]
    }))
    client = _make_client(http)
    await client.initialize()

    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": {
            "totalPurchaseAmount": {"krw": "0", "usd": None},
            "marketValue": {"amount": {"krw": "0", "usd": None}, "amountAfterCost": {"krw": "0", "usd": None}},
            "profitLoss": {
                "amount": {"krw": "0", "usd": None},
                "amountAfterCost": {"krw": "0", "usd": None},
                "rate": "0",
                "rateAfterCost": "0",
            },
            "dailyProfitLoss": {"amount": {"krw": "0", "usd": None}, "rate": "0"},
            "items": [
                _holding_item("005930", "삼성전자", "10", "70000", "75000", "750000", "0", "0"),
                _holding_item("000660", "SK하이닉스", "5", "100000", "110000", "550000", "0", "0"),
            ],
        }
    }))

    balance = await client.get_balance(symbol="005930")
    assert len(balance.items) == 1
    assert balance.items[0].symbol == "005930"


@pytest.mark.asyncio
async def test_get_balance_maps_us_market_country_to_overseas():
    http = AsyncMock()
    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": [{"accountSeq": 1}]
    }))
    client = _make_client(http)
    await client.initialize()

    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": {
            "totalPurchaseAmount": {"krw": "0", "usd": "1553"},
            "marketValue": {"amount": {"krw": "0", "usd": "1785"}, "amountAfterCost": {"krw": "0", "usd": "1771.43"}},
            "profitLoss": {
                "amount": {"krw": "0", "usd": "232"},
                "amountAfterCost": {"krw": "0", "usd": "218.43"},
                "rate": "0.1494",
                "rateAfterCost": "0.1406",
            },
            "dailyProfitLoss": {"amount": {"krw": "0", "usd": "25"}, "rate": "0.0141"},
            "items": [
                _holding_item("AAPL", "Apple", "10", "155.3", "178.5", "1785", "232", "0.1494", country="US"),
            ],
        }
    }))

    balance = await client.get_balance()
    assert balance.items[0].market == Market.OVERSEAS


# ---------------------------------------------------------------------------
# place_order
# ---------------------------------------------------------------------------


def _make_order(side: OrderSide = OrderSide.BUY) -> Order:
    sig_side = SignalSide.BUY if side == OrderSide.BUY else SignalSide.SELL
    signal = Signal(
        strategy="test",
        symbol="005930",
        side=sig_side,
        qty=10,
        price=75000.0,
    )
    return Order(
        symbol="005930",
        market=Market.DOMESTIC,
        side=side,
        order_type=OrderType.LIMIT,
        qty=10,
        price=75000.0,
        source_signal=signal,
        client_order_id="test-uuid-1234",
    )


@pytest.mark.asyncio
async def test_place_order_returns_order_ack():
    http = AsyncMock()
    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": [{"accountSeq": 1}]
    }))
    client = _make_client(http)
    await client.initialize()

    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": {"orderId": "toss-order-789", "status": "PENDING"}
    }))

    order = _make_order()
    ack = await client.place_order(order)

    assert ack.broker_order_id == "toss-order-789"
    assert ack.client_order_id == "test-uuid-1234"
    assert ack.status == "submitted"


@pytest.mark.asyncio
async def test_place_order_request_includes_client_order_id():
    http = AsyncMock()
    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": [{"accountSeq": 1}]
    }))
    client = _make_client(http)
    await client.initialize()

    http.request = AsyncMock(return_value=_mock_resp(200, {
        "result": {"orderId": "order-xyz"}
    }))

    await client.place_order(_make_order())

    call_kwargs = http.request.call_args.kwargs
    sent_body = call_kwargs.get("json", {})
    assert sent_body.get("clientOrderId") == "test-uuid-1234"
    assert sent_body.get("side") == "BUY"
    assert sent_body.get("quantity") == 10


# ---------------------------------------------------------------------------
# Rate Limit 그룹 격리 검증
# ---------------------------------------------------------------------------


def test_market_and_order_throttlers_are_separate():
    """MARKET_DATA와 ORDER 스로틀러가 별도 인스턴스임을 확인한다."""
    client = TossRestClient(auth=_make_auth())
    assert client._market_throttler is not client._order_throttler


# ---------------------------------------------------------------------------
# 401 재시도 경로 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_price_retries_on_401_and_succeeds():
    """401 수신 시 refresh_on_401() 호출 후 재시도해 성공한다."""
    new_token = OAuth2Token(
        access_token="new_token_after_refresh",
        token_type="Bearer",
        expires_in=3600,
        issued_at=time.time(),
    )
    auth = MagicMock(spec=TossAuth)
    auth.get_access_token = AsyncMock(return_value=OAuth2Token(
        access_token="old_token", token_type="Bearer", expires_in=3600, issued_at=time.time(),
    ))
    auth.refresh_on_401 = AsyncMock(return_value=new_token)

    # 첫 번째 요청 401, 두 번째 요청 200 성공
    resp_401 = httpx.Response(401, json={"error": "unauthorized"})
    resp_401.request = httpx.Request("GET", "https://openapi.tossinvest.com/")
    resp_200 = _mock_resp(200, {
        "result": [{
            "symbol": "005930",
            "lastPrice": "75000",
            "openPrice": "74000",
            "highPrice": "76000",
            "lowPrice": "73500",
            "volume": "123456",
            "marketCountry": "KR",
        }]
    })

    http = AsyncMock()
    http.request = AsyncMock(side_effect=[resp_401, resp_200])

    fast = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0))
    client = TossRestClient(auth=auth, http_client=http, market_throttler=fast, order_throttler=fast)

    price = await client.get_price("005930")

    assert price.current_price == 75000.0
    auth.refresh_on_401.assert_called_once()
    assert http.request.call_count == 2  # 첫 401 + 재시도


@pytest.mark.asyncio
async def test_get_price_raises_after_two_consecutive_401():
    """401이 두 번 연속 오면 RuntimeError를 발생시켜야 한다."""
    auth = MagicMock(spec=TossAuth)
    auth.get_access_token = AsyncMock(return_value=OAuth2Token(
        access_token="token", token_type="Bearer", expires_in=3600, issued_at=time.time(),
    ))
    auth.refresh_on_401 = AsyncMock(return_value=OAuth2Token(
        access_token="new_token", token_type="Bearer", expires_in=3600, issued_at=time.time(),
    ))

    resp_401 = httpx.Response(401, json={})
    resp_401.request = httpx.Request("GET", "https://openapi.tossinvest.com/")

    http = AsyncMock()
    http.request = AsyncMock(return_value=resp_401)

    fast = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0))
    client = TossRestClient(auth=auth, http_client=http, market_throttler=fast, order_throttler=fast)

    with pytest.raises(RuntimeError, match="401"):
        await client.get_price("005930")


@pytest.mark.asyncio
async def test_place_order_raises_when_order_id_missing():
    """Toss 응답에 orderId가 없으면 RuntimeError를 발생시켜야 한다."""
    http = AsyncMock()
    http.request = AsyncMock(return_value=_mock_resp(200, {"result": [{"accountSeq": 1}]}))
    client = _make_client(http)
    await client.initialize()

    # orderId 없는 응답
    http.request = AsyncMock(return_value=_mock_resp(200, {"result": {}}))

    with pytest.raises(RuntimeError, match="orderId"):
        await client.place_order(_make_order())
