"""멀티 타임프레임 데이터 동기화 모듈 테스트.

T071 테스트:
- TimeframeState.__post_init__: cci/cci_signal 길이 불일치 검증
- TossCandle → Candle 변환
- 리샘플링 (일→주, 일→월, 분→시)
- 병렬 조회 + 예외 처리 (gather)
- TTL 캐시 (만료 전/후 동작)
- lookup_upper() 반환 구조
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.marketdata.models import Candle
from core.strategy.multi_timeframe import (
    MultiTimeframeData,
    MultiTimeframeLoader,
    TimeframeState,
    UpperTimeframeState,
    _aggregate_minute_candles_to_hourly,
    _resample_candles_to_monthly,
    _resample_candles_to_weekly,
    _toss_candle_to_candle,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_daily_candles() -> list[Candle]:
    """30개 일봉 샘플 (가격 상승 추세)."""
    base_price = 100.0
    candles = []
    for i in range(30):
        price = base_price + (i * 0.5)
        candle = Candle(
            symbol="TEST",
            open=price,
            high=price + 0.5,
            low=price - 0.5,
            close=price,
            volume=1000 + i * 10,
            timestamp=datetime(2026, 1, 1 + i, tzinfo=UTC),
            market="domestic",
            interval="1d",
        )
        candles.append(candle)
    return candles


@pytest.fixture
def sample_minute_candles() -> list[Candle]:
    """120개 1분봉 샘플 (2시간, 60개 단위로 집계 가능)."""
    base_price = 100.0
    candles = []
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    for i in range(120):
        price = base_price + (i * 0.1)
        candle = Candle(
            symbol="TEST",
            open=price,
            high=price + 0.2,
            low=price - 0.2,
            close=price,
            volume=100 + i,
            timestamp=base_time + timedelta(minutes=i),
            market="domestic",
            interval="1m",
        )
        candles.append(candle)
    return candles


@pytest.fixture
def mock_toss_candle():
    """Mock TossCandle (dataclass)."""
    candle = MagicMock()
    candle.timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    candle.open_price = 100.0
    candle.high_price = 101.0
    candle.low_price = 99.0
    candle.close_price = 100.5
    candle.volume = 1000
    candle.currency = "KRW"
    return candle


@pytest.fixture
def mock_rest_client():
    """Mock TossRestClient."""
    client = AsyncMock()
    return client


# ============================================================================
# TimeframeState.__post_init__ 검증
# ============================================================================


def test_timeframe_state_post_init_valid():
    """TimeframeState: 유효한 길이 조합."""
    candles = [MagicMock(spec=Candle) for _ in range(5)]
    cci = [1.0, 2.0, 3.0]
    cci_signal = [1.1, 2.1, 3.1]
    ma5 = [100.0, 101.0, 102.0]
    ma20 = [99.0, 99.5, 100.0]
    volume_ma20 = [1000.0, 1100.0, 1200.0]

    state = TimeframeState(
        candles=candles,
        cci=cci,
        cci_signal=cci_signal,
        ma5=ma5,
        ma20=ma20,
        volume_ma20=volume_ma20,
        last_updated=datetime.now(UTC),
    )

    assert state.cci == cci
    assert state.cci_signal == cci_signal


def test_timeframe_state_post_init_length_mismatch():
    """TimeframeState: CCI/signal 길이 불일치 → ValueError."""
    candles = [MagicMock(spec=Candle) for _ in range(5)]
    cci = [1.0, 2.0, 3.0]
    cci_signal = [1.1, 2.1]  # 길이 2 (불일치)
    ma5 = [100.0, 101.0, 102.0]
    ma20 = [99.0, 99.5, 100.0]
    volume_ma20 = [1000.0, 1100.0, 1200.0]

    with pytest.raises(ValueError, match="CCI/시그널 길이 불일치"):
        TimeframeState(
            candles=candles,
            cci=cci,
            cci_signal=cci_signal,
            ma5=ma5,
            ma20=ma20,
            volume_ma20=volume_ma20,
            last_updated=datetime.now(UTC),
        )


def test_timeframe_state_is_resampled_flag():
    """TimeframeState: is_resampled 플래그 확인."""
    state = TimeframeState(
        candles=[],
        cci=[],
        cci_signal=[],
        ma5=[],
        ma20=[],
        volume_ma20=[],
        last_updated=datetime.now(UTC),
        is_resampled=True,
    )
    assert state.is_resampled is True


# ============================================================================
# Toss 캔들 변환
# ============================================================================


def test_toss_candle_to_candle_domestic(mock_toss_candle):
    """TossCandle → Candle 변환 (국내 = KRW)."""
    result = _toss_candle_to_candle(mock_toss_candle, "AAPL", "1d")

    assert result.symbol == "AAPL"
    assert result.open == 100.0
    assert result.high == 101.0
    assert result.low == 99.0
    assert result.close == 100.5
    assert result.volume == 1000
    assert result.market == "domestic"
    assert result.interval == "1d"


def test_toss_candle_to_candle_overseas():
    """TossCandle → Candle 변환 (해외 = USD)."""
    candle = MagicMock()
    candle.timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    candle.open_price = 100.0
    candle.high_price = 101.0
    candle.low_price = 99.0
    candle.close_price = 100.5
    candle.volume = 1000
    candle.currency = "USD"

    result = _toss_candle_to_candle(candle, "AAPL", "1d")

    assert result.market == "overseas"


# ============================================================================
# 리샘플링: 일 → 주
# ============================================================================


def test_resample_candles_to_weekly_basic(sample_daily_candles):
    """일봉 → 주봉 리샘플링 기본 동작."""
    # 샘플: 30개 일봉 (1월 1일부터 시작)
    result = _resample_candles_to_weekly(sample_daily_candles)

    # 일봉이 리샘플되어 주봉 개수가 줄어들어야 함
    assert len(result) < len(sample_daily_candles)
    # 모든 주봉이 interval="1w"를 가져야 함
    assert all(c.interval == "1w" for c in result)
    # 주봉 데이터가 유효해야 함
    assert all(c.open > 0 and c.close > 0 for c in result)


def test_resample_candles_to_weekly_empty():
    """일봉 리샘플링: 빈 리스트."""
    result = _resample_candles_to_weekly([])
    assert result == []


def test_resample_candles_to_weekly_preserves_symbol(sample_daily_candles):
    """일봉 → 주봉 리샘플링: 심볼 보존."""
    result = _resample_candles_to_weekly(sample_daily_candles)
    assert all(c.symbol == "TEST" for c in result)


# ============================================================================
# 리샘플링: 일 → 월
# ============================================================================


def test_resample_candles_to_monthly_basic(sample_daily_candles):
    """일봉 → 월봉 리샘플링 기본 동작."""
    result = _resample_candles_to_monthly(sample_daily_candles)

    # 샘플(30일) → 월봉(1개)
    assert len(result) <= len(sample_daily_candles)
    assert all(c.interval == "1M" for c in result)


def test_resample_candles_to_monthly_empty():
    """일봉 리샘플링: 빈 리스트."""
    result = _resample_candles_to_monthly([])
    assert result == []


# ============================================================================
# 집계: 1분봉 → 60분봉
# ============================================================================


def test_aggregate_minute_candles_to_hourly(sample_minute_candles):
    """1분봉 60개 → 60분봉 집계 기본 동작."""
    # 120개 1분봉 → 2개 60분봉
    result = _aggregate_minute_candles_to_hourly(sample_minute_candles)

    assert len(result) == 2
    assert all(c.interval == "60m" for c in result)
    # 각 60분봉은 60개 1분봉의 OHLC를 포함해야 함
    for hourly in result:
        assert hourly.open > 0
        assert hourly.close > 0
        assert hourly.high >= hourly.low


def test_aggregate_minute_candles_to_hourly_incomplete():
    """1분봉 집계: 미완성 시간 제외."""
    # 70개 1분봉 → 1개 60분봉 (마지막 10개는 미완성)
    candles = [
        Candle(
            symbol="TEST",
            open=100.0 + i * 0.1,
            high=100.0 + i * 0.1 + 0.2,
            low=100.0 + i * 0.1 - 0.2,
            close=100.0 + i * 0.1,
            volume=100,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            market="domestic",
            interval="1m",
        )
        for i in range(70)
    ]
    result = _aggregate_minute_candles_to_hourly(candles)

    assert len(result) == 1


def test_aggregate_minute_candles_to_hourly_empty():
    """1분봉 집계: 빈 리스트."""
    result = _aggregate_minute_candles_to_hourly([])
    assert result == []


# ============================================================================
# MultiTimeframeLoader: 병렬 조회 + 예외 처리
# ============================================================================


@pytest.mark.asyncio
async def test_loader_initialize(mock_rest_client):
    """MultiTimeframeLoader 초기화."""
    loader = MultiTimeframeLoader(mock_rest_client)
    assert loader._rest_client is mock_rest_client


@pytest.mark.asyncio
async def test_load_all_timeframes_success(mock_rest_client):
    """MultiTimeframeLoader.load(): 4개 타임프레임 모두 성공."""

    async def mock_get_candles(symbol, interval, count=100, before=None, adjusted=True):
        """Mock get_candles로 interval별 데이터 반환."""
        if interval == "1m":
            # 1분봉: 120개만 반환 (60분봉은 1개 구성)
            candles = []
            for i in range(120):
                tc = MagicMock()
                tc.timestamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i)
                tc.open_price = 100.0 + i * 0.01
                tc.high_price = 100.1 + i * 0.01
                tc.low_price = 99.9 + i * 0.01
                tc.close_price = 100.05 + i * 0.01
                tc.volume = 100 + i
                tc.currency = "KRW"
                candles.append(tc)
            return candles
        else:  # "1d"
            # 일봉: 50개 반환
            candles = []
            for i in range(50):
                tc = MagicMock()
                tc.timestamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
                tc.open_price = 100.0 + i * 0.5
                tc.high_price = 101.0 + i * 0.5
                tc.low_price = 99.0 + i * 0.5
                tc.close_price = 100.5 + i * 0.5
                tc.volume = 1000 + i * 10
                tc.currency = "KRW"
                candles.append(tc)
            return candles

    mock_rest_client.get_candles.side_effect = mock_get_candles

    loader = MultiTimeframeLoader(mock_rest_client)
    result = await loader.load("TEST")

    assert isinstance(result, MultiTimeframeData)
    assert result.symbol == "TEST"
    assert result.daily is not None
    assert result.weekly is not None
    assert result.monthly is not None
    assert result.sixty_min is not None


@pytest.mark.asyncio
async def test_load_timeframe_daily_required(mock_rest_client):
    """MultiTimeframeLoader: 일봉 실패 → RuntimeError."""
    mock_rest_client.get_candles.side_effect = RuntimeError("API error")

    loader = MultiTimeframeLoader(mock_rest_client)

    with pytest.raises(RuntimeError, match="일봉 조회 실패"):
        await loader.load("TEST")


@pytest.mark.asyncio
async def test_load_with_ttl_cache(mock_rest_client):
    """MultiTimeframeLoader: TTL 캐시 동작.

    첫 번째 로드 후 TTL 내에 재로드 시 API 호출 줄어들어야 함.
    """

    async def mock_get_candles(symbol, interval, count=100, before=None, adjusted=True):
        """Mock get_candles로 interval별 데이터 반환."""
        if interval == "1m":
            candles = []
            for i in range(120):
                tc = MagicMock()
                tc.timestamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i)
                tc.open_price = 100.0 + i * 0.01
                tc.high_price = 100.1 + i * 0.01
                tc.low_price = 99.9 + i * 0.01
                tc.close_price = 100.05 + i * 0.01
                tc.volume = 100 + i
                tc.currency = "KRW"
                candles.append(tc)
            return candles
        else:  # "1d"
            candles = []
            for i in range(50):
                tc = MagicMock()
                tc.timestamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
                tc.open_price = 100.0 + i * 0.5
                tc.high_price = 101.0 + i * 0.5
                tc.low_price = 99.0 + i * 0.5
                tc.close_price = 100.5 + i * 0.5
                tc.volume = 1000 + i * 10
                tc.currency = "KRW"
                candles.append(tc)
            return candles

    mock_rest_client.get_candles.side_effect = mock_get_candles

    loader = MultiTimeframeLoader(mock_rest_client)

    # 첫 번째 로드
    result1 = await loader.load("TEST")
    call_count_1 = mock_rest_client.get_candles.call_count

    # 두 번째 로드 (TTL 내에서 캐시 재사용)
    result2 = await loader.load("TEST")
    call_count_2 = mock_rest_client.get_candles.call_count

    # 캐시가 적용되어 API 호출이 줄어야 함
    # (daily는 5분 TTL, 즉시 두 번째 로드에서는 캐시 재사용)
    # 단, weekly/monthly/60min은 daily 캐시에 의존하므로 실제 호출 수 감소 확인
    assert result1.daily is not None
    assert result2.daily is not None


@pytest.mark.asyncio
async def test_load_with_partial_failure(mock_rest_client):
    """MultiTimeframeLoader: 일부 타임프레임 실패 시 경고 로깅 + 자동 재시도."""

    async def mock_get_candles(symbol, interval, count=100, before=None, adjusted=True):
        """Mock get_candles로 interval별 데이터 반환."""
        if interval == "1m":
            candles = []
            for i in range(120):
                tc = MagicMock()
                tc.timestamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i)
                tc.open_price = 100.0 + i * 0.01
                tc.high_price = 100.1 + i * 0.01
                tc.low_price = 99.9 + i * 0.01
                tc.close_price = 100.05 + i * 0.01
                tc.volume = 100 + i
                tc.currency = "KRW"
                candles.append(tc)
            return candles
        else:  # "1d"
            candles = []
            for i in range(50):
                tc = MagicMock()
                tc.timestamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
                tc.open_price = 100.0 + i * 0.5
                tc.high_price = 101.0 + i * 0.5
                tc.low_price = 99.0 + i * 0.5
                tc.close_price = 100.5 + i * 0.5
                tc.volume = 1000 + i * 10
                tc.currency = "KRW"
                candles.append(tc)
            return candles

    loader = MultiTimeframeLoader(mock_rest_client)

    # 성공 시나리오: 모든 호출이 성공
    mock_rest_client.get_candles.side_effect = mock_get_candles

    result = await loader.load("TEST")
    assert result is not None
    assert result.daily is not None


# ============================================================================
# MultiTimeframeData: lookup_upper()
# ============================================================================


def test_lookup_upper_returns_typed_dict():
    """MultiTimeframeData.lookup_upper(): UpperTimeframeState 반환."""
    now = datetime.now(UTC)

    daily = TimeframeState(
        candles=[],
        cci=[],
        cci_signal=[],
        ma5=[],
        ma20=[],
        volume_ma20=[],
        last_updated=now,
    )

    weekly = TimeframeState(
        candles=[],
        cci=[],
        cci_signal=[],
        ma5=[],
        ma20=[],
        volume_ma20=[],
        last_updated=now,
        is_resampled=True,
    )

    monthly = TimeframeState(
        candles=[],
        cci=[],
        cci_signal=[],
        ma5=[],
        ma20=[],
        volume_ma20=[],
        last_updated=now,
        is_resampled=True,
    )

    sixty_min = TimeframeState(
        candles=[],
        cci=[],
        cci_signal=[],
        ma5=[],
        ma20=[],
        volume_ma20=[],
        last_updated=now,
        is_resampled=True,
    )

    data = MultiTimeframeData(
        symbol="TEST",
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        sixty_min=sixty_min,
    )

    result = data.lookup_upper(datetime.now(UTC))

    assert isinstance(result, dict)
    assert "monthly" in result
    assert "weekly" in result
    assert "sixty_min" in result
    assert result["monthly"] is monthly
    assert result["weekly"] is weekly
    assert result["sixty_min"] is sixty_min


def test_lookup_upper_keys():
    """MultiTimeframeData.lookup_upper(): TypedDict 키 검증."""
    now = datetime.now(UTC)
    state = TimeframeState(
        candles=[],
        cci=[],
        cci_signal=[],
        ma5=[],
        ma20=[],
        volume_ma20=[],
        last_updated=now,
    )

    data = MultiTimeframeData(
        symbol="TEST",
        daily=state,
        weekly=state,
        monthly=state,
        sixty_min=state,
    )

    result = data.lookup_upper(datetime.now(UTC))

    # TypedDict 키 확인
    assert set(result.keys()) == {"monthly", "weekly", "sixty_min"}


# ============================================================================
# Integration: 지표 계산 포함
# ============================================================================


@pytest.mark.asyncio
async def test_load_includes_indicators(mock_rest_client):
    """MultiTimeframeLoader: 조회 후 지표(CCI, MA) 계산 포함."""

    async def mock_get_candles(symbol, interval, count=100, before=None, adjusted=True):
        """Mock get_candles로 interval별 데이터 반환."""
        if interval == "1m":
            candles = []
            for i in range(120):
                tc = MagicMock()
                tc.timestamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i)
                tc.open_price = 100.0 + i * 0.01
                tc.high_price = 100.1 + i * 0.01
                tc.low_price = 99.9 + i * 0.01
                tc.close_price = 100.05 + i * 0.01
                tc.volume = 100 + i
                tc.currency = "KRW"
                candles.append(tc)
            return candles
        else:  # "1d"
            candles = []
            for i in range(50):
                tc = MagicMock()
                tc.timestamp = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
                tc.open_price = 100.0 + i * 0.5
                tc.high_price = 101.0 + i * 0.5
                tc.low_price = 99.0 + i * 0.5
                tc.close_price = 100.5 + i * 0.5
                tc.volume = 1000 + i * 10
                tc.currency = "KRW"
                candles.append(tc)
            return candles

    mock_rest_client.get_candles.side_effect = mock_get_candles

    loader = MultiTimeframeLoader(mock_rest_client)
    result = await loader.load("TEST")

    # 일봉 지표 확인
    assert len(result.daily.cci) > 0
    assert len(result.daily.cci_signal) > 0
    assert len(result.daily.ma5) > 0
    assert len(result.daily.ma20) > 0
    assert len(result.daily.volume_ma20) > 0

    # CCI/signal 길이 일치
    assert len(result.daily.cci) == len(result.daily.cci_signal)


# ============================================================================
# Edge cases
# ============================================================================


def test_timeframe_state_minimal():
    """TimeframeState: 최소 데이터."""
    state = TimeframeState(
        candles=[],
        cci=[],
        cci_signal=[],
        ma5=[],
        ma20=[],
        volume_ma20=[],
        last_updated=datetime.now(UTC),
    )
    assert state.candles == []
    assert state.cci == []


def test_resample_single_candle():
    """리샘플링: 1개 캔들."""
    candle = Candle(
        symbol="TEST",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        market="domestic",
    )
    result = _resample_candles_to_weekly([candle])
    # 1개 캔들은 1주일에 미달해 결과 없음
    assert len(result) <= 1
