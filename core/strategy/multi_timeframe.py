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
from typing import TypedDict

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
    """

    candles: list[Candle]
    cci: list[float]
    cci_signal: list[float]
    ma5: list[float]
    ma20: list[float]
    volume_ma20: list[float]
    last_updated: datetime
    is_resampled: bool = False

    def __post_init__(self) -> None:
        """배열 정렬 검증."""
        if len(self.cci) != len(self.cci_signal):
            raise ValueError(
                f"CCI/시그널 길이 불일치: cci={len(self.cci)}, signal={len(self.cci_signal)}"
            )


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
    """일봉 → 주봉 리샘플링.

    월요일 시작 주간 (W-MON).
    """
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

    # 주간 리샘플링
    weekly = df.resample("W-MON").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    weekly = weekly.dropna()

    # 결과를 Candle로 변환
    candles = []
    symbol = daily_candles[0].symbol if daily_candles else "UNKNOWN"
    for timestamp, row in weekly.iterrows():
        candles.append(
            Candle(
                symbol=symbol,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                timestamp=pd.Timestamp(timestamp).to_pydatetime().replace(tzinfo=UTC),
                market=daily_candles[0].market,
                interval="1w",
            )
        )

    return candles


def _resample_candles_to_monthly(daily_candles: list[Candle]) -> list[Candle]:
    """일봉 → 월봉 리샘플링.

    월 단위 리샘플링 (월초 ~ 월말).
    """
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

    # 월간 리샘플링
    monthly = df.resample("ME").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    monthly = monthly.dropna()

    # 결과를 Candle로 변환
    candles = []
    symbol = daily_candles[0].symbol if daily_candles else "UNKNOWN"
    for timestamp, row in monthly.iterrows():
        candles.append(
            Candle(
                symbol=symbol,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                timestamp=pd.Timestamp(timestamp).to_pydatetime().replace(tzinfo=UTC),
                market=daily_candles[0].market,
                interval="1M",
            )
        )

    return candles


def _aggregate_minute_candles_to_hourly(minute_candles: list[Candle]) -> list[Candle]:
    """1분봉 60개 → 60분봉 집계.

    60개씩 그룹화해 OHLCV 계산.
    """
    if not minute_candles:
        return []

    hourly_candles = []
    for i in range(0, len(minute_candles), 60):
        chunk = minute_candles[i : i + 60]
        if len(chunk) < 60:
            # 미완성 시간 제외
            break

        hourly = Candle(
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
        hourly_candles.append(hourly)

    return hourly_candles


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

        # 심볼별 캐시 초기화
        if symbol not in self._cache:
            self._cache[symbol] = {}

        # 각 타임프레임 조회 태스크
        tasks = [
            self._load_timeframe(symbol, "daily", now),
            self._load_timeframe(symbol, "weekly", now),
            self._load_timeframe(symbol, "monthly", now),
            self._load_timeframe(symbol, "60min", now),
        ]

        # 병렬 실행 (예외는 저장, 전파 안 함)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 매핑 및 예외 처리
        # 개별 타임프레임 실패 시 이전 캐시 사용 (TTL 만료되었어도 유지)
        daily_state = results[0] if not isinstance(results[0], Exception) else None
        weekly_state = results[1] if not isinstance(results[1], Exception) else None
        monthly_state = results[2] if not isinstance(results[2], Exception) else None
        sixty_min_state = results[3] if not isinstance(results[3], Exception) else None

        # 타임프레임별 예외 처리 및 캐시 보존
        tf_names = ["daily", "weekly", "monthly", "60min"]
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tf_name = tf_names[i]
                # 이전 캐시 확인 (TTL 만료 여부 무관)
                prev_cache = self._cache.get(symbol, {}).get(tf_name)

                if prev_cache is not None:
                    # 이전 캐시 사용 (stale cache)
                    if tf_name == "daily":
                        daily_state = prev_cache.state
                    elif tf_name == "weekly":
                        weekly_state = prev_cache.state
                    elif tf_name == "monthly":
                        monthly_state = prev_cache.state
                    elif tf_name == "60min":
                        sixty_min_state = prev_cache.state

                    logger.warning(
                        "T071: %s 타임프레임 로드 실패, 이전 캐시 유지 (symbol=%s, error=%s)",
                        tf_name,
                        symbol,
                        result,
                    )
                else:
                    # 이전 캐시 없음
                    logger.warning(
                        "T071: %s 타임프레임 로드 실패, 이전 캐시 없음 (symbol=%s, error=%s)",
                        tf_name,
                        symbol,
                        result,
                    )

        # 최소 일봉은 필수 (critical)
        if daily_state is None:
            raise RuntimeError(f"일봉 조회 실패 (symbol={symbol})")

        # 주봉/월봉/60분봉이 None이면 빈 TimeframeState 생성
        # (이전 캐시도 없는 경우, non-critical)
        if weekly_state is None:
            logger.warning(
                "T071: 주봉 데이터 사용 불가 (symbol=%s, 이전 캐시도 없음)",
                symbol,
            )
            weekly_state = TimeframeState(
                candles=[],
                cci=[],
                cci_signal=[],
                ma5=[],
                ma20=[],
                volume_ma20=[],
                last_updated=now,
                is_resampled=True,
            )
        if monthly_state is None:
            logger.warning(
                "T071: 월봉 데이터 사용 불가 (symbol=%s, 이전 캐시도 없음)",
                symbol,
            )
            monthly_state = TimeframeState(
                candles=[],
                cci=[],
                cci_signal=[],
                ma5=[],
                ma20=[],
                volume_ma20=[],
                last_updated=now,
                is_resampled=True,
            )
        if sixty_min_state is None:
            logger.warning(
                "T071: 60분봉 데이터 사용 불가 (symbol=%s, 이전 캐시도 없음)",
                symbol,
            )
            sixty_min_state = TimeframeState(
                candles=[],
                cci=[],
                cci_signal=[],
                ma5=[],
                ma20=[],
                volume_ma20=[],
                last_updated=now,
                is_resampled=True,
            )

        return MultiTimeframeData(
            symbol=symbol,
            daily=daily_state,
            weekly=weekly_state,
            monthly=monthly_state,
            sixty_min=sixty_min_state,
        )

    async def _load_timeframe(
        self,
        symbol: str,
        timeframe: str,
        now: datetime,
        skip_cache: bool = False,
    ) -> TimeframeState:
        """단일 타임프레임 조회.

        Args:
            symbol: 종목 심볼.
            timeframe: 타임프레임 ("daily", "weekly", "monthly", "60min").
            now: 현재 시각.
            skip_cache: 캐시 무시 여부.

        Returns:
            TimeframeState.

        Raises:
            Exception: API 조회 실패 시.
        """
        # 캐시 확인
        if not skip_cache:
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
        """일봉 조회 및 지표 계산.

        최근 500일치 조회.
        """
        toss_candles = await self._rest_client.get_candles(
            symbol, interval="1d", count=500, adjusted=True
        )
        candles = [_toss_candle_to_candle(tc, symbol, "1d") for tc in toss_candles]

        # 지표 계산
        close_prices = [c.close for c in candles]
        volumes = [c.volume for c in candles]

        cci = calculate_cci(candles, period=20)
        cci_signal = calculate_cci_signal(cci, signal_period=20)

        # CCI와 signal 길이 정렬 (둘 다 같은 길이로 trimming)
        # signal = cci[20:], cci는 원본 길이 유지하되 signal과 정렬 필요
        # 따라서 둘 다 signal 길이로 통일
        min_cci_signal_len = len(cci_signal)
        cci = cci[-min_cci_signal_len:] if min_cci_signal_len > 0 else []

        ma5 = calculate_sma(close_prices, period=5)
        ma20 = calculate_sma(close_prices, period=20)
        volume_ma20 = calculate_sma(volumes, period=20)

        return TimeframeState(
            candles=candles,
            cci=cci,
            cci_signal=cci_signal,
            ma5=ma5,
            ma20=ma20,
            volume_ma20=volume_ma20,
            last_updated=now,
            is_resampled=False,
        )

    async def _fetch_and_compute_weekly(self, symbol: str, now: datetime) -> TimeframeState:
        """주봉 조회 및 지표 계산.

        현재: 일봉 500개를 주간 리샘플링 (추후 native 지원 시 변경).
        """
        # 일봉 조회 (캐시 사용, TTL 무시)
        daily_cache = self._cache.get(symbol, {}).get("daily")
        if daily_cache and daily_cache.expires_at > now:
            daily_candles = daily_cache.state.candles
        else:
            daily_state = await self._fetch_and_compute_daily(symbol, now)
            daily_candles = daily_state.candles

        # 주봉으로 리샘플링
        candles = _resample_candles_to_weekly(daily_candles)
        if not candles:
            raise RuntimeError("주봉 리샘플링 실패")

        # 지표 계산
        close_prices = [c.close for c in candles]
        volumes = [c.volume for c in candles]

        cci = calculate_cci(candles, period=20)
        cci_signal = calculate_cci_signal(cci, signal_period=20)

        # CCI와 signal 길이 정렬
        min_cci_signal_len = len(cci_signal)
        cci = cci[-min_cci_signal_len:] if min_cci_signal_len > 0 else []

        ma5 = calculate_sma(close_prices, period=5)
        ma20 = calculate_sma(close_prices, period=20)
        volume_ma20 = calculate_sma(volumes, period=20)

        return TimeframeState(
            candles=candles,
            cci=cci,
            cci_signal=cci_signal,
            ma5=ma5,
            ma20=ma20,
            volume_ma20=volume_ma20,
            last_updated=now,
            is_resampled=True,
        )

    async def _fetch_and_compute_monthly(self, symbol: str, now: datetime) -> TimeframeState:
        """월봉 조회 및 지표 계산.

        현재: 일봉 500개를 월간 리샘플링 (추후 native 지원 시 변경).
        """
        # 일봉 조회 (캐시 사용, TTL 무시)
        daily_cache = self._cache.get(symbol, {}).get("daily")
        if daily_cache and daily_cache.expires_at > now:
            daily_candles = daily_cache.state.candles
        else:
            daily_state = await self._fetch_and_compute_daily(symbol, now)
            daily_candles = daily_state.candles

        # 월봉으로 리샘플링
        candles = _resample_candles_to_monthly(daily_candles)
        if not candles:
            raise RuntimeError("월봉 리샘플링 실패")

        # 지표 계산
        close_prices = [c.close for c in candles]
        volumes = [c.volume for c in candles]

        cci = calculate_cci(candles, period=20)
        cci_signal = calculate_cci_signal(cci, signal_period=20)

        # CCI와 signal 길이 정렬
        min_cci_signal_len = len(cci_signal)
        cci = cci[-min_cci_signal_len:] if min_cci_signal_len > 0 else []

        ma5 = calculate_sma(close_prices, period=5)
        ma20 = calculate_sma(close_prices, period=20)
        volume_ma20 = calculate_sma(volumes, period=20)

        return TimeframeState(
            candles=candles,
            cci=cci,
            cci_signal=cci_signal,
            ma5=ma5,
            ma20=ma20,
            volume_ma20=volume_ma20,
            last_updated=now,
            is_resampled=True,
        )

    async def _fetch_and_compute_60min(self, symbol: str, now: datetime) -> TimeframeState:
        """60분봉 조회 및 지표 계산.

        현재: 1분봉 3600개(60시간)를 60분 집계 (추후 native 지원 시 변경).
        """
        toss_candles = await self._rest_client.get_candles(
            symbol, interval="1m", count=3600, adjusted=True
        )
        minute_candles = [_toss_candle_to_candle(tc, symbol, "1m") for tc in toss_candles]

        # 60분 집계
        candles = _aggregate_minute_candles_to_hourly(minute_candles)
        if not candles:
            raise RuntimeError("60분봉 집계 실패")

        # 지표 계산
        close_prices = [c.close for c in candles]
        volumes = [c.volume for c in candles]

        cci = calculate_cci(candles, period=20)
        cci_signal = calculate_cci_signal(cci, signal_period=20)

        # CCI와 signal 길이 정렬
        min_cci_signal_len = len(cci_signal)
        cci = cci[-min_cci_signal_len:] if min_cci_signal_len > 0 else []

        ma5 = calculate_sma(close_prices, period=5)
        ma20 = calculate_sma(close_prices, period=20)
        volume_ma20 = calculate_sma(volumes, period=20)

        return TimeframeState(
            candles=candles,
            cci=cci,
            cci_signal=cci_signal,
            ma5=ma5,
            ma20=ma20,
            volume_ma20=volume_ma20,
            last_updated=now,
            is_resampled=True,
        )


# ============================================================================
# UpperTimeframeState: lookup_upper 반환 타입
# ============================================================================


class UpperTimeframeState(TypedDict):
    """상위 타임프레임 상태 (lookup_upper 반환).

    Keys:
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
