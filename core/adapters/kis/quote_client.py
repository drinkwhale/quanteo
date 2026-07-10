"""
KisQuoteClient — KIS(한국투자증권) Open API 읽기 전용 시세 조회.

실전 매매 브로커가 아니다 — Phase 8-9에서 KIS 브로커는 완전 제거됐고,
Toss가 유일한 실거래 어댑터다. 이 클라이언트는 딱 하나의 목적만 가진다:
전일 종가(stck_sdpr) 조회. Toss 캔들 API(get_candles)의 종가 데이터가
실제 시세와 어긋나는 사례가 실측으로 확인돼(SK하이닉스: Toss 2,253,000원
vs KIS·네이버 2,186,000원), day_change 계산의 전일 종가만 KIS로 대체한다.

인증: POST /oauth2/tokenP (client_credentials 유사, KIS 전용 포맷).
토큰은 프로세스 메모리에만 캐시한다(파일 캐시 없음) — Toss와 달리 이
클라이언트는 짧은 주기(당일 등락 조회)로만 쓰여 재시작이 잦지 않고,
KIS 토큰 발급 자체가 분당 요청 제한이 있어 매 호출마다 재발급하면 안 된다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://openapi.koreainvestment.com:9443"
_TR_ID_INQUIRE_PRICE = "FHKST01010100"


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float

    def is_valid(self, margin_seconds: float = 60.0) -> bool:
        return time.time() < (self.expires_at - margin_seconds)


class KisQuoteClient:
    """국내 주식 전일 종가(stck_sdpr) 조회 전용 클라이언트.

    Args:
        app_key: KIS 앱키.
        app_secret: KIS 앱시크릿.
        base_url: KIS API 베이스 URL (기본 실전 도메인).
        http_client: 테스트 인젝션용 httpx.AsyncClient.
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        base_url: str = _DEFAULT_BASE_URL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base_url = base_url
        self._http_client = http_client
        self._token: _CachedToken | None = None
        self._lock = asyncio.Lock()

    async def get_prev_close(self, symbol: str) -> Decimal:
        """국내 종목의 전일 종가(기준가, stck_sdpr)를 조회한다.

        Args:
            symbol: 국내 종목 코드 (예: "000660").

        Returns:
            전일 종가.

        Raises:
            RuntimeError: 토큰 발급 실패, KIS API 논리적 오류(rt_cd != "0"),
                          응답에 stck_sdpr 필드가 없는 경우.
        """
        token = await self._get_token()
        client = self._http_client or httpx.AsyncClient()
        try:
            resp = await client.get(
                f"{self._base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": self._app_key,
                    "appsecret": self._app_secret,
                    "tr_id": _TR_ID_INQUIRE_PRICE,
                    "custtype": "P",
                },
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol,
                },
                timeout=10.0,
            )
        finally:
            if self._http_client is None:
                await client.aclose()

        resp.raise_for_status()
        body = resp.json()

        if body.get("rt_cd") != "0":
            raise RuntimeError(
                f"KIS 시세 조회 실패 (symbol={symbol}, rt_cd={body.get('rt_cd')}): "
                f"{body.get('msg1')}"
            )

        output = body.get("output", {})
        stck_sdpr = output.get("stck_sdpr")
        if not stck_sdpr:
            raise RuntimeError(
                f"KIS 응답에 stck_sdpr(전일 종가) 필드가 없습니다 (symbol={symbol}): {output}"
            )

        return Decimal(str(stck_sdpr))

    async def _get_token(self) -> str:
        """캐시된 토큰이 유효하면 재사용하고, 아니면 새로 발급한다."""
        async with self._lock:
            if self._token and self._token.is_valid():
                return self._token.access_token

            client = self._http_client or httpx.AsyncClient()
            try:
                resp = await client.post(
                    f"{self._base_url}/oauth2/tokenP",
                    json={
                        "grant_type": "client_credentials",
                        "appkey": self._app_key,
                        "appsecret": self._app_secret,
                    },
                    timeout=10.0,
                )
            finally:
                if self._http_client is None:
                    await client.aclose()

            if resp.status_code != 200:
                raise RuntimeError(
                    f"KIS 토큰 발급 실패 (status={resp.status_code}): {resp.text}"
                )

            body = resp.json()
            access_token = body.get("access_token")
            if not access_token:
                raise RuntimeError(f"KIS 토큰 응답에 access_token이 없습니다: {body}")

            expires_in = int(body.get("expires_in", 86400))
            self._token = _CachedToken(access_token=access_token, expires_at=time.time() + expires_in)
            logger.info("KIS 토큰 발급 완료 (expires_in=%ds)", expires_in)
            return self._token.access_token
