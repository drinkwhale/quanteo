"""KisQuoteClient — 전일 종가(stck_sdpr) 조회 전용 읽기 클라이언트 테스트.

배경: Toss 캔들 API의 종가 데이터가 실제 KIS/네이버 시세와 어긋나는 사례가
확인됐다(SK하이닉스 실측: Toss 2,253,000원 vs KIS·네이버 2,186,000원).
day_change 계산의 전일 종가만 KIS 실시간 시세 조회로 대체한다.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from core.adapters.kis.quote_client import KisQuoteClient


def _token_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"access_token": "test-token-abc", "token_type": "Bearer", "expires_in": 86400},
    )


def _quote_response(stck_sdpr: str = "2186000") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "output": {"stck_sdpr": stck_sdpr, "stck_prpr": "2265000"},
            "rt_cd": "0",
            "msg_cd": "MCA00000",
            "msg1": "정상처리 되었습니다.",
        },
    )


@pytest.fixture
def client_factory():
    def _make(handler):
        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        return KisQuoteClient(
            app_key="test-app-key",
            app_secret="test-app-secret",
            http_client=http_client,
        )

    return _make


@pytest.mark.asyncio
async def test_get_prev_close_returns_stck_sdpr(client_factory) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if "tokenP" in request.url.path:
            return _token_response(request)
        return _quote_response("2186000")

    client = client_factory(handler)

    result = await client.get_prev_close("000660")

    assert result == Decimal("2186000")
    assert any("tokenP" in p for p in calls)
    assert any("inquire-price" in p for p in calls)


@pytest.mark.asyncio
async def test_get_prev_close_reuses_cached_token(client_factory) -> None:
    """토큰 발급은 1회만 — 같은 클라이언트로 두 번 조회해도 tokenP 호출은 1번."""
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if "tokenP" in request.url.path:
            token_calls += 1
            return _token_response(request)
        return _quote_response()

    client = client_factory(handler)

    await client.get_prev_close("000660")
    await client.get_prev_close("005930")

    assert token_calls == 1


@pytest.mark.asyncio
async def test_get_prev_close_raises_on_token_failure(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error_description": "invalid app key"})

    client = client_factory(handler)

    with pytest.raises(RuntimeError, match="토큰"):
        await client.get_prev_close("000660")


@pytest.mark.asyncio
async def test_get_prev_close_raises_on_quote_api_error(client_factory) -> None:
    """rt_cd != '0'이면 KIS가 논리적 오류를 응답한 것 — 예외로 알려야 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "tokenP" in request.url.path:
            return _token_response(request)
        return httpx.Response(
            200,
            json={"output": {}, "rt_cd": "1", "msg_cd": "EGW00123", "msg1": "모의투자 미지원 종목입니다."},
        )

    client = client_factory(handler)

    with pytest.raises(RuntimeError, match="모의투자 미지원"):
        await client.get_prev_close("000660")


@pytest.mark.asyncio
async def test_get_prev_close_raises_on_missing_stck_sdpr_field(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "tokenP" in request.url.path:
            return _token_response(request)
        return httpx.Response(
            200,
            json={"output": {"stck_prpr": "2265000"}, "rt_cd": "0", "msg_cd": "MCA00000", "msg1": "OK"},
        )

    client = client_factory(handler)

    with pytest.raises(RuntimeError, match="stck_sdpr"):
        await client.get_prev_close("000660")


@pytest.mark.asyncio
async def test_get_prev_close_uses_correct_request_params(client_factory) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "tokenP" in request.url.path:
            return _token_response(request)
        captured["params"] = dict(request.url.params)
        captured["headers"] = dict(request.headers)
        return _quote_response()

    client = client_factory(handler)
    await client.get_prev_close("000660")

    assert captured["params"]["FID_INPUT_ISCD"] == "000660"
    assert captured["params"]["FID_COND_MRKT_DIV_CODE"] == "J"
    assert captured["headers"]["tr_id"] == "FHKST01010100"
    assert captured["headers"]["appkey"] == "test-app-key"
    assert "test-token-abc" in captured["headers"]["authorization"]
