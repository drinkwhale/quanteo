"""타임프레임 계층 방향 판단 모듈 테스트.

월봉 BEARISH 시 거래 금지, 경계값(cci == 0), 데이터 미비 시 NEUTRAL 처리 검증.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.marketdata.models import Candle
from core.strategy.multi_timeframe import MultiTimeframeData, TimeframeState
from core.strategy.timeframe_judge import MarketDirection, TimeframeJudge


@pytest.fixture
def judge() -> TimeframeJudge:
    """TimeframeJudge 인스턴스."""
    return TimeframeJudge()


@pytest.fixture
def sample_candles() -> list[Candle]:
    """테스트용 샘플 캔들 데이터 (25개)."""
    candles = []
    for i in range(25):
        candle = Candle(
            symbol="TEST",
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=1000,
            timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            market="domestic",
            interval="1d",
        )
        candles.append(candle)
    return candles


@pytest.fixture
def sample_timeframe_state(sample_candles) -> TimeframeState:
    """정상 데이터가 있는 TimeframeState."""
    cci_values = [50.0 + i for i in range(20)]  # 20개의 CCI 값
    signal_values = [40.0 + i for i in range(20)]  # 20개의 신호 값
    ma5_values = [100.0 + i for i in range(25)]
    ma20_values = [100.0 + i for i in range(25)]
    volume_ma20_values = [1000.0 + i * 10 for i in range(25)]

    return TimeframeState(
        candles=sample_candles,
        cci=cci_values,
        cci_signal=signal_values,
        ma5=ma5_values,
        ma20=ma20_values,
        volume_ma20=volume_ma20_values,
        last_updated=datetime.now(UTC),
        is_resampled=False,
    )


def test_assess_monthly_bullish(judge, sample_timeframe_state):
    """월봉 BULLISH 조건: cci[-1] > cci_signal[-1] AND cci[-1] > 0."""
    monthly = sample_timeframe_state  # cci[-1]=69, signal[-1]=59, 69 > 59 AND 69 > 0
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=monthly,
        sixty_min=sample_timeframe_state,
    )

    result = judge.assess(mtf)

    assert result["monthly"] == MarketDirection.BULLISH


def test_assess_monthly_bearish_signal_cross(judge, sample_timeframe_state):
    """월봉 BEARISH: cci_signal > cci."""
    # cci_signal > cci인 상태 생성
    modified = TimeframeState(
        candles=sample_timeframe_state.candles,
        cci=[40.0 + i for i in range(20)],  # 낮은 CCI
        cci_signal=[50.0 + i for i in range(20)],  # 높은 signal
        ma5=sample_timeframe_state.ma5,
        ma20=sample_timeframe_state.ma20,
        volume_ma20=sample_timeframe_state.volume_ma20,
        last_updated=sample_timeframe_state.last_updated,
        is_resampled=False,
    )
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=modified,
        sixty_min=sample_timeframe_state,
    )

    result = judge.assess(mtf)

    assert result["monthly"] == MarketDirection.BEARISH


def test_assess_monthly_bearish_negative_cci(judge, sample_timeframe_state):
    """월봉 BEARISH: cci[-1] <= 0."""
    # cci[-1] = -10, signal[-1] = -20
    # cci > signal이지만 cci <= 0이므로 BEARISH
    modified = TimeframeState(
        candles=sample_timeframe_state.candles,
        cci=[-20.0 + i for i in range(20)],  # 마지막: -1
        cci_signal=[-30.0 + i for i in range(20)],  # 마지막: -11
        ma5=sample_timeframe_state.ma5,
        ma20=sample_timeframe_state.ma20,
        volume_ma20=sample_timeframe_state.volume_ma20,
        last_updated=sample_timeframe_state.last_updated,
        is_resampled=False,
    )
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=modified,
        sixty_min=sample_timeframe_state,
    )

    result = judge.assess(mtf)

    assert result["monthly"] == MarketDirection.BEARISH


def test_assess_monthly_boundary_cci_equals_zero(judge, sample_timeframe_state):
    """월봉 경계값: cci[-1] == 0 → BEARISH (not > 0)."""
    # cci[-1] = 0, signal[-1] = -10
    # 0 > -10이지만 0 > 0이 아니므로 BEARISH
    modified = TimeframeState(
        candles=sample_timeframe_state.candles,
        cci=[-10.0 + i for i in range(20)],  # 마지막: 10... no 마지막: -10 + 19 = 9? 아 이건 마지막 인덱스
        cci_signal=[-20.0 + i for i in range(20)],
        ma5=sample_timeframe_state.ma5,
        ma20=sample_timeframe_state.ma20,
        volume_ma20=sample_timeframe_state.volume_ma20,
        last_updated=sample_timeframe_state.last_updated,
        is_resampled=False,
    )

    # cci 배열을 명시적으로 마지막 값이 0이 되도록 설정
    modified.cci[-1] = 0.0
    modified.cci_signal[-1] = -10.0  # signal < cci인데, cci == 0

    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=modified,
        sixty_min=sample_timeframe_state,
    )

    result = judge.assess(mtf)

    assert result["monthly"] == MarketDirection.BEARISH


def test_assess_weekly_bullish(judge, sample_timeframe_state):
    """주봉 BULLISH: cci[-1] > cci_signal[-1]."""
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=sample_timeframe_state,
        sixty_min=sample_timeframe_state,
    )

    result = judge.assess(mtf)

    assert result["weekly"] == MarketDirection.BULLISH


def test_assess_weekly_bearish(judge, sample_timeframe_state):
    """주봉 BEARISH: cci_signal >= cci."""
    modified = TimeframeState(
        candles=sample_timeframe_state.candles,
        cci=[40.0 + i for i in range(20)],
        cci_signal=[50.0 + i for i in range(20)],
        ma5=sample_timeframe_state.ma5,
        ma20=sample_timeframe_state.ma20,
        volume_ma20=sample_timeframe_state.volume_ma20,
        last_updated=sample_timeframe_state.last_updated,
        is_resampled=False,
    )
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=modified,
        monthly=sample_timeframe_state,
        sixty_min=sample_timeframe_state,
    )

    result = judge.assess(mtf)

    assert result["weekly"] == MarketDirection.BEARISH


def test_assess_empty_candles_neutral(judge, sample_timeframe_state):
    """캔들이 비어 있으면 NEUTRAL."""
    empty_state = TimeframeState(
        candles=[],  # 비어 있음
        cci=[50.0 + i for i in range(20)],
        cci_signal=[40.0 + i for i in range(20)],
        ma5=[100.0],
        ma20=[100.0],
        volume_ma20=[1000.0],
        last_updated=datetime.now(UTC),
        is_resampled=False,
    )
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=empty_state,
        sixty_min=sample_timeframe_state,
    )

    result = judge.assess(mtf)

    assert result["monthly"] == MarketDirection.NEUTRAL


def test_assess_insufficient_cci_neutral(judge, sample_timeframe_state):
    """CCI 길이 < 20이면 NEUTRAL."""
    short_cci_state = TimeframeState(
        candles=sample_timeframe_state.candles,
        cci=[50.0 + i for i in range(10)],  # 10개만
        cci_signal=[40.0 + i for i in range(10)],
        ma5=sample_timeframe_state.ma5,
        ma20=sample_timeframe_state.ma20,
        volume_ma20=sample_timeframe_state.volume_ma20,
        last_updated=datetime.now(UTC),
        is_resampled=False,
    )
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=short_cci_state,
        sixty_min=sample_timeframe_state,
    )

    result = judge.assess(mtf)

    assert result["monthly"] == MarketDirection.NEUTRAL


def test_assess_empty_cci_signal_neutral(judge, sample_timeframe_state):
    """CCI 및 시그널이 비어 있으면 NEUTRAL."""
    # TimeframeState의 __post_init__에서 cci와 cci_signal 길이가 같아야 함
    no_signal_state = TimeframeState(
        candles=sample_timeframe_state.candles,
        cci=[],  # 둘 다 비어 있음
        cci_signal=[],
        ma5=sample_timeframe_state.ma5,
        ma20=sample_timeframe_state.ma20,
        volume_ma20=sample_timeframe_state.volume_ma20,
        last_updated=datetime.now(UTC),
        is_resampled=False,
    )
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=no_signal_state,
        sixty_min=sample_timeframe_state,
    )

    result = judge.assess(mtf)

    assert result["monthly"] == MarketDirection.NEUTRAL


def test_is_trade_allowed_monthly_bullish(judge, sample_timeframe_state):
    """월봉 BULLISH → 거래 허용."""
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=sample_timeframe_state,
        sixty_min=sample_timeframe_state,
    )
    direction = judge.assess(mtf)

    assert judge.is_trade_allowed(direction) is True


def test_is_trade_allowed_monthly_bearish(judge, sample_timeframe_state):
    """월봉 BEARISH → 거래 불허."""
    modified = TimeframeState(
        candles=sample_timeframe_state.candles,
        cci=[40.0 + i for i in range(20)],  # cci < signal
        cci_signal=[50.0 + i for i in range(20)],
        ma5=sample_timeframe_state.ma5,
        ma20=sample_timeframe_state.ma20,
        volume_ma20=sample_timeframe_state.volume_ma20,
        last_updated=sample_timeframe_state.last_updated,
        is_resampled=False,
    )
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=modified,
        sixty_min=sample_timeframe_state,
    )
    direction = judge.assess(mtf)

    assert judge.is_trade_allowed(direction) is False


def test_is_trade_allowed_monthly_neutral(judge, sample_timeframe_state):
    """월봉 NEUTRAL → 거래 불허."""
    empty_state = TimeframeState(
        candles=[],
        cci=[],
        cci_signal=[],
        ma5=[],
        ma20=[],
        volume_ma20=[],
        last_updated=datetime.now(UTC),
        is_resampled=False,
    )
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=empty_state,
        sixty_min=sample_timeframe_state,
    )
    direction = judge.assess(mtf)

    assert judge.is_trade_allowed(direction) is False


def test_is_trade_allowed_missing_monthly_key(judge):
    """월봉 키 누락 → logger.error + False 반환."""
    direction = {
        "weekly": MarketDirection.BULLISH,
        "daily": MarketDirection.BULLISH,
        "sixty_min": MarketDirection.BULLISH,
        # "monthly" 누락
    }

    result = judge.is_trade_allowed(direction)

    assert result is False


def test_assess_all_timeframes(judge, sample_timeframe_state):
    """모든 타임프레임 방향 반환."""
    mtf = MultiTimeframeData(
        symbol="TEST",
        daily=sample_timeframe_state,
        weekly=sample_timeframe_state,
        monthly=sample_timeframe_state,
        sixty_min=sample_timeframe_state,
    )

    result = judge.assess(mtf)

    assert "monthly" in result
    assert "weekly" in result
    assert "daily" in result
    assert "sixty_min" in result
    assert isinstance(result["monthly"], MarketDirection)
    assert isinstance(result["weekly"], MarketDirection)
    assert isinstance(result["daily"], MarketDirection)
    assert isinstance(result["sixty_min"], MarketDirection)
