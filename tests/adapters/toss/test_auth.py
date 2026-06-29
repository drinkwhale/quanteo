"""Toss OAuth2 인증 테스트 — httpx mock 사용."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from core.adapters.toss.auth import OAuth2Token, TossAuth
from core.config.settings import TossCredentials

DUMMY_CREDS = TossCredentials(
    client_id="test-client-id",
    client_secret="test-client-secret",  # type: ignore[arg-type]
)

TOKEN_RESPONSE = {
    "access_token": "test_access_token_abc123",
    "token_type": "Bearer",
    "expires_in": 3600,
}


def _mock_http_client(status: int = 200, body: dict | None = None) -> AsyncMock:
    resp = httpx.Response(status, json=body or TOKEN_RESPONSE)
    resp.request = httpx.Request("POST", "https://openapi.tossinvest.com/oauth2/token")
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)
    return client


# ---------------------------------------------------------------------------
# OAuth2Token
# ---------------------------------------------------------------------------


def test_token_is_valid_when_not_expired():
    token = OAuth2Token(
        access_token="tok",
        token_type="Bearer",
        expires_in=3600,
        issued_at=time.time(),
    )
    assert token.is_valid()


def test_token_invalid_when_expired():
    token = OAuth2Token(
        access_token="tok",
        token_type="Bearer",
        expires_in=0,
        issued_at=time.time() - 100,
    )
    assert not token.is_valid()


def test_token_serialization():
    token = OAuth2Token(
        access_token="tok123",
        token_type="Bearer",
        expires_in=3600,
        issued_at=1000.0,
    )
    data = token.to_dict()
    restored = OAuth2Token.from_dict(data)
    assert restored.access_token == "tok123"
    assert restored.expires_in == 3600
    assert restored.issued_at == 1000.0


# ---------------------------------------------------------------------------
# TossAuth — 토큰 발급
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_access_token_issues_new_token(tmp_path: Path):
    http_client = _mock_http_client()
    auth = TossAuth(DUMMY_CREDS, cache_path=tmp_path / "token.json", http_client=http_client)

    token = await auth.get_access_token()

    assert token.access_token == "test_access_token_abc123"
    assert token.is_valid()
    http_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_get_access_token_uses_memory_cache(tmp_path: Path):
    http_client = _mock_http_client()
    auth = TossAuth(DUMMY_CREDS, cache_path=tmp_path / "token.json", http_client=http_client)

    token1 = await auth.get_access_token()
    token2 = await auth.get_access_token()  # 두 번째 호출 — 캐시 사용

    assert token1.access_token == token2.access_token
    assert http_client.post.call_count == 1  # 발급은 1회만


@pytest.mark.asyncio
async def test_get_access_token_uses_file_cache(tmp_path: Path):
    cache_path = tmp_path / "token.json"
    # 유효한 토큰을 캐시 파일에 미리 저장
    cached_token = OAuth2Token(
        access_token="cached_token",
        token_type="Bearer",
        expires_in=3600,
        issued_at=time.time(),
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w") as f:
        json.dump(cached_token.to_dict(), f)

    http_client = _mock_http_client()
    auth = TossAuth(DUMMY_CREDS, cache_path=cache_path, http_client=http_client)

    token = await auth.get_access_token()

    assert token.access_token == "cached_token"
    http_client.post.assert_not_called()  # 캐시 히트 — 발급 안 함


@pytest.mark.asyncio
async def test_get_access_token_reissues_when_cache_expired(tmp_path: Path):
    cache_path = tmp_path / "token.json"
    expired_token = OAuth2Token(
        access_token="expired_token",
        token_type="Bearer",
        expires_in=0,
        issued_at=time.time() - 100,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w") as f:
        json.dump(expired_token.to_dict(), f)

    http_client = _mock_http_client()
    auth = TossAuth(DUMMY_CREDS, cache_path=cache_path, http_client=http_client)

    token = await auth.get_access_token()

    assert token.access_token == "test_access_token_abc123"
    http_client.post.assert_called_once()


# ---------------------------------------------------------------------------
# TossAuth — 401 감지 후 재발급
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_on_401_deletes_cache_and_reissues(tmp_path: Path):
    cache_path = tmp_path / "token.json"
    old_token = OAuth2Token(
        access_token="old_token",
        token_type="Bearer",
        expires_in=3600,
        issued_at=time.time(),
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w") as f:
        json.dump(old_token.to_dict(), f)

    http_client = _mock_http_client()
    auth = TossAuth(DUMMY_CREDS, cache_path=cache_path, http_client=http_client)
    auth._token = old_token  # 메모리 캐시에도 적재

    new_token = await auth.refresh_on_401()

    assert new_token.access_token == "test_access_token_abc123"
    assert not cache_path.exists() or json.loads(cache_path.read_text())["access_token"] == new_token.access_token
    http_client.post.assert_called_once()
