"""KisWsClient — WebSocket 어댑터 단위 테스트."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

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

    ok_resp = json.dumps({
        "header": {"tr_id": "H0STCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "0", "msg1": "SUBSCRIBE SUCCESS"},
    })
    client._handle_raw(ok_resp)
    assert len(received) == 1
    assert received[0].tr_id == "H0STCNT0"


# ---------------------------------------------------------------------------
# 연결·재연결·종료 (websockets.connect mock)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_sets_running_false():
    """stop() 호출 시 _running이 False로 설정되어야 한다."""
    client = KisWsClient(_make_auth())
    client._running = True

    # _conn이 없는 상태에서 stop() — 예외 없이 동작해야 함
    await client.stop()
    assert client._running is False


@pytest.mark.asyncio
async def test_run_reconnects_on_connection_error():
    """연결 실패 시 reconnect_delay 후 재시도한다."""
    client = KisWsClient(_make_auth(), reconnect_delay=0.01)

    call_count = 0

    async def fake_connect_and_receive() -> None:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("연결 실패 (테스트)")
        # 3번째 호출에서 정상 종료
        client._running = False

    client._connect_and_receive = fake_connect_and_receive  # type: ignore[method-assign]
    await client.run()

    assert call_count == 3


@pytest.mark.asyncio
async def test_run_stops_immediately_when_not_running():
    """stop() 후 연결 오류가 나면 루프를 즉시 종료한다."""
    client = KisWsClient(_make_auth(), reconnect_delay=0.01)

    async def fake_connect_and_receive() -> None:
        client._running = False
        raise ConnectionError("연결 실패 (테스트)")

    client._connect_and_receive = fake_connect_and_receive  # type: ignore[method-assign]
    await client.run()  # _running=False이므로 재연결 없이 종료

    assert client._running is False


@pytest.mark.asyncio
async def test_messages_clears_conn_on_exit():
    """messages() 완료 후 self._conn이 None으로 정리되어야 한다."""
    client = KisWsClient(_make_auth())
    client.subscribe_price("005930")

    async def _fake_conn():
        yield "0|H0STCNT0|005930|75000^1000"

    mock_conn = MagicMock()
    mock_conn.__aiter__ = MagicMock(return_value=_fake_conn())
    mock_conn.send = AsyncMock()

    with patch("core.adapters.kis.ws.websockets.connect") as mock_connect:
        mock_connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_connect.return_value.__aexit__ = AsyncMock(return_value=False)

        msgs = [msg async for msg in client.messages()]

    assert client._conn is None
    assert len(msgs) == 1
