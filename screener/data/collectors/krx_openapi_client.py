"""KRX Open API 기반 시세 수집기 (공식 API).

유가증권 일별매매정보 API를 사용하여
코스피/코스닥 전 종목의 시세 데이터를 조회합니다.

Spec: specs/유가증권.docx
Endpoint: https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path("screener/data/cache")
_KRX_API_BASE = "https://data-dbg.krx.co.kr/svc/apis/sto"


class KrxOpenApiClient:
    """KRX 유가증권 API 클라이언트."""

    def __init__(self, api_key: str, cache_dir: Path | str = _DEFAULT_CACHE_DIR) -> None:
        self._api_key = api_key  # 현재 미사용 (공개 API)
        self._cache_dir = Path(cache_dir)

    async def fetch_universe(self, date: str) -> pd.DataFrame:
        """코스피+코스닥 전 종목의 일별 매매 정보를 조회한다.

        Args:
            date: 조회 일자 (YYYYMMDD).

        Returns:
            DataFrame with columns: ticker, name, market, close, volume, market_cap, shares_outstanding
        """
        cache_path = self._cache_dir / f"{date}_krx_universe.parquet"
        if cache_path.exists():
            return pd.read_parquet(cache_path)

        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, self._fetch_universe_sync, date)

        if not df.empty:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache_path)
        return df

    def _fetch_universe_sync(self, date: str) -> pd.DataFrame:
        """KRX API에서 코스피/코스닥 일별매매정보를 동기로 조회."""
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        frames = []
        endpoints = [
            ("stk_bydd_trd", "KOSPI"),  # 유가증권(코스피)
            ("ksq_bydd_trd", "KOSDAQ"),  # 코스닥
        ]

        for endpoint, market_name in endpoints:
            try:
                url = f"{_KRX_API_BASE}/{endpoint}"
                payload = {"basDd": date}
                headers = {"Content-Type": "application/json"}

                resp = requests.post(
                    url,
                    data=json.dumps(payload),
                    headers=headers,
                    timeout=10,
                    verify=False
                )

                if resp.status_code != 200:
                    logger.warning(f"KRX API 요청 실패({market_name}): {resp.status_code}")
                    continue

                data = resp.json()
                if not data.get("OutBlock_1"):
                    logger.warning(f"KRX API 응답 빈 데이터({market_name})")
                    continue

                df = pd.DataFrame(data["OutBlock_1"])
                if df.empty:
                    continue

                # 컬럼명 매핑
                df = df.rename(columns={
                    "ISU_CD": "ticker",
                    "ISU_NM": "name",
                    "TDD_CLSPRC": "close",
                    "ACC_TRDVOL": "volume",
                    "MKTCAP": "market_cap",
                    "LIST_SHRS": "shares_outstanding",
                })

                # 시장 정보 추가
                df["market"] = market_name

                # 필요한 컬럼만 선택
                required_cols = ["ticker", "name", "market", "close", "volume", "market_cap", "shares_outstanding"]
                df = df[[col for col in required_cols if col in df.columns]]
                frames.append(df)

                logger.info(f"✅ KRX API {market_name} 성공: {len(df)}개 종목")

            except Exception as exc:
                logger.warning(f"KRX API 조회 실패({market_name}): {exc}")
                continue

        if not frames:
            logger.error("KRX API 전체 조회 실패")
            return pd.DataFrame()

        return pd.concat(frames, ignore_index=True)

