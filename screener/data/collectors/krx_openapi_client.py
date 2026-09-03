"""KRX Open API 기반 시세 수집기 (공식 API).

KRX 정보데이터시스템(openapi.krx.co.kr)을 통해
코스피/코스닥 전 종목의 시세 데이터를 조회합니다.

Reference: https://openapi.krx.co.kr/
Auth: AUTH_KEY 헤더에 API 인증키 포함
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib3
from pathlib import Path
from typing import Any

import pandas as pd
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path("screener/data/cache")
_KRX_API_BASE = "https://openapi.krx.co.kr/api"
_REQUEST_TIMEOUT = 10


class KrxOpenApiClient:
    """KRX 공식 Open API 클라이언트.

    Attrs:
        api_key: AUTH_KEY 헤더에 사용할 인증키.
        cache_dir: 조회 결과 캐시 디렉토리.
    """

    def __init__(self, api_key: str, cache_dir: Path | str = _DEFAULT_CACHE_DIR) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._cache_dir = Path(cache_dir)
        self._session = requests.Session()
        self._session.headers.update({"AUTH_KEY": self._api_key, "Content-Type": "application/json"})

    async def fetch_universe(self, date: str) -> pd.DataFrame:
        """코스피+코스닥 전 종목의 일별 매매 정보를 조회한다.

        Args:
            date: 조회 일자 (YYYYMMDD).

        Returns:
            DataFrame with columns: ticker, name, market, close, volume, market_cap, shares_outstanding.
        """
        cache_path = self._cache_dir / f"{date}_krx_universe.parquet"
        if cache_path.exists():
            logger.info(f"KRX universe cache hit: {cache_path}")
            return pd.read_parquet(cache_path)

        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, self._fetch_universe_sync, date)

        if not df.empty:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache_path)
            logger.info(f"KRX universe cached: {cache_path}")
        return df

    async def fetch_stock_info(self, ticker: str, date: str) -> dict[str, Any] | None:
        """단일 종목의 시세 정보를 조회한다.

        Args:
            ticker: 종목 코드 (예: "005930").
            date: 조회 일자 (YYYYMMDD).

        Returns:
            Dict with keys: ticker, name, market, close, volume, market_cap, shares_outstanding.
                None if not found.
        """
        df = await self.fetch_universe(date)
        if df.empty:
            return None

        row = df[df["ticker"] == ticker]
        if row.empty:
            logger.warning(f"Ticker not found: {ticker}")
            return None

        return row.iloc[0].to_dict()

    def _fetch_universe_sync(self, date: str) -> pd.DataFrame:
        """KRX Open API에서 코스피/코스닥 일별매매정보를 동기로 조회.

        Args:
            date: 조회 일자 (YYYYMMDD).

        Returns:
            DataFrame with columns: ticker, name, market, close, volume, market_cap, shares_outstanding.
                Empty DataFrame if all markets fail.
        """
        frames = []
        endpoints = [
            ("sto/stk_bydd_trd", "KOSPI"),
            ("sto/ksq_bydd_trd", "KOSDAQ"),
        ]

        for endpoint, market_name in endpoints:
            try:
                url = f"{_KRX_API_BASE}/{endpoint}"
                payload = {"basDd": date}

                resp = self._session.post(url, data=json.dumps(payload), timeout=_REQUEST_TIMEOUT, verify=False)
                resp.raise_for_status()

                data = resp.json()
                if not data.get("OutBlock_1"):
                    logger.warning(f"KRX API 응답 빈 데이터({market_name})")
                    continue

                df = pd.DataFrame(data["OutBlock_1"])
                if df.empty:
                    continue

                df = df.rename(columns={
                    "ISU_CD": "ticker",
                    "ISU_NM": "name",
                    "TDD_CLSPRC": "close",
                    "ACC_TRDVOL": "volume",
                    "MKTCAP": "market_cap",
                    "LIST_SHRS": "shares_outstanding",
                })
                df["market"] = market_name

                required_cols = ["ticker", "name", "market", "close", "volume", "market_cap", "shares_outstanding"]
                df = df[[col for col in required_cols if col in df.columns]]
                frames.append(df)

                logger.info(f"✅ KRX {market_name}: {len(df)} stocks")

            except requests.RequestException as exc:
                logger.warning(f"KRX API request error ({market_name}): {exc}")
            except (KeyError, ValueError) as exc:
                logger.warning(f"KRX API parse error ({market_name}): {exc}")

        if not frames:
            logger.error("KRX API all markets failed")
            return pd.DataFrame()

        return pd.concat(frames, ignore_index=True)

