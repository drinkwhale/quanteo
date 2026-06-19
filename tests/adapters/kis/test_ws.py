"""KisWsClient — WebSocket 어댑터 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.adapters.kis.ws import KisWsClient, WsMessage
from core.config.settings import Env, KisCredentials, Market

DUMMY_CREDS = KisCredentials(
    app_key="testkey",
    app_secret="testsecret",  # type: ignore[arg-type]
    account_no="12345678",
    account_code="01",
    hts_id="test",
)


def _make_auth() -> MagicMock:
    auth = MagicMock()
    auth.credentials = DUMMY_CREDS
    ws_key = MagicMock()
    ws_key.key = "dummy_ws_key"
    auth.get_websocket_key = AsyncMock(return_value=ws_key)
    return auth


# ---------------------------------------------------------------------------
# 구독 등록
# ---------------------------------------------------------------------------


def test_subscribe_price_domestic():
    client = KisWsClient(_make_auth(), env=Env.VPS, market=Market.DOMESTIC)
    client.subscribe_price("005930")
    assert len(client._subscriptions) == 1
    tr_id, tr_key = client._subscriptions[0]
    assert tr_id == "H0STCNT0"
    assert tr_key == "005930"


def test_subscribe_quote_domestic():
    client = KisWsClient(_make_auth(), env=Env.VPS, market=Market.DOMESTIC)
    client.subscribe_quote("005930")
    assert client._subscriptions[0][0] == "H0STASP0"


def test_subscribe_quote_overseas_raises():
    client = KisWsClient(_make_auth(), env=Env.VPS, market=Market.OVERSEAS)
    with pytest.raises(ValueError, match="지원되지 않습니다"):
        client.subscribe_quote("AAPL")


# ---------------------------------------------------------------------------
# 메시지 파싱
# ---------------------------------------------------------------------------


def test_handle_raw_pipe_format():
    received: list[WsMessage] = []
    client = KisWsClient(_make_auth(), on_message=received.append)

    # KIS 실시간 시세 포맷: "0|H0STCNT0|005930|75000^..."
    client._handle_raw("0|H0STCNT0|005930|75000^1000")

    assert len(received) == 1
    assert received[0].tr_id == "H0STCNT0"
    assert received[0].tr_key == "005930"
    assert "75000" in received[0].data_body


def test_handle_raw_json_error_response():
    received: list[WsMessage] = []
    client = KisWsClient(_make_auth(), on_message=received.append)

    import json

    error_resp = json.dumps({
        "header": {"tr_id": "H0STCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "1", "msg1": "인증 실패"},
    })
    client._handle_raw(error_resp)
    # 에러 응답은 콜백 호출 안 함
    assert len(received) == 0


def test_handle_raw_json_success():
    received: list[WsMessage] = []
    client = KisWsClient(_make_auth(), on_message=received.append)

    import json

    ok_resp = json.dumps({
        "header": {"tr_id": "H0STCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "0", "msg1": "SUBSCRIBE SUCCESS"},
    })
    client._handle_raw(ok_resp)
    assert len(received) == 1
    assert received[0].tr_id == "H0STCNT0"
