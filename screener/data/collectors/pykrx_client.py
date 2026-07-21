"""pykrx 기반 시세·시총·밸류에이션·수급 수집기.

KRX 조회는 동기 라이브러리(pykrx)라 asyncio 이벤트 루프를 막지 않도록
run_in_executor로 감싼다. 시세/수급은 일별 parquet 캐시를 사용해 같은 날
재호출을 피한다.

NOTE: pykrx 반환 컬럼명(시가총액/PER/PBR 등)은 문서 기준으로 매핑했다.
      실거래 투입 전 실제 KRX 응답으로 컬럼명 검증 필요 (네트워크 제한
      환경에서 라이브 호출 검증 불가 — 스펙 8절 Phase 1 로컬 검증 스크립트
      (T101)로 실행 시 확인할 것).

NOTE: KRX가 전종목시세/시총/펀더멘털 등 대량 조회 엔드포인트(JSON API,
      CSV 다운로드 OTP 플로우 포함)에 로그인 세션을 요구하도록 변경했다
      (2026-07 확인, 세션 쿠키만으로는 우회 불가 — 실제 KRX_ID/KRX_PW 로그인
      필수). krx_id/krx_pw를 생성자에 넘기면 이 클라이언트가 os.environ에
      설정해 pykrx의 내장 로그인 세션(KRX_ID/KRX_PW 환경 변수 기반)을
      활성화한다. 투자자별 순매수·공매도 잔고 등 개별/기간 조회 엔드포인트는
      로그인 없이도 동작한다.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_MARKETS = ("KOSPI", "KOSDAQ")
_MAX_FALLBACK_DAYS = 7

_DEFAULT_CACHE_DIR = Path("screener/data/cache")


def _prev_day(date: str) -> str:
    dt = datetime.strptime(date, "%Y%m%d") - timedelta(days=1)
    return dt.strftime("%Y%m%d")


class PykrxClient:
    """KRX 시세·시총·밸류에이션·수급 데이터 수집기."""

    def __init__(
        self,
        cache_dir: Path | str = _DEFAULT_CACHE_DIR,
        krx_id: str = "",
        krx_pw: str = "",
    ) -> None:
        self._cache_dir = Path(cache_dir)
        # pykrx는 KRX_ID/KRX_PW를 os.environ에서 직접 읽는다(생성자 인자로 못
        # 받음) — 둘 다 채워졌을 때만 설정하고, 비워두면 이미 shell에 export된
        # 값이 있어도 그대로 둔다(로컬 수동 검증 스크립트용 탈출구).
        if krx_id and krx_pw:
            os.environ["KRX_ID"] = krx_id
            os.environ["KRX_PW"] = krx_pw

    # ------------------------------------------------------------------
    # 유니버스 (시세·시총·밸류에이션)
    # ------------------------------------------------------------------

    async def fetch_universe(self, date: str) -> pd.DataFrame:
        """코스피+코스닥 전 종목의 시세·시총·PER/PBR/배당수익률을 조회한다.

        Args:
            date: 조회 일자 (YYYYMMDD).

        Returns:
            columns: ticker, name, market, close, volume, change_pct,
                      market_cap, shares_outstanding, per, pbr, div_yield
        """
        cache_path = self._cache_dir / f"{date}_ohlcv.parquet"
        if cache_path.exists():
            return pd.read_parquet(cache_path)

        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, self._fetch_universe_sync, date)

        attempts = 0
        target_date = date
        while df.empty and attempts < _MAX_FALLBACK_DAYS:
            target_date = _prev_day(target_date)
            logger.warning("pykrx 휴장일 감지(%s) — 직전 영업일(%s)로 폴백", date, target_date)
            df = await loop.run_in_executor(None, self._fetch_universe_sync, target_date)
            attempts += 1

        if not df.empty:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache_path)
        return df

    def _fetch_universe_sync(self, date: str) -> pd.DataFrame:
        from pykrx import stock

        frames: list[pd.DataFrame] = []
        for market in _MARKETS:
            ohlcv = stock.get_market_ohlcv(date, market=market)
            if ohlcv is None or ohlcv.empty:
                continue
            cap = stock.get_market_cap(date, market=market)
            fund = stock.get_market_fundamental(date, market=market)

            merged = ohlcv.copy()
            if cap is not None and not cap.empty:
                # get_market_ohlcv가 이미 시가총액을 포함해서 반환하는 pykrx
                # 버전이 있다(실거래 조회로 확인, T101 로컬 검증 당시 mock에는
                # 없어 미발견) — 겹치면 join이 ValueError로 죽으므로 상장주식수만
                # cap에서 가져온다.
                cap_cols = [c for c in ("시가총액", "상장주식수") if c not in merged.columns]
                if cap_cols:
                    merged = merged.join(cap.reindex(columns=cap_cols), how="left")
            if fund is not None and not fund.empty:
                merged = merged.join(fund.reindex(columns=["PER", "PBR", "DIV"]), how="left")
            merged["market"] = market
            frames.append(merged)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames)
        combined.index.name = "ticker"
        combined = combined.reset_index()
        combined = combined.rename(
            columns={
                "종가": "close",
                "거래량": "volume",
                "거래대금": "trading_value",
                "등락률": "change_pct",
                "시가총액": "market_cap",
                "상장주식수": "shares_outstanding",
                "PER": "per",
                "PBR": "pbr",
                "DIV": "div_yield",
            }
        )
        if "trading_value" not in combined.columns:
            # 일부 pykrx 버전은 전종목 조회에서 거래대금을 반환하지 않는다 — 근사치로 대체.
            combined["trading_value"] = combined.get("close", 0) * combined.get("volume", 0)
        try:
            combined["name"] = combined["ticker"].map(stock.get_market_ticker_name)
        except Exception as exc:  # pragma: no cover - 네트워크 의존
            logger.warning("종목명 매핑 실패, 빈 값으로 대체: %s", exc)
            combined["name"] = ""

        combined["sector"] = combined["ticker"].map(self._sector_map(date))
        combined["sector"] = combined["sector"].fillna("UNKNOWN")
        return combined

    def _sector_map(self, date: str) -> dict[str, str]:
        """티커 → 업종명 매핑. 실패 시 빈 매핑(전부 UNKNOWN 처리)."""
        from pykrx import stock

        mapping: dict[str, str] = {}
        for market in _MARKETS:
            try:
                sectors = stock.get_market_sector_classifications(date, market)
            except Exception as exc:
                logger.warning("업종 분류 조회 실패(%s/%s): %s", date, market, exc)
                continue
            if sectors is None or sectors.empty:
                continue
            # 컬럼명은 pykrx 버전에 따라 "업종명" 또는 "업종"으로 다를 수 있다.
            sector_col = next((c for c in ("업종명", "업종") if c in sectors.columns), None)
            if sector_col is None:
                continue
            mapping.update(sectors[sector_col].to_dict())
        return mapping

    # ------------------------------------------------------------------
    # 단일 종목 일봉 히스토리 (박병창 매수 3원칙 판정용)
    # ------------------------------------------------------------------

    async def fetch_ohlcv_history(
        self, ticker: str, end_date: str, lookback_days: int = 40
    ) -> pd.DataFrame:
        """단일 종목의 최근 일봉 히스토리를 조회한다.

        전종목 대량조회와 달리 단일 종목·기간 조회 엔드포인트는 로그인 세션이
        없어도 동작한다(실거래 확인 완료).

        Args:
            ticker: 종목코드.
            end_date: 조회 종료일 (YYYYMMDD).
            lookback_days: end_date 기준 역산할 달력일수(거래일 아님 — 주말·
                휴장 포함 여유를 둔 값. 기본 40일이면 통상 20영업일 이상 확보).

        Returns:
            columns: 시가, 고가, 저가, 종가, 거래량 (index: 날짜, datetime64,
                오래된 것부터 최신 순). 조회 실패 시 빈 DataFrame.
        """
        cache_path = self._cache_dir / f"{end_date}_{ticker}_hist.parquet"
        if cache_path.exists():
            return pd.read_parquet(cache_path)

        start_date = (
            datetime.strptime(end_date, "%Y%m%d") - timedelta(days=lookback_days)
        ).strftime("%Y%m%d")
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(
            None, self._fetch_ohlcv_history_sync, ticker, start_date, end_date
        )
        if not df.empty:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache_path)
        return df

    def _fetch_ohlcv_history_sync(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        from pykrx import stock

        try:
            df = stock.get_market_ohlcv(start_date, end_date, ticker)
        except Exception as exc:
            logger.warning("일봉 히스토리 조회 실패(%s): %s", ticker, exc)
            return pd.DataFrame()
        return df if df is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # 투자자별 순매수 (외인/기관)
    # ------------------------------------------------------------------

    async def fetch_investor_trading(self, date: str) -> pd.DataFrame:
        """외인+기관 순매수(금액) 를 티커 기준으로 조회한다.

        Returns:
            columns: ticker, foreign_net, institution_net
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_investor_trading_sync, date)

    def _fetch_investor_trading_sync(self, date: str) -> pd.DataFrame:
        from pykrx import stock

        series: dict[str, pd.Series] = {}
        for investor, col in (("외국인", "foreign_net"), ("기관합계", "institution_net")):
            parts: list[pd.DataFrame] = []
            for market in _MARKETS:
                try:
                    df = stock.get_market_net_purchases_of_equities(date, date, market, investor)
                except Exception as exc:
                    logger.warning("투자자별 순매수 조회 실패(%s/%s): %s", market, investor, exc)
                    continue
                if df is not None and not df.empty:
                    parts.append(df)
            if parts:
                combined = pd.concat(parts)
                series[col] = combined["순매수거래대금"].groupby(level=0).sum()

        if not series:
            return pd.DataFrame(columns=["ticker", "foreign_net", "institution_net"])

        result = pd.DataFrame(series)
        result.index.name = "ticker"
        return result.reset_index().fillna(0)

    # ------------------------------------------------------------------
    # 공매도 잔고
    # ------------------------------------------------------------------

    async def fetch_short_balance(self, date: str) -> pd.DataFrame:
        """티커별 공매도 잔고 현황을 조회한다.

        Returns:
            columns: ticker, short_balance, short_ratio
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_short_balance_sync, date)

    def _fetch_short_balance_sync(self, date: str) -> pd.DataFrame:
        from pykrx import stock

        frames: list[pd.DataFrame] = []
        for market in _MARKETS:
            try:
                df = stock.get_shorting_balance(date, market)
            except Exception as exc:
                logger.warning("공매도 잔고 조회 실패(%s): %s", market, exc)
                continue
            if df is not None and not df.empty:
                frames.append(df)

        if not frames:
            return pd.DataFrame(columns=["ticker", "short_balance", "short_ratio"])

        combined = pd.concat(frames)
        combined.index.name = "ticker"
        combined = combined.reset_index()
        combined = combined.rename(columns={"공매도잔고": "short_balance", "비중": "short_ratio"})
        return combined.reindex(columns=["ticker", "short_balance", "short_ratio"])
