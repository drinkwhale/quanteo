"""
KIS Open API 인증 모듈.

Access Token 발급·캐싱·재발급 및 WebSocket 접속키 발급을 담당한다.

참조: open-trading-api/examples_llm/auth/
"""

from __future__ import annotations

import json
import logging
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from core.config.settings import Env, KisCredentials

logger = logging.getLogger(__name__)


_KIS_SSL_CONTEXT: ssl.SSLContext | None = None


def _kis_ssl_context() -> ssl.SSLContext:
    """KIS 서버 전용 SSL 컨텍스트 (모듈 레벨 싱글톤).

    - TLS 1.2 상한 고정: KIS 서버가 TLS 1.3 미지원
    - 인증서 검증 비활성화: KIS 인증서에 Authority Key Identifier 미포함으로
      Python 3.14+ OpenSSL이 검증을 거부함 (KIS 서버 인증서 문제)

    ⚠️  CERT_NONE은 MITM 공격에 취약합니다. KIS 인증서 문제 해결 전까지
        모의투자(VPS) 환경에서만 사용하고, 실전 환경은 보안 네트워크에서 실행하세요.
    """
    global _KIS_SSL_CONTEXT
    if _KIS_SSL_CONTEXT is None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _KIS_SSL_CONTEXT = ctx
    return _KIS_SSL_CONTEXT


# ---------------------------------------------------------------------------
# 도메인 상수 (T005 tr_ids.py와 일관성 유지)
# ---------------------------------------------------------------------------

_REST_DOMAIN: dict[Env, str] = {
    Env.PROD: "https://openapi.koreainvestment.com:9443",
    Env.VPS: "https://openapivts.koreainvestment.com:29443",
}

# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------


class AccessToken:
    """KIS Access Token 래퍼."""

    def __init__(self, token: str, expires_at: datetime) -> None:
        self.token = token
        self.expires_at = expires_at

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """만료 buffer_seconds 전부터 만료됐다고 판단한다 (기본 5분)."""
        return datetime.now(UTC) >= self.expires_at - timedelta(seconds=buffer_seconds)

    def __str__(self) -> str:
        return self.token


class WebSocketKey:
    """KIS WebSocket 접속키 래퍼."""

    def __init__(self, key: str) -> None:
        self.key = key

    def __str__(self) -> str:
        return self.key


# ---------------------------------------------------------------------------
# 토큰 캐시
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_DIR = Path.home() / "KIS" / "cache"


def _cache_path(env: Env, cache_dir: Path) -> Path:
    return cache_dir / f"token_{env.value}.json"


def _save_token_cache(token: AccessToken, env: Env, cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "access_token": token.token,
        "expires_at": token.expires_at.isoformat(),
    }
    _cache_path(env, cache_dir).write_text(json.dumps(data), encoding="utf-8")


def _load_token_cache(env: Env, cache_dir: Path) -> AccessToken | None:
    path = _cache_path(env, cache_dir)
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        expires_at = datetime.fromisoformat(data["expires_at"])
        token = AccessToken(token=data["access_token"], expires_at=expires_at)
        if not token.is_expired():
            return token
        return None
    except Exception as exc:
        logger.warning("토큰 캐시 읽기 실패, 재발급합니다: %s", exc)
        return None


# ---------------------------------------------------------------------------
# KIS 인증 클라이언트
# ---------------------------------------------------------------------------


