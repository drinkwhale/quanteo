"""멀티 타임프레임 데이터 동기화 모듈.

일봉·주봉·월봉·60분봉의 OHLCV·지표를 동시 관리하고,
특정 일봉 시점의 상위 타임프레임 상태를 조회하는 기능을 제공한다.

T071 구현:
- TimeframeState: 타임프레임별 데이터(캔들·지표·TTL 캐시)
- MultiTimeframeLoader: 병렬 조회·리샘플링·예외 처리
- MultiTimeframeData: 4개 타임프레임 통합 관리 + lookup_upper()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pandas as pd

from core.adapters.toss.rest import TossRestClient
from core.marketdata.models import Candle
from core.strategy.indicators.cci import calculate_cci, calculate_cci_signal
from core.strategy.indicators.ma import calculate_sma

logger = logging.getLogger(__name__)


# ============================================================================
# TimeframeState: 타임프레임별 데이터 + 검증
# ============================================================================


@dataclass
class TimeframeState:
    """타임프레임 상태.

    Attributes:
        candles: Candle 리스트 (오래된 것부터 최신 순).
        cci: CCI 값 리스트.
        cci_signal: CCI 시그널 라인 리스트.
        ma5: 5일 이동평균 리스트.
        ma20: 20일 이동평균 리스트.
        volume_ma20: 거래량 20기간 이동평균 리스트.
        last_updated: 마지막 업데이트 시각.
        is_resampled: 리샘플링된 데이터 여부 (주봉·월봉·60분봉 등).
        is_empty: API 장애 + 이전 캐시 없음으로 데이터 사용 불가 상태.
    """

    candles: list[Candle]
    cci: list[float]
    cci_signal: list[float]
    ma5: list[float]
    ma20: list[float]
    volume_ma20: list[float]
    last_updated: datetime
    is_resampled: bool = False
    is_empty: bool = False

    def __post_init__(self) -> None:
        """배열 정렬 및 지표 존재 검증."""
        if len(self.cci) != len(self.cci_signal):
            raise ValueError(
                f"CCI/시그널 길이 불일치: cci={len(self.cci)}, signal={len(self.cci_signal)}"
            )
        # 충분한 캔들이 있으면 이동평균 배열도 반드시 존재해야 함
        if len(self.candles) >= 20 and not self.ma20:
            raise ValueError("20개 이상 캔들에서 ma20이 비어있음 — 지표 계산 오류")
        if len(self.candles) >= 5 and not self.ma5:
            raise ValueError("5개 이상 캔들에서 ma5가 비어있음 — 지표 계산 오류")


# ============================================================================
# 캐시 엔트리
# ============================================================================


@dataclass
class _CachedState:
    """TTL 캐시된 TimeframeState."""

    state: TimeframeState
    expires_at: datetime


# ============================================================================
# Toss 캔들 변환 헬퍼
# ============================================================================


def _toss_candle_to_candle(
    toss_candle,  # TossCandle (타입 순환참조 방지)
    symbol: str,
    interval: str,
) -> Candle:
    """TossCandle → Candle 변환."""
    market = "domestic" if toss_candle.currency == "KRW" else "overseas"
    return Candle(
        symbol=symbol,
        open=float(toss_candle.open_price),
        high=float(toss_candle.high_price),
        low=float(toss_candle.low_price),
        close=float(toss_candle.close_price),
        volume=toss_candle.volume,
        timestamp=toss_candle.timestamp,
        market=market,
        interval=interval,
    )


# ============================================================================
# 리샘플링 유틸리티
# ============================================================================


def _resample_candles_to_weekly(daily_candles: list[Candle]) -> list[Candle]:
    """일봉 → 주봉 리샘플링 (월요일 시작 주간 W-MON)."""
    if not daily_candles:
        return []

    df = pd.DataFrame(
        [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in daily_candles
        ]
    ).set_index("timestamp")

    weekly = df.resample("W-MON").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()

    symbol = daily_candles[0].symbol
    return [
        Candle(
            symbol=symbol,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]),
            timestamp=pd.Timestamp(ts).to_pydatetime().replace(tzinfo=UTC),
            market=daily_candles[0].market,
            interval="1w",
        )
        for ts, row in weekly.iterrows()
    ]


def _resample_candles_to_monthly(daily_candles: list[Candle]) -> list[Candle]:
    """일봉 → 월봉 리샘플링 (월 단위 ME)."""
    if not daily_candles:
        return []

    df = pd.DataFrame(
        [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in daily_candles
        ]
    ).set_index("timestamp")

    monthly = df.resample("ME").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()

    symbol = daily_candles[0].symbol
    return [
        Candle(
            symbol=symbol,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]),
            timestamp=pd.Timestamp(ts).to_pydatetime().replace(tzinfo=UTC),
            market=daily_candles[0].market,
            interval="1M",
        )
        for ts, row in monthly.iterrows()
    ]


def _aggregate_minute_candles_to_hourly(minute_candles: list[Candle]) -> list[Candle]:
    """1분봉 60개 → 60분봉 집계 (60개씩 그룹화, 미완성 시간 제외)."""
    if not minute_candles:
        return []

    hourly_candles = []
    for i in range(0, len(minute_candles), 60):
        chunk = minute_candles[i : i + 60]
        if len(chunk) < 60:
            break

        hourly_candles.append(
            Candle(
                symbol=chunk[0].symbol,
                open=chunk[0].open,
                high=max(c.high for c in chunk),
                low=min(c.low for c in chunk),
                close=chunk[-1].close,
                volume=sum(c.volume for c in chunk),
                timestamp=chunk[0].timestamp,
                market=chunk[0].market,
                interval="60m",
            )
        )

    return hourly_candles


# ============================================================================
# 지표 계산 헬퍼
# ============================================================================


def _compute_timeframe_state(
    candles: list[Candle],
    now: datetime,
    is_resampled: bool,
) -> TimeframeState:
    """캔들로부터 CCI·MA 지표를 계산하고 TimeframeState를 생성한다."""
    close_prices = [c.close for c in candles]
    volumes = [c.volume for c in candles]

    cci_raw = calculate_cci(candles, period=20)
    cci_signal = calculate_cci_signal(cci_raw, signal_period=20)

    if not cci_signal:
        # CCI(period=20) + signal(period=20) = 최소 40개 캔들 필요
        logger.warning(
            "CCI 시그널 계산 불가 — 최소 40개 캔들 필요 (현재 %d개)", len(candles)
        )
        cci = []
    else:
        # cci_signal이 더 짧으므로 cci 앞쪽을 trimming해 길이 맞춤
        cci = cci_raw[-len(cci_signal):]

    return TimeframeState(
        candles=candles,
        cci=cci,
        cci_signal=cci_signal,
        ma5=calculate_sma(close_prices, period=5),
        ma20=calculate_sma(close_prices, period=20),
        volume_ma20=calculate_sma(volumes, period=20),
        last_updated=now,
        is_resampled=is_resampled,
    )


# ============================================================================
# MultiTimeframeLoader: 병렬 조회 + 리샘플링 + 예외 처리
# ============================================================================


class MultiTimeframeLoader:
    """4개 타임프레임 병렬 조회 및 지표 계산."""

    # TTL (캐시 만료 시간)
    _TTL_MONTHLY = timedelta(hours=1)
    _TTL_WEEKLY = timedelta(minutes=30)
    _TTL_DAILY = timedelta(minutes=5)
    _TTL_60MIN = timedelta(minutes=1)

    def __init__(self, rest_client: TossRestClient) -> None:
        """초기화.

        Args:
            rest_client: TossRestClient 인스턴스.
        """
        self._rest_client = rest_client
        # 캐시: symbol → timeframe → _CachedState
        self._cache: dict[str, dict[str, _CachedState]] = {}

    async def load(self, symbol: str) -> MultiTimeframeData:
        """4개 타임프레임 데이터 로드 및 지표 계산.

        TTL 캐시를 활용해 필요한 타임프레임만 조회한다.

        Args:
            symbol: 종목 심볼.

        Returns:
            MultiTimeframeData (4개 TimeframeState 포함).
        """
        now = datetime.now(UTC)

        if symbol not in self._cache:
            self._cache[symbol] = {}

        # Step 1: daily 먼저 직렬 확정
        # weekly/monthly는 daily 캔들을 리샘플링하므로 daily 캐시 준비 후 실행해야 함
        daily_raw = (
            await asyncio.gather(
                self._load_timeframe(symbol, "daily", now),
                return_exceptions=True,
            )
        )[0]

        # Step 2: 나머지 3개 병렬 실행 (daily 캐시 준비 완료)
        secondary = await asyncio.gather(
            self._load_timeframe(symbol, "weekly", now),
            self._load_timeframe(symbol, "monthly", now),
            self._load_timeframe(symbol, "60min", now),
            return_exceptions=True,
        )

        tf_names = ["daily", "weekly", "monthly", "60min"]
        all_results: list = [daily_raw, *secondary]

        # 성공 결과 추출
        states: dict[str, TimeframeState | None] = {
            name: (r if not isinstance(r, Exception) else None)
            for name, r in zip(tf_names, all_results)
        }

        # 실패한 타임프레임: 이전 캐시 보존 (TTL 만료도 재사용)
        for name, result in zip(tf_names, all_results):
            if not isinstance(result, Exception):
                continue
            prev = self._cache[symbol].get(name)
            if prev is not None:
                states[name] = prev.state
                logger.warning(
                    "T071: %s 로드 실패, stale 캐시 유지 (symbol=%s, error=%s)",
                    name,
                    symbol,
                    result,
                )
            else:
                logger.warning(
                    "T071: %s 로드 실패, 이전 캐시 없음 (symbol=%s, error=%s)",
                    name,
                    symbol,
                    result,
                )

        # 일봉은 필수 (critical)
        if states["daily"] is None:
            raise RuntimeError(f"일봉 조회 실패 (symbol={symbol})")

        # 주봉/월봉/60분봉 없으면 빈 상태 (is_empty=True)로 대체
        # is_empty=True는 "API 장애 + 이전 캐시 없음"을 의미
        # TimeframeJudge가 일반 데이터 부족(NEUTRAL)과 구분해 로깅할 수 있음
        for name in ("weekly", "monthly", "60min"):
            if states[name] is None:
                logger.warning(
                    "T071: %s 데이터 사용 불가 (symbol=%s, 이전 캐시도 없음)", name, symbol
                )
                states[name] = TimeframeState(
                    candles=[],
                    cci=[],
                    cci_signal=[],
                    ma5=[],
                    ma20=[],
                    volume_ma20=[],
                    last_updated=now,
                    is_resampled=True,
                    is_empty=True,
                )

        return MultiTimeframeData(
            symbol=symbol,
            daily=states["daily"],
            weekly=states["weekly"],
            monthly=states["monthly"],
            sixty_min=states["60min"],
        )

    async def _load_timeframe(
        self,
        symbol: str,
        timeframe: str,
        now: datetime,
    ) -> TimeframeState:
        """단일 타임프레임 조회.

        Args:
            symbol: 종목 심볼.
            timeframe: 타임프레임 ("daily", "weekly", "monthly", "60min").
            now: 현재 시각.

        Returns:
            TimeframeState.

        Raises:
            Exception: API 조회 실패 시.
        """
        # 캐시 확인
        cache_entry = self._cache.get(symbol, {}).get(timeframe)
        if cache_entry and now < cache_entry.expires_at:
            return cache_entry.state

        # 조회 수행
        if timeframe == "daily":
            state = await self._fetch_and_compute_daily(symbol, now)
            ttl = self._TTL_DAILY
        elif timeframe == "weekly":
            state = await self._fetch_and_compute_weekly(symbol, now)
            ttl = self._TTL_WEEKLY
        elif timeframe == "monthly":
            state = await self._fetch_and_compute_monthly(symbol, now)
            ttl = self._TTL_MONTHLY
        elif timeframe == "60min":
            state = await self._fetch_and_compute_60min(symbol, now)
            ttl = self._TTL_60MIN
        else:
            raise ValueError(f"Unknown timeframe: {timeframe}")

        # 캐시 저장
        if symbol not in self._cache:
            self._cache[symbol] = {}
        self._cache[symbol][timeframe] = _CachedState(state, now + ttl)

        return state

    async def _fetch_and_compute_daily(self, symbol: str, now: datetime) -> TimeframeState:
        """일봉 조회 및 지표 계산 (최근 500일)."""
        toss_candles = await self._rest_client.get_candles(
            symbol, interval="1d", count=500, adjusted=True
        )
        candles = [_toss_candle_to_candle(tc, symbol, "1d") for tc in toss_candles]
        return _compute_timeframe_state(candles, now, is_resampled=False)

    async def _fetch_and_compute_weekly(self, symbol: str, now: datetime) -> TimeframeState:
        """주봉 조회 및 지표 계산 (일봉 리샘플링).

        load()에서 daily를 먼저 확정했으므로 daily 캐시가 반드시 유효하다.
        """
        daily_cache = self._cache.get(symbol, {}).get("daily")
        if daily_cache:
            daily_candles = daily_cache.state.candles
        else:
            # load()를 우회한 직접 호출 시 안전망
            daily_state = await self._fetch_and_compute_daily(symbol, now)
            daily_candles = daily_state.candles

        candles = _resample_candles_to_weekly(daily_candles)
        if not candles:
            raise RuntimeError("주봉 리샘플링 실패")

        return _compute_timeframe_state(candles, now, is_resampled=True)

    async def _fetch_and_compute_monthly(self, symbol: str, now: datetime) -> TimeframeState:
        """월봉 조회 및 지표 계산 (일봉 리샘플링).

        load()에서 daily를 먼저 확정했으므로 daily 캐시가 반드시 유효하다.
        """
        daily_cache = self._cache.get(symbol, {}).get("daily")
        if daily_cache:
            daily_candles = daily_cache.state.candles
        else:
            # load()를 우회한 직접 호출 시 안전망
            daily_state = await self._fetch_and_compute_daily(symbol, now)
            daily_candles = daily_state.candles

        candles = _resample_candles_to_monthly(daily_candles)
        if not candles:
            raise RuntimeError("월봉 리샘플링 실패")

        return _compute_timeframe_state(candles, now, is_resampled=True)

    async def _fetch_and_compute_60min(self, symbol: str, now: datetime) -> TimeframeState:
        """60분봉 조회 및 지표 계산 (1분봉 집계)."""
        toss_candles = await self._rest_client.get_candles(
            symbol, interval="1m", count=3600, adjusted=True
        )
        minute_candles = [_toss_candle_to_candle(tc, symbol, "1m") for tc in toss_candles]

        candles = _aggregate_minute_candles_to_hourly(minute_candles)
        if not candles:
            raise RuntimeError("60분봉 집계 실패")

        return _compute_timeframe_state(candles, now, is_resampled=True)


# ============================================================================
# UpperTimeframeState: lookup_upper 반환 타입
# ============================================================================


@dataclass(frozen=True)
class UpperTimeframeState:
    """상위 타임프레임 상태 (lookup_upper 반환).

    frozen dataclass로 불변성 보장.

    Attributes:
        monthly: 월봉 TimeframeState.
        weekly: 주봉 TimeframeState.
        sixty_min: 60분봉 TimeframeState.
    """

    monthly: TimeframeState
    weekly: TimeframeState
    sixty_min: TimeframeState


# ============================================================================
# MultiTimeframeData: 4개 타임프레임 통합 관리
# ============================================================================


@dataclass
class MultiTimeframeData:
    """4개 타임프레임 데이터 통합.

    Attributes:
        symbol: 종목 심볼.
        daily: 일봉 TimeframeState.
        weekly: 주봉 TimeframeState.
        monthly: 월봉 TimeframeState.
        sixty_min: 60분봉 TimeframeState.
    """

    symbol: str
    daily: TimeframeState
    weekly: TimeframeState
    monthly: TimeframeState
    sixty_min: TimeframeState

    def lookup_upper(self, date: datetime) -> UpperTimeframeState:
        """특정 일봉 시점의 상위 타임프레임 상태 반환.

        Args:
            date: 조회 시각.

        Returns:
            UpperTimeframeState (monthly, weekly, sixty_min).
        """
        return UpperTimeframeState(
            monthly=self.monthly,
            weekly=self.weekly,
            sixty_min=self.sixty_min,
        )
