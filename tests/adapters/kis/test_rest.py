"""KisRestClient — 현재가·잔고 REST 어댑터 테스트 (httpx mock 사용)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from core.adapters.kis.rest import BalanceInfo, KisRestClient, PriceInfo
from core.config.settings import Env, KisCredentials, Market

# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

DUMMY_CREDS = KisCredentials(
    app_key="testkey",
    app_secret="testsecret",  # type: ignore[arg-type]
    account_no="12345678",
    account_code="01",
    hts_id="test",
)


def _make_auth(env: Env = Env.VPS) -> MagicMock:
    auth = MagicMock()
    auth.env = env
    auth.credentials = DUMMY_CREDS
    token = MagicMock()
    token.token = "dummy_token"
    auth.get_access_token = AsyncMock(return_value=token)
    return auth


def _mock_response(data: dict) -> httpx.Response:
    resp = httpx.Response(200, json=data)
    resp.request = httpx.Request("GET", "https://openapivts.koreainvestment.com:29443/")
    return resp


# ---------------------------------------------------------------------------
# 현재가 조회 — 국내
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_domestic_price():
    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=_mock_response(
            {
                "rt_cd": "0",
                "output": {
                    "stck_prpr": "75000",
                    "stck_oprc": "74000",
                    "stck_hgpr": "76000",
                    "stck_lwpr": "73500",
                    "acml_vol": "1234567",
                },
            }
        )
    )

    client = KisRestClient(auth, env=Env.VPS, market=Market.DOMESTIC, http_client=mock_client)
    result = await client.get_price("005930")

    assert isinstance(result, PriceInfo)
    assert result.symbol == "005930"
    assert result.current_price == 75000.0
    assert result.volume == 1234567
    assert result.market == Market.DOMESTIC


@pytest.mark.asyncio
async def test_get_price_api_error():
    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=_mock_response({"rt_cd": "1", "msg1": "종목코드 오류"})
    )

    client = KisRestClient(auth, http_client=mock_client)
    with pytest.raises(RuntimeError, match="KIS API 오류"):
        await client.get_price("INVALID")


# ---------------------------------------------------------------------------
# 현재가 조회 — 해외
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_overseas_price():
    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=_mock_response(
            {
                "rt_cd": "0",
                "output": {
                    "last": "185.50",
                    "open": "183.00",
                    "high": "186.00",
                    "low": "182.50",
                    "tvol": "987654",
                },
            }
        )
    )

    client = KisRestClient(auth, env=Env.VPS, market=Market.OVERSEAS, http_client=mock_client)
    result = await client.get_price("AAPL")

    assert isinstance(result, PriceInfo)
    assert result.symbol == "AAPL"
    assert result.current_price == 185.50
    assert result.open_price == 183.00
    assert result.volume == 987654
    assert result.market == Market.OVERSEAS


@pytest.mark.asyncio
async def test_get_overseas_price_api_error():
    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=_mock_response({"rt_cd": "7", "msg1": "해외 종목 조회 실패"})
    )

    client = KisRestClient(auth, market=Market.OVERSEAS, http_client=mock_client)
    with pytest.raises(RuntimeError, match="KIS API 오류"):
        await client.get_price("INVALID")


# ---------------------------------------------------------------------------
# 잔고 조회 — 국내
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_domestic_balance():
    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=_mock_response(
            {
                "rt_cd": "0",
                "output1": [
                    {
                        "pdno": "005930",
                        "prdt_name": "삼성전자",
                        "hldg_qty": "10",
                        "pchs_avg_pric": "70000",
                        "prpr": "75000",
                        "evlu_amt": "750000",
                        "evlu_pfls_amt": "50000",
                        "evlu_pfls_rt": "7.14",
                    }
                ],
                "output2": [
                    {
                        "tot_evlu_amt": "1750000",
                        "evlu_pfls_smtl_amt": "50000",
                        "dnca_tot_amt": "1000000",
                    }
                ],
            }
        )
    )

    client = KisRestClient(auth, http_client=mock_client)
    result = await client.get_balance()

    assert isinstance(result, BalanceInfo)
    assert len(result.items) == 1
    assert result.items[0].symbol == "005930"
    assert result.items[0].qty == 10
    assert result.deposit == 1000000.0


@pytest.mark.asyncio
async def test_get_balance_skips_zero_qty():
    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=_mock_response(
            {
                "rt_cd": "0",
                "output1": [
                    {"pdno": "005930", "prdt_name": "삼성전자", "hldg_qty": "0"},
                ],
                "output2": [{}],
            }
        )
    )

    client = KisRestClient(auth, http_client=mock_client)
    result = await client.get_balance()
    assert result.items == []


# ---------------------------------------------------------------------------
# 잔고 조회 — 해외
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_overseas_balance():
    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=_mock_response(
            {
                "rt_cd": "0",
                "output1": [
                    {
                        "ovrs_pdno": "AAPL",
                        "ovrs_item_name": "Apple Inc",
                        "ovrs_cblc_qty": "5",
                        "pchs_avg_pric": "170.00",
                        "now_pric2": "185.50",
                        "ovrs_stck_evlu_amt": "927.50",
                        "frcr_evlu_pfls_amt": "77.50",
                        "evlu_pfls_rt": "9.12",
                    }
                ],
                "output2": {
                    "tot_evlu_amt": "1927.50",
                    "ovrs_tot_pfls": "77.50",
                    "frcr_dncl_amt_2": "1000.00",
                },
            }
        )
    )

    client = KisRestClient(auth, market=Market.OVERSEAS, http_client=mock_client)
    result = await client.get_balance()

    assert isinstance(result, BalanceInfo)
    assert len(result.items) == 1
    assert result.items[0].symbol == "AAPL"
    assert result.items[0].qty == 5
    assert result.items[0].current_price == 185.50
    assert result.deposit == 1000.00


@pytest.mark.asyncio
async def test_get_overseas_balance_skips_zero_qty():
    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=_mock_response(
            {
                "rt_cd": "0",
                "output1": [{"ovrs_pdno": "TSLA", "ovrs_cblc_qty": "0"}],
                "output2": {},
            }
        )
    )

    client = KisRestClient(auth, market=Market.OVERSEAS, http_client=mock_client)
    result = await client.get_balance()
    assert result.items == []


# ---------------------------------------------------------------------------
# T019: 매수/매도 주문 (국내)
# ---------------------------------------------------------------------------


def _post_mock_response(data: dict) -> httpx.Response:
    resp = httpx.Response(200, json=data)
    resp.request = httpx.Request("POST", "https://openapivts.koreainvestment.com:29443/")
    return resp


@pytest.mark.asyncio
async def test_place_domestic_buy_order():
    from core.config.settings import Env, Market
    from core.risk.models import Order, OrderSide, OrderType
    from core.strategy.base import Signal, SignalSide

    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        return_value=_post_mock_response({"rt_cd": "0", "output": {"ODNO": "0000123456"}})
    )

    client = KisRestClient(auth, env=Env.VPS, market=Market.DOMESTIC, http_client=mock_client)

    sig = Signal(strategy="test", symbol="005930", side=SignalSide.BUY, qty=5, price=75000.0)
    order = Order(
        symbol="005930",
        market=Market.DOMESTIC,
        env=Env.VPS,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        qty=5,
        price=75000.0,
        source_signal=sig,
    )

    ack = await client.place_order(order)

    assert ack.kis_order_id == "0000123456"
    assert ack.status == "submitted"
    assert ack.symbol == "005930"

    call_kwargs = mock_client.post.call_args
    sent_body = call_kwargs.kwargs["json"]
    assert sent_body["PDNO"] == "005930"
    assert sent_body["ORD_QTY"] == "5"
    assert sent_body["ORD_DVSN"] == "00"  # 지정가


@pytest.mark.asyncio
async def test_place_domestic_sell_order_market():
    from core.config.settings import Env, Market
    from core.risk.models import Order, OrderSide, OrderType
    from core.strategy.base import Signal, SignalSide

    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        return_value=_post_mock_response({"rt_cd": "0", "output": {"ODNO": "0000999999"}})
    )

    client = KisRestClient(auth, env=Env.VPS, market=Market.DOMESTIC, http_client=mock_client)

    sig = Signal(strategy="test", symbol="005930", side=SignalSide.SELL, qty=3, price=None)
    order = Order(
        symbol="005930",
        market=Market.DOMESTIC,
        env=Env.VPS,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        qty=3,
        price=0.0,
        source_signal=sig,
    )

    ack = await client.place_order(order)

    assert ack.kis_order_id == "0000999999"
    sent_body = mock_client.post.call_args.kwargs["json"]
    assert sent_body["ORD_DVSN"] == "01"  # 시장가
    assert sent_body["ORD_UNPR"] == "0"   # 시장가 가격은 0


@pytest.mark.asyncio
async def test_place_order_api_error_raises():
    from core.config.settings import Env, Market
    from core.risk.models import Order, OrderSide, OrderType
    from core.strategy.base import Signal, SignalSide

    auth = _make_auth()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        return_value=_post_mock_response({"rt_cd": "9", "msg1": "잔고 부족"})
    )

    client = KisRestClient(auth, env=Env.VPS, market=Market.DOMESTIC, http_client=mock_client)

    sig = Signal(strategy="test", symbol="005930", side=SignalSide.BUY, qty=1, price=100.0)
    order = Order(
        symbol="005930", market=Market.DOMESTIC, env=Env.VPS,
        side=OrderSide.BUY, order_type=OrderType.LIMIT, qty=1, price=100.0, source_signal=sig,
    )

    with pytest.raises(RuntimeError, match="KIS 주문 오류"):
        await client.place_order(order)
