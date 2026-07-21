"""DART 재무제표 & 공시 수집기 (Stock Miner 전체 유니버스용).

info/news/dart_collector.py(T060)와 동일한 OpenDartReader 인스턴스 재사용
패턴을 따르되, 조회 대상을 SK하이닉스 단일 종목에서 전체 유니버스로
확장한다. 재무제표는 분기당 1회만 갱신되므로 parquet로 캐싱한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import OpenDartReader
import pandas as pd
import pytz

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

_DEFAULT_CACHE_DIR = Path("screener/data/cache")

# T060의 IMPORTANT_REPORT_TYPES와 취지는 같으나, 전체 유니버스 스크리닝에
# 맞춰 자사주 취득/처분·무상증자 등을 추가한 별도 집합.
IMPORTANT_DISCLOSURE_TYPES = {
    "자기주식취득결정",
    "자기주식처분결정",
    "유상증자결정",
    "무상증자결정",
    "전환사채권발행결정",
    "주식관련사채권발행결정",
    "주요사항보고서",
    "단일판매ㆍ공급계약체결",
    "실적정정",
}

# finstate_all() 응답의 account_nm 값 매핑 — 여러 표기 변형을 허용한다.
_ACCOUNT_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("매출액", "수익(매출액)"),
    "operating_income": ("영업이익", "영업이익(손실)"),
    "net_income": ("당기순이익", "당기순이익(손실)", "반기순이익", "분기순이익"),
    "total_liabilities": ("부채총계",),
    "current_assets": ("유동자산",),
    "current_liabilities": ("유동부채",),
    "operating_cash_flow": ("영업활동현금흐름", "영업활동으로인한현금흐름"),
}


@dataclass(frozen=True)
class YearlyFinancials:
    """한 회계연도의 핵심 재무 항목. 조회 실패 항목은 None."""

    year: int
    revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    total_liabilities: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    operating_cash_flow: float | None = None


@dataclass(frozen=True)
class FinancialStatement:
    """기업의 최근 N개년 재무제표."""

    corp_code: str
    years: list[YearlyFinancials]


@dataclass(frozen=True)
class Disclosure:
    """중요 공시 1건."""

    corp_code: str
    title: str
    url: str
    report_type: str
    published_kst: datetime


def _quarter_key(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(tz=KST)
    return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"


def _to_float(raw: object) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None


class DartClient:
    """DART 재무제표·공시 수집기 (전체 유니버스 대상)."""

    def __init__(self, api_key: str, cache_dir: Path | str = _DEFAULT_CACHE_DIR) -> None:
        self._api_key = api_key
        self._cache_dir = Path(cache_dir)

    # ------------------------------------------------------------------
    # 재무제표
    # ------------------------------------------------------------------

    async def fetch_financials(self, corp_code: str, years: int = 3) -> FinancialStatement:
        """최근 `years`개년 핵심 재무 항목을 조회한다 (분기 캐시 적용).

        Args:
            corp_code: DART 고유 회사코드 (8자리).
            years: 조회할 연도 수.

        Returns:
            FinancialStatement. API 장애 시 years=[] 로 반환 (예외 미전파).
        """
        cache_path = self._cache_path(corp_code)
        if cache_path.exists():
            return self._load_cache(cache_path, corp_code)

        loop = asyncio.get_running_loop()
        try:
            stmt = await loop.run_in_executor(
                None, self._fetch_financials_sync, corp_code, years
            )
        except Exception as exc:
            logger.error("DART 재무제표 조회 실패(%s): %s", corp_code, exc)
            return FinancialStatement(corp_code=corp_code, years=[])

        if stmt.years:
            self._save_cache(cache_path, stmt)
        return stmt

    def _cache_path(self, corp_code: str) -> Path:
        return self._cache_dir / f"{corp_code}_financials_{_quarter_key()}.parquet"

    def _load_cache(self, path: Path, corp_code: str) -> FinancialStatement:
        df = pd.read_parquet(path)
        years = []
        for row in df.to_dict(orient="records"):
            row["year"] = int(row["year"])
            for key, val in row.items():
                if key != "year" and pd.isna(val):
                    row[key] = None
            years.append(YearlyFinancials(**row))
        return FinancialStatement(corp_code=corp_code, years=years)

    def _save_cache(self, path: Path, stmt: FinancialStatement) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([vars(y) for y in stmt.years])
        df.to_parquet(path)

    def _fetch_financials_sync(self, corp_code: str, years: int) -> FinancialStatement:
        dart = OpenDartReader(self._api_key)
        current_year = datetime.now(tz=KST).year

        results: list[YearlyFinancials] = []
        for offset in range(1, years + 1):
            year = current_year - offset
            try:
                df = dart.finstate_all(corp_code, str(year))
            except Exception as exc:
                logger.warning("DART finstate_all 조회 실패(%s, %s년): %s", corp_code, year, exc)
                continue
            if df is None or df.empty:
                continue
            results.append(self._parse_year(year, df))

        return FinancialStatement(corp_code=corp_code, years=results)

    def _parse_year(self, year: int, df: pd.DataFrame) -> YearlyFinancials:
        def lookup(field: str) -> float | None:
            for name in _ACCOUNT_ALIASES[field]:
                match = df[df["account_nm"] == name]
                if not match.empty:
                    return _to_float(match.iloc[0].get("thstrm_amount"))
            return None

        return YearlyFinancials(
            year=year,
            revenue=lookup("revenue"),
            operating_income=lookup("operating_income"),
            net_income=lookup("net_income"),
            total_liabilities=lookup("total_liabilities"),
            current_assets=lookup("current_assets"),
            current_liabilities=lookup("current_liabilities"),
            operating_cash_flow=lookup("operating_cash_flow"),
        )

    # ------------------------------------------------------------------
    # 공시
    # ------------------------------------------------------------------

    async def fetch_recent_disclosures(self, corp_code: str, days: int = 30) -> list[Disclosure]:
        """최근 `days`일 내 중요 공시를 조회한다.

        API 장애 시 빈 리스트를 반환한다 (전체 파이프라인 중단 방지 —
        T060과 동일한 장애 격리 원칙).
        """
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None, self._fetch_disclosures_sync, corp_code, days
            )
        except Exception as exc:
            logger.error("DART 공시 조회 실패(%s): %s", corp_code, exc)
            return []

    def _fetch_disclosures_sync(self, corp_code: str, days: int) -> list[Disclosure]:
        dart = OpenDartReader(self._api_key)

        today = datetime.now(tz=KST).strftime("%Y%m%d")
        start = (datetime.now(tz=KST) - timedelta(days=days)).strftime("%Y%m%d")

        raw = dart.list(corp_code, bgn_de=start, end_de=today)
        if raw is None or len(raw) == 0:
            return []

        items: list[Disclosure] = []
        for _, row in raw.iterrows():
            report_nm = str(row.get("report_nm", ""))
            matched_type = next(
                (rtype for rtype in IMPORTANT_DISCLOSURE_TYPES if rtype in report_nm), None
            )
            if matched_type is None:
                continue

            rcept_dt = str(row.get("rcept_dt", ""))
            try:
                pub_dt = datetime.strptime(rcept_dt, "%Y%m%d").replace(tzinfo=KST)
            except ValueError:
                pub_dt = datetime.now(tz=KST)

            rcp_no = str(row.get("rcept_no", ""))
            items.append(
                Disclosure(
                    corp_code=corp_code,
                    title=report_nm,
                    url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp_no}",
                    report_type=matched_type,
                    published_kst=pub_dt,
                )
            )

        return items
