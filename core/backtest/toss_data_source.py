"""Toss 캔들 데이터 소스 & 캐싱.

Protocol 기반 추상화로 실제 Toss API와 CSV 오프라인 소스 모두 지원.
SQLite TTL 캐싱으로 반복 백테스트 시 API 호출 최소화.

T079 구현.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from core.marketdata.models import Candle

logger = logging.getLogger(__name__)

# 캐시 DB 기본 경로 (라이브 시세 캐시와 분리)
_DEFAULT_CACHE_DB = Path.home() / ".quanteo" / "backtest_cache.db"
# 캐시 TTL (24시간)
_CACHE_TTL_HOURS = 24


# ============================================================================
# Protocol
# ============================================================================


class BacktestDataSource(Protocol):
    """백테스트 데이터 소스 Protocol.

    T055 TossRestClient.get_candles() 시그니처와 정렬.
    """

    async def get_candles(
        self,
        symbol: str,
        interval: Literal["1m", "1d"],
        count: int = 100,
        before: str | None = None,
        adjusted: bool = True,
    ) -> list[Candle]: ...

    async def fetch_range(
        self,
        symbol: str,
        interval: Literal["1m", "1d"],
        start_date: datetime,
        end_date: datetime,
    ) -> list[Candle]: ...


# ============================================================================
# SQLite 캐시
# ============================================================================


class _CacheDB:
    """백테스트 전용 SQLite 캐시."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candle_cache (
                cache_key TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                count INTEGER NOT NULL,
                adjusted INTEGER NOT NULL,
                before_ts TEXT,
                data TEXT NOT NULL,
                cached_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _make_key(
        self,
        symbol: str,
        interval: str,
        count: int,
        before: str | None,
        adjusted: bool,
    ) -> str:
        return f"{symbol}:{interval}:{count}:{before or ''}:{int(adjusted)}"

    def get(
        self,
        symbol: str,
        interval: str,
        count: int,
        before: str | None,
        adjusted: bool,
    ) -> list[dict] | None:
        """캐시 조회. TTL 만료 시 None 반환."""
        key = self._make_key(symbol, interval, count, before, adjusted)
        row = self._conn.execute(
            "SELECT data, cached_at FROM candle_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None

        import json

        data_str, cached_at_str = row
        cached_at = datetime.fromisoformat(cached_at_str)
        if datetime.now(UTC) - cached_at > timedelta(hours=_CACHE_TTL_HOURS):
            self._conn.execute("DELETE FROM candle_cache WHERE cache_key = ?", (key,))
            self._conn.commit()
            return None

        return json.loads(data_str)

    def put(
        self,
        symbol: str,
        interval: str,
        count: int,
        before: str | None,
        adjusted: bool,
        candles_data: list[dict],
    ) -> None:
        """캐시 저장."""
        import json

        key = self._make_key(symbol, interval, count, before, adjusted)
        now_str = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO candle_cache
            (cache_key, symbol, interval, count, adjusted, before_ts, data, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (key, symbol, interval, count, int(adjusted), before, json.dumps(candles_data), now_str),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _candle_to_dict(c: Candle) -> dict:
    return {
        "symbol": c.symbol,
        "open": c.open,
        "high": c.high,
        "low": c.low,
        "close": c.close,
        "volume": c.volume,
        "timestamp": c.timestamp.isoformat(),
        "market": c.market,
        "interval": c.interval,
    }


def _dict_to_candle(d: dict) -> Candle:
    return Candle(
        symbol=d["symbol"],
        open=float(d["open"]),
        high=float(d["high"]),
        low=float(d["low"]),
        close=float(d["close"]),
        volume=int(d["volume"]),
        timestamp=datetime.fromisoformat(d["timestamp"]),
        market=d["market"],
        interval=d["interval"],
    )


# ============================================================================
# TossBacktestDataSource
# ============================================================================


class TossBacktestDataSource:
    """Toss API + SQLite 캐시 기반 백테스트 데이터 소스."""

    def __init__(
        self,
        rest_client,  # TossRestClient (순환참조 방지)
        cache_db_path: Path = _DEFAULT_CACHE_DB,
    ) -> None:
        self._rest_client = rest_client
        self._cache = _CacheDB(cache_db_path)

    async def get_candles(
        self,
        symbol: str,
        interval: Literal["1m", "1d"] = "1d",
        count: int = 100,
        before: str | None = None,
        adjusted: bool = True,
    ) -> list[Candle]:
        """캐시 → API 순서로 캔들 반환."""
        # 캐시 조회
        cached = self._cache.get(symbol, interval, count, before, adjusted)
        if cached is not None:
            logger.debug("캐시 히트: symbol=%s interval=%s count=%d", symbol, interval, count)
            return [_dict_to_candle(d) for d in cached]

        # API 조회
        logger.debug("API 조회: symbol=%s interval=%s count=%d", symbol, interval, count)
        try:
            toss_candles = await self._rest_client.get_candles(
                symbol, interval=interval, count=count, before=before, adjusted=adjusted
            )
        except Exception as e:
            logger.error("Toss API 오류 — 캐시 없음 (symbol=%s, error=%s)", symbol, e)
            raise

        # Toss TossCandle → Candle 변환
        candles = self._convert_toss_candles(toss_candles, symbol, interval)

        # 캐시 저장
        self._cache.put(symbol, interval, count, before, adjusted, [_candle_to_dict(c) for c in candles])

        return candles

    async def fetch_range(
        self,
        symbol: str,
        interval: Literal["1m", "1d"] = "1d",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[Candle]:
        """날짜 범위의 캔들 조회.

        `before` 파라미터를 이동하며 여러 번 get_candles()를 호출해 조합한다.
        """
        all_candles: list[Candle] = []
        before: str | None = end_date.isoformat() if end_date else None
        batch_size = 200

        prev_oldest_ts: datetime | None = None
        max_iterations = 500  # 안전장치

        for _ in range(max_iterations):
            batch = await self.get_candles(symbol, interval, count=batch_size, before=before)
            if not batch:
                break

            oldest_ts = batch[0].timestamp

            # 이전 배치와 동일한 oldest timestamp → 더 이상 과거 데이터 없음
            if prev_oldest_ts is not None and oldest_ts >= prev_oldest_ts:
                break
            prev_oldest_ts = oldest_ts

            # 시작일 이전 항목 필터링
            if start_date:
                valid = [c for c in batch if c.timestamp >= start_date]
                all_candles = valid + all_candles
                if len(valid) < len(batch):
                    break  # 시작일 이전 데이터 도달
            else:
                all_candles = batch + all_candles

            # 다음 배치의 before = 현재 배치의 가장 오래된 캔들 타임스탬프
            before = oldest_ts.isoformat()

            # 시작일 없으면 단일 배치로 종료
            if start_date is None:
                break

            # API 과부하 방지
            await asyncio.sleep(0.1)

        return sorted(all_candles, key=lambda c: c.timestamp)

    def _convert_toss_candles(self, toss_candles: list, symbol: str, interval: str) -> list[Candle]:
        """TossCandle 리스트 → Candle 리스트."""
        result = []
        for tc in toss_candles:
            market = "domestic" if getattr(tc, "currency", "KRW") == "KRW" else "overseas"
            result.append(
                Candle(
                    symbol=symbol,
                    open=float(tc.open_price),
                    high=float(tc.high_price),
                    low=float(tc.low_price),
                    close=float(tc.close_price),
                    volume=tc.volume,
                    timestamp=tc.timestamp,
                    market=market,
                    interval=interval,
                )
            )
        return result

    def close(self) -> None:
        self._cache.close()


# ============================================================================
# CSVBacktestDataSource
# ============================================================================


class CSVBacktestDataSource:
    """CSV 파일 기반 오프라인 백테스트 데이터 소스.

    CSV 형식: symbol,open,high,low,close,volume,timestamp,market,interval
    """

    def __init__(self, csv_path: Path, market: str = "domestic", interval: str = "1d") -> None:
        self._csv_path = csv_path
        self._market = market
        self._interval = interval
        self._candles: list[Candle] = []
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        candles = []
        with open(self._csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts_str = row.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                except ValueError:
                    logger.warning("CSV 타임스탬프 파싱 실패: %r", ts_str)
                    continue
                candles.append(
                    Candle(
                        symbol=row.get("symbol", ""),
                        open=float(row.get("open", 0)),
                        high=float(row.get("high", 0)),
                        low=float(row.get("low", 0)),
                        close=float(row.get("close", 0)),
                        volume=int(row.get("volume", 0)),
                        timestamp=ts,
                        market=row.get("market", self._market),
                        interval=row.get("interval", self._interval),
                    )
                )
        self._candles = sorted(candles, key=lambda c: c.timestamp)
        self._loaded = True

    async def get_candles(
        self,
        symbol: str,
        interval: Literal["1m", "1d"] = "1d",
        count: int = 100,
        before: str | None = None,
        adjusted: bool = True,
    ) -> list[Candle]:
        """CSV에서 캔들 반환 (캐싱 불필요)."""
        self._load()
        filtered = [c for c in self._candles if c.symbol == symbol]

        if before:
            try:
                before_dt = datetime.fromisoformat(before)
                filtered = [c for c in filtered if c.timestamp < before_dt]
            except ValueError:
                pass

        return filtered[-count:]

    async def fetch_range(
        self,
        symbol: str,
        interval: Literal["1m", "1d"] = "1d",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[Candle]:
        self._load()
        filtered = [c for c in self._candles if c.symbol == symbol]
        if start_date:
            filtered = [c for c in filtered if c.timestamp >= start_date]
        if end_date:
            filtered = [c for c in filtered if c.timestamp <= end_date]
        return filtered
