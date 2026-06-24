"""KIS 인증 모듈 단위 테스트."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.adapters.kis.auth import (
    AccessToken,
    KisAuth,
    _cache_path,
    _load_token_cache,
    _save_token_cache,
)
from core.config.settings import Env, KisCredentials


@pytest.fixture
def credentials() -> KisCredentials:
    return KisCredentials(
        app_key="TESTKEY1234567890123",
        app_secret="TESTSECRET12345678901234567890123456789012345678",
        account_no="12345678",
        account_code="01",
        hts_id="test_user",
    )


@pytest.fixture
def vps_auth(credentials: KisCredentials, tmp_path: Path) -> KisAuth:
    return KisAuth(env=Env.VPS, credentials=credentials, cache_dir=tmp_path)


def _mock_token_response(token: str = "TOKEN_ABC", expires_in: int = 86400) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"access_token": token, "expires_in": expires_in})
    return resp


def _mock_ws_key_response(key: str = "WSKEY_XYZ") -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"approval_key": key})
    return resp


# ---------------------------------------------------------------------------
# AccessToken
# ---------------------------------------------------------------------------


class TestAccessToken:
    def test_not_expired_when_fresh(self) -> None:
        token = AccessToken("tok", datetime.now(UTC) + timedelta(hours=12))
        assert not token.is_expired()

    def test_expired_when_past(self) -> None:
        token = AccessToken("tok", datetime.now(UTC) - timedelta(seconds=1))
        assert token.is_expired()

    def test_expired_within_buffer(self) -> None:
        # 만료까지 3분 남았을 때 버퍼 5분이면 만료로 간주
        token = AccessToken("tok", datetime.now(UTC) + timedelta(seconds=180))
        assert token.is_expired(buffer_seconds=300)

    def test_str_returns_token(self) -> None:
        token = AccessToken("mytoken", datetime.now(UTC) + timedelta(hours=1))
        assert str(token) == "mytoken"


# ---------------------------------------------------------------------------
# 토큰 캐시
# ---------------------------------------------------------------------------


class TestTokenCache:
    def test_save_and_load_valid_token(self, tmp_path: Path) -> None:
        token = AccessToken("CACHED_TOKEN", datetime.now(UTC) + timedelta(hours=12))
        _save_token_cache(token, Env.VPS, tmp_path)

        loaded = _load_token_cache(Env.VPS, tmp_path)
        assert loaded is not None
        assert loaded.token == "CACHED_TOKEN"

    def test_expired_cache_returns_none(self, tmp_path: Path) -> None:
        token = AccessToken("OLD_TOKEN", datetime.now(UTC) - timedelta(hours=1))
        _save_token_cache(token, Env.VPS, tmp_path)

        loaded = _load_token_cache(Env.VPS, tmp_path)
        assert loaded is None

    def test_missing_cache_returns_none(self, tmp_path: Path) -> None:
        result = _load_token_cache(Env.VPS, tmp_path)
        assert result is None

    def test_corrupted_cache_returns_none(self, tmp_path: Path) -> None:
        _cache_path(Env.VPS, tmp_path).write_text("not-valid-json")
        result = _load_token_cache(Env.VPS, tmp_path)
        assert result is None

    def test_cache_path_differs_by_env(self, tmp_path: Path) -> None:
        prod_path = _cache_path(Env.PROD, tmp_path)
        vps_path = _cache_path(Env.VPS, tmp_path)
        assert prod_path != vps_path


# ---------------------------------------------------------------------------
# KisAuth — Access Token
# ---------------------------------------------------------------------------


class TestKisAuthAccessToken:
    @pytest.mark.asyncio
    async def test_issues_token_from_api(self, vps_auth: KisAuth) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_token_response("NEW_TOKEN"))

        with patch("core.adapters.kis.auth.httpx.AsyncClient", return_value=mock_client):
            token = await vps_auth.get_access_token()

        assert token.token == "NEW_TOKEN"

    @pytest.mark.asyncio
    async def test_returns_cached_token_on_second_call(
        self, vps_auth: KisAuth
    ) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_token_response("FIRST_TOKEN"))

        with patch("core.adapters.kis.auth.httpx.AsyncClient", return_value=mock_client):
            token1 = await vps_auth.get_access_token()
            token2 = await vps_auth.get_access_token()

        # API는 한 번만 호출되어야 한다
        assert mock_client.post.call_count == 1
        assert token1.token == token2.token == "FIRST_TOKEN"

    @pytest.mark.asyncio
    async def test_loads_from_file_cache(
        self, vps_auth: KisAuth
    ) -> None:
        valid_token = AccessToken(
            "CACHED_TOKEN",
            datetime.now(UTC) + timedelta(hours=12),
        )
        _save_token_cache(valid_token, Env.VPS, vps_auth.cache_dir)

        mock_post = AsyncMock()
        with patch("core.adapters.kis.auth.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=mock_post))
            token = await vps_auth.get_access_token()

        # 캐시 파일이 있으면 API 호출 없어야 한다
        mock_post.assert_not_called()
        assert token.token == "CACHED_TOKEN"

    @pytest.mark.asyncio
    async def test_reissues_when_expired(
        self, vps_auth: KisAuth
    ) -> None:
        expired = AccessToken("OLD", datetime.now(UTC) - timedelta(hours=1))
        _save_token_cache(expired, Env.VPS, vps_auth.cache_dir)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_token_response("RENEWED"))

        with patch("core.adapters.kis.auth.httpx.AsyncClient", return_value=mock_client):
            token = await vps_auth.get_access_token()

        assert token.token == "RENEWED"


# ---------------------------------------------------------------------------
# KisAuth — WebSocket 접속키 (T004)
# ---------------------------------------------------------------------------


class TestKisAuthWebSocketKey:
    @pytest.mark.asyncio
    async def test_issues_websocket_key(self, vps_auth: KisAuth) -> None:
        # Access Token 미리 주입
        vps_auth._access_token = AccessToken(
            "BEARER_TOKEN",
            datetime.now(UTC) + timedelta(hours=12),
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_ws_key_response("WS_KEY_123"))

        with patch("core.adapters.kis.auth.httpx.AsyncClient", return_value=mock_client):
            ws_key = await vps_auth.get_websocket_key()

        assert ws_key.key == "WS_KEY_123"
        assert str(ws_key) == "WS_KEY_123"

    @pytest.mark.asyncio
    async def test_websocket_key_uses_bearer_token_in_header(
        self, vps_auth: KisAuth
    ) -> None:
        vps_auth._access_token = AccessToken(
            "MY_BEARER",
            datetime.now(UTC) + timedelta(hours=12),
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_ws_key_response("WS_KEY"))

        with patch("core.adapters.kis.auth.httpx.AsyncClient", return_value=mock_client):
            await vps_auth.get_websocket_key()

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs.args[1] if len(call_kwargs.args) > 1 else {})
        assert "Bearer MY_BEARER" in str(headers)
