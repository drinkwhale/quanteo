"""KisRestClient — 현재가·잔고 REST 어댑터 테스트 (httpx mock 사용)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
# 현재가 조회
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
# 잔고 조회
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
