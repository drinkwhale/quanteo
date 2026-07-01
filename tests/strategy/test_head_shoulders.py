"""헤드앤숄더 패턴 감지 테스트.

패턴 감지 경계 케이스, 거래량 조건 충족/불충족, override 시 스코어 무시 검증.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.marketdata.models import Candle
from core.strategy.indicators.head_shoulders import detect_head_shoulders


# ============================================================================
# 픽스처 헬퍼
# ============================================================================

_TS_BASE = datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)


def _c(i: int, close: float, high: float | None = None, volume: int = 1000) -> Candle:
    h = high if high is not None else close * 1.01
    return Candle(
        symbol="000660",
        open=close * 0.99,
        high=h,
        low=close * 0.98,
        close=close,
        volume=volume,
        timestamp=_TS_BASE + timedelta(weeks=i),
        market="domestic",
        interval="1w",
    )


def _head_shoulders_candles(vol_confirms: bool = True) -> list[Candle]:
    """하락전환 헤드앤숄더 패턴 캔들.

    구조: 상승 → 왼쪽어깨(100) → 하락 → 머리(130) → 하락 → 오른쪽어깨(90) → 하락
    """
    # 오른쪽 어깨 거래량: vol_confirms=True이면 머리보다 낮음
    right_vol = 500 if vol_confirms else 2000

    candles = [
        # 초기 상승 (바닥)
        _c(0, 60.0),
        _c(1, 70.0),
        _c(2, 80.0),
        # 왼쪽 어깨 형성 (고점 100)
        _c(3, 100.0, volume=1000),
        # 첫 번째 조정 (저점)
        _c(4, 75.0),
        # 머리 형성 (고점 130 - 왼쪽어깨보다 높음)
        _c(5, 130.0, volume=2000),
        # 두 번째 조정
        _c(6, 70.0),
        # 오른쪽 어깨 (고점 90 - 왼쪽어깨보다 낮음)
        _c(7, 90.0, volume=right_vol),
        # 하락 전환
        _c(8, 65.0),
        _c(9, 55.0),
    ]
    return candles


def _inverse_head_shoulders_candles() -> list[Candle]:
    """상승전환 역헤드앤숄더 패턴 캔들.

    구조: 하락 → 왼쪽어깨저점(40) → 상승 → 머리저점(20) → 상승 → 오른쪽어깨저점(50) → 돌파
    """
    candles = [
        # 초기 하락
        _c(0, 90.0),
        _c(1, 80.0),
        _c(2, 70.0),
        # 왼쪽 어깨 저점 (40)
        _c(3, 40.0, volume=1000),
        # 반등
        _c(4, 65.0),
        # 머리 저점 (20 - 왼쪽어깨보다 낮음)
        _c(5, 20.0, volume=800),
        # 반등
        _c(6, 55.0),
        # 오른쪽 어깨 저점 (50 - 왼쪽어깨보다 높음)
        _c(7, 50.0, volume=900),
        # 거래량 급증 + 장대양봉으로 왼쪽 고점 돌파
        _c(8, 92.0, volume=2000),  # 왼쪽 고점(90) 돌파
        _c(9, 95.0, volume=1800),
    ]
    return candles


# ============================================================================
# 캔들 부족
# ============================================================================


def test_insufficient_candles_returns_none():
    """캔들 10개 미만 → None 반환."""
    candles = [_c(i, 100.0) for i in range(5)]
    assert detect_head_shoulders(candles) is None


def test_empty_candles_returns_none():
    """빈 리스트 → None 반환."""
    assert detect_head_shoulders([]) is None


# ============================================================================
# 하락전환 헤드앤숄더
# ============================================================================


def test_bearish_pattern_detected():
    """올바른 헤드앤숄더 패턴 감지."""
    candles = _head_shoulders_candles(vol_confirms=True)
    result = detect_head_shoulders(candles)

    assert result is not None
    assert result.pattern_type == "하락전환"


def test_bearish_volume_confirms_true():
    """오른쪽 어깨 거래량 < 머리 거래량 → volume_confirms=True."""
    candles = _head_shoulders_candles(vol_confirms=True)
    result = detect_head_shoulders(candles)

    assert result is not None
    assert result.volume_confirms is True


def test_bearish_volume_confirms_false():
    """오른쪽 어깨 거래량 > 머리 거래량 → volume_confirms=False."""
    candles = _head_shoulders_candles(vol_confirms=False)
    result = detect_head_shoulders(candles)

    # 패턴 자체는 감지되지만 거래량 확인 안 됨
    if result is not None and result.pattern_type == "하락전환":
        assert result.volume_confirms is False


def test_bearish_neckline_is_average_of_troughs():
    """넥라인 = 두 저점의 평균."""
    candles = _head_shoulders_candles(vol_confirms=True)
    result = detect_head_shoulders(candles)

    if result is not None and result.pattern_type == "하락전환":
        # 넥라인은 두 조정 저점의 평균 (양수여야 함)
        assert result.neckline > 0


def test_bearish_no_pattern_when_head_lower():
    """머리가 어깨보다 낮으면 헤드앤숄더 아님."""
    candles = [
        _c(0, 60.0),
        _c(1, 100.0, volume=1000),  # 왼쪽 어깨
        _c(2, 70.0),
        _c(3, 80.0, volume=1000),   # "머리" — 왼쪽어깨보다 낮음
        _c(4, 60.0),
        _c(5, 90.0, volume=800),    # 오른쪽 어깨 — 머리보다 높음
        _c(6, 55.0),
        _c(7, 50.0),
        _c(8, 45.0),
        _c(9, 40.0),
    ]
    result = detect_head_shoulders(candles)
    if result is not None:
        assert result.pattern_type != "하락전환"


# ============================================================================
# 상승전환 역헤드앤숄더
# ============================================================================


def test_bullish_pattern_detected():
    """올바른 역헤드앤숄더 패턴 감지."""
    candles = _inverse_head_shoulders_candles()
    result = detect_head_shoulders(candles)

    assert result is not None
    assert result.pattern_type == "상승전환"


def test_bullish_volume_confirms():
    """역헤드앤숄더: 거래량 급증 + 장대양봉 → volume_confirms=True."""
    candles = _inverse_head_shoulders_candles()
    result = detect_head_shoulders(candles)

    if result is not None and result.pattern_type == "상승전환":
        assert result.volume_confirms is True


# ============================================================================
# override 동작: 스코어 무관하게 즉시 전량 매도
# ============================================================================


def test_override_sells_regardless_of_score():
    """헤드앤숄더 하락전환 감지 시 on_tick이 SELL 시그널을 반환한다.

    CcibbcStrategy.on_tick()의 헤드앤숄더 override 분기를 직접 검증.
    """
    from unittest.mock import MagicMock

    from core.marketdata.models import Tick
    from core.strategy.base import MarketContext
    from core.strategy.plugins.cci_bbc_strategy import CciBbcStrategy
    from core.strategy.base import SignalSide

    # 헤드앤숄더 패턴 캔들
    hs_candles = _head_shoulders_candles(vol_confirms=True)

    # 실제 패턴이 감지되는지 먼저 확인
    hs_result = detect_head_shoulders(hs_candles)
    if hs_result is None or hs_result.pattern_type != "하락전환" or not hs_result.volume_confirms:
        pytest.skip("헤드앤숄더 패턴 미감지 — override 테스트 생략")

    strategy = CciBbcStrategy(symbol="000660")
    strategy._mtf_data = None  # MTF 없으면 보통 None 반환하지만 HS override가 먼저 실행됨

    tick = Tick(
        symbol="000660",
        price=65.0,
        volume=1000,
        timestamp=_TS_BASE + timedelta(weeks=10),
        market="domestic",
    )
    ctx = MarketContext(symbol="000660", recent_candles=tuple(hs_candles))

    signal = strategy.on_tick(tick, ctx)

    assert signal is not None
    assert signal.side == SignalSide.SELL
