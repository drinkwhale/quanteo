"""
Toss증권 OAuth2 인증 — Client Credentials Grant.

엔드포인트: POST https://openapi.tossinvest.com/oauth2/token
인증 방식: application/x-www-form-urlencoded, grant_type=client_credentials

토큰 캐시: ~/toss/cache/token.json
  - 유효 토큰 1개 원칙: 재발급 시 이전 토큰 즉시 무효화 → 캐시 갱신
  - 401 수신 시: 캐시 삭제 후 즉시 재발급 (중복 인스턴스로 무효화된 경우 처리)
  - 선제적 갱신: expires_in 기반 만료 60초 전 백그라운드 재발급
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from core.config.settings import TossCredentials

logger = logging.getLogger(__name__)

_TOSS_BASE_URL = "https://openapi.tossinvest.com"
_DEFAULT_CACHE_PATH = Path.home() / "toss" / "cache" / "token.json"


# ---------------------------------------------------------------------------
# 토큰 모델
# ---------------------------------------------------------------------------


@dataclass
class OAuth2Token:
    """Toss OAuth2 액세스 토큰."""

    access_token: str
    token_type: str
    expires_in: int      # 초 단위 유효 기간
    issued_at: float     # time.time() 기준 발급 시각

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.expires_in

    def is_valid(self, margin_seconds: float = 60.0) -> bool:
        """만료까지 margin_seconds 이상 남아있으면 유효하다."""
        return time.time() < (self.expires_at - margin_seconds)

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "issued_at": self.issued_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OAuth2Token:
        return cls(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=int(data.get("expires_in", 0)),
            issued_at=float(data.get("issued_at", 0.0)),
        )


# ---------------------------------------------------------------------------
# Toss 인증 클라이언트
# ---------------------------------------------------------------------------


class TossAuth:
    """Toss증권 OAuth2 인증 관리자.

    Args:
        credentials: TossCredentials (client_id, client_secret).
        cache_path: 토큰 캐시 파일 경로. 기본값 ~/toss/cache/token.json.
        http_client: 테스트 인젝션용 httpx.AsyncClient.
    """

    def __init__(
        self,
        credentials: TossCredentials,
        cache_path: Path | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._credentials = credentials
        self._cache_path = cache_path or _DEFAULT_CACHE_PATH
        self._http_client = http_client
        self._token: OAuth2Token | None = None
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    async def get_access_token(self) -> OAuth2Token:
        """유효한 액세스 토큰을 반환한다.

        캐시 → 메모리 순으로 확인 후, 없거나 만료 임박 시 재발급한다.
        """
        async with self._lock:
            if self._token and self._token.is_valid():
                return self._token

            # 캐시 파일 확인
            cached = self._load_cache()
            if cached and cached.is_valid():
                self._token = cached
                self._schedule_proactive_refresh(cached)
                return self._token

            # 신규 발급
            token = await self._issue_token()
            self._token = token
            self._save_cache(token)
            self._schedule_proactive_refresh(token)
            return token

    async def refresh_on_401(self) -> OAuth2Token:
        """401 Unauthorized 수신 시 캐시를 삭제하고 토큰을 재발급한다.

        다른 인스턴스가 이전 토큰을 무효화한 경우를 처리한다.
        """
        async with self._lock:
            logger.warning("401 감지 — 토큰 캐시 삭제 후 재발급")
            self._invalidate_cache()
            self._token = None
            token = await self._issue_token()
            self._token = token
            self._save_cache(token)
            return token

    # ------------------------------------------------------------------
    # 토큰 발급
    # ------------------------------------------------------------------

    async def _issue_token(self) -> OAuth2Token:
        """POST /oauth2/token 으로 신규 토큰을 발급받는다."""
        data = {
            "grant_type": "client_credentials",
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret.get_secret_value(),
        }
        url = f"{_TOSS_BASE_URL}/oauth2/token"

        if self._http_client:
            resp = await self._http_client.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=10.0,
                )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Toss 토큰 발급 실패 (status={resp.status_code}): {resp.text}"
            )

        body = resp.json()
        token = OAuth2Token(
            access_token=body["access_token"],
            token_type=body.get("token_type", "Bearer"),
            expires_in=int(body.get("expires_in", 3600)),
            issued_at=time.time(),
        )
        logger.info(
            "Toss 토큰 발급 완료 (expires_in=%ds, expires_at=%.0f)",
            token.expires_in,
            token.expires_at,
        )
        return token

    # ------------------------------------------------------------------
    # 캐시
    # ------------------------------------------------------------------

    def _load_cache(self) -> OAuth2Token | None:
        """캐시 파일에서 토큰을 로드한다. 파일 없거나 파싱 실패 시 None."""
        if not self._cache_path.exists():
            return None
        try:
            with self._cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return OAuth2Token.from_dict(data)
        except Exception as exc:
            logger.warning("Toss 토큰 캐시 로드 실패: %s", exc)
            return None

    def _save_cache(self, token: OAuth2Token) -> None:
        """토큰을 캐시 파일에 저장한다."""
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self._cache_path.open("w", encoding="utf-8") as f:
                json.dump(token.to_dict(), f, indent=2)
        except Exception as exc:
            logger.warning("Toss 토큰 캐시 저장 실패: %s", exc)

    def _invalidate_cache(self) -> None:
        """캐시 파일을 삭제한다 (401 감지 시 호출)."""
        try:
            if self._cache_path.exists():
                self._cache_path.unlink()
                logger.debug("Toss 토큰 캐시 삭제 완료")
        except Exception as exc:
            logger.warning("Toss 토큰 캐시 삭제 실패: %s", exc)

    # ------------------------------------------------------------------
    # 선제적 갱신 (백그라운드)
    # ------------------------------------------------------------------

    def _schedule_proactive_refresh(self, token: OAuth2Token) -> None:
        """만료 60초 전에 백그라운드 재발급을 예약한다."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

        delay = token.expires_at - time.time() - 60.0
        if delay <= 0:
            return

        async def _refresh_loop() -> None:
            try:
                await asyncio.sleep(delay)
                logger.info("Toss 토큰 선제적 갱신 시작")
                async with self._lock:
                    new_token = await self._issue_token()
                    self._token = new_token
                    self._save_cache(new_token)
                    self._schedule_proactive_refresh(new_token)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("Toss 토큰 선제적 갱신 실패: %s", exc)

        try:
            loop = asyncio.get_running_loop()
            self._refresh_task = loop.create_task(_refresh_loop())
        except RuntimeError:
            pass  # 이벤트 루프 없음 (테스트 환경 등)