class KisAuth:
    """KIS API 인증 관리 클라이언트.

    Access Token과 WebSocket 접속키를 발급·캐싱·재발급한다.

    Args:
        env: 투자 환경 (PROD/VPS).
        credentials: KIS API 자격증명.
        cache_dir: 토큰 캐시 저장 디렉토리. 기본값: ~/KIS/cache/
        http_client: 테스트 인젝션용 httpx.AsyncClient. None이면 내부 생성.
    """

    def __init__(
        self,
        env: Env,
        credentials: KisCredentials,
        cache_dir: Path | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.env = env
        self.credentials = credentials
        self.cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self._base_url = _REST_DOMAIN[env]
        self._http_client = http_client
        self._access_token: AccessToken | None = None
        if env == Env.PROD:
            logger.warning(
                "실전(PROD) 환경에서 인증서 검증이 비활성화됩니다 (KIS 서버 인증서 문제). "
                "신뢰할 수 있는 네트워크에서만 실행하세요."
            )

    # ------------------------------------------------------------------
    # Access Token
    # ------------------------------------------------------------------

    async def get_access_token(self) -> AccessToken:
        """유효한 Access Token을 반환한다. 필요 시 재발급."""
        if self._access_token and not self._access_token.is_expired():
            return self._access_token

        # 캐시 파일 시도
        cached = _load_token_cache(self.env, self.cache_dir)
        if cached:
            self._access_token = cached
            logger.debug("캐시에서 토큰 로드 (env=%s)", self.env.value)
            return self._access_token

        # 신규 발급
        self._access_token = await self._issue_access_token()
        _save_token_cache(self._access_token, self.env, self.cache_dir)
        logger.info("새 Access Token 발급 완료 (env=%s)", self.env.value)
        return self._access_token

    async def _issue_access_token(self) -> AccessToken:
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.credentials.app_key,
            "appsecret": self.credentials.app_secret.get_secret_value(),
        }
        headers = {"content-type": "application/json"}

        if self._http_client:
            resp = await self._http_client.post(
                f"{self._base_url}/oauth2/tokenP",
                json=payload,
                headers=headers,
                timeout=10.0,
            )
        else:
            async with httpx.AsyncClient(verify=_kis_ssl_context()) as c:
                resp = await c.post(
                    f"{self._base_url}/oauth2/tokenP",
                    json=payload,
                    headers=headers,
                    timeout=10.0,
                )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        token_str: str = data["access_token"]
        expires_in: int = int(data.get("expires_in", 86400))
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        return AccessToken(token=token_str, expires_at=expires_at)

    async def revoke_access_token(self) -> None:
        """Access Token 폐기 (로그아웃)."""
        if not self._access_token:
            return

        token = await self.get_access_token()
        payload = {
            "appkey": self.credentials.app_key,
            "appsecret": self.credentials.app_secret.get_secret_value(),
            "token": token.token,
        }
        headers = {"content-type": "application/json"}

        async with httpx.AsyncClient(verify=_kis_ssl_context()) as client:
            resp = await client.post(
                f"{self._base_url}/oauth2/revokeP",
                json=payload,
                headers=headers,
                timeout=10.0,
            )
        resp.raise_for_status()

        self._access_token = None
        cache_file = _cache_path(self.env, self.cache_dir)
        if cache_file.exists():
            cache_file.unlink()
        logger.info("Access Token 폐기 완료 (env=%s)", self.env.value)

    # ------------------------------------------------------------------
    # WebSocket 접속키 (T004)
    # ------------------------------------------------------------------

    async def get_websocket_key(self) -> WebSocketKey:
        """WebSocket 실시간 구독용 접속키를 발급한다.

        WebSocket 키는 캐싱하지 않는다 — 연결마다 새로 발급.

        참조: open-trading-api auth/auth_ws 패턴
        """
        token = await self.get_access_token()

        payload = {
            "grant_type": "client_credentials",
            "appkey": self.credentials.app_key,
            "secretkey": self.credentials.app_secret.get_secret_value(),
        }
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token.token}",
        }

        async with httpx.AsyncClient(verify=_kis_ssl_context()) as client:
            resp = await client.post(
                f"{self._base_url}/oauth2/Approval",
                json=payload,
                headers=headers,
                timeout=10.0,
            )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        ws_key: str = data["approval_key"]
        logger.info("WebSocket 접속키 발급 완료 (env=%s)", self.env.value)
        return WebSocketKey(ws_key)
