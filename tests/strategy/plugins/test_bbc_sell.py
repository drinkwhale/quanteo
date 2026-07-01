"""박병창 매도 2원칙 테스트.

1/2원칙 SellAction 매핑, 전량 매도 트리거, 45도 하락 경계 케이스, 캔들 부족 시 False 검증.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.marketdata.models import Candle
from core.strategy.plugins.bbc_sell import (
    BbcSellSignal,
    SellAction,
    check_sell_principle_1,
    check_sell_principle_2,
    detect_45_degree_decline,
    evaluate_sell,
)


# ============================================================================
# Fixture
# ============================================================================


def make_candle(
    open_p: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 105.0,
    volume: int = 1000,
) -> Candle:
    return Candle(
        symbol="TEST",
        open=open_p,
        high=high,
        low=low,
        close=close,
        volume=volume,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        market="domestic",
    )


def make_candles(count: int = 15, volume: int = 1000) -> list[Candle]:
    return [make_candle(volume=volume) for _ in range(count)]


def make_bearish_candle(volume: int = 1000) -> Candle:
    """음봉: open > close."""
    return make_candle(open_p=105.0, close=99.0, high=108.0, low=97.0, volume=volume)


def make_large_bearish_candle(volume: int = 1000) -> Candle:
    """장대음봉: 몸통 비율 >= 0.6."""
    # 몸통: |105-90| = 15, 총범위: 115-88 = 27 → 비율 0.55 → 0.7로 조정
    # 몸통: |108-90| = 18, 총범위: 110-88 = 22 → 비율 0.818 ✓
    return make_candle(open_p=108.0, close=90.0, high=110.0, low=88.0, volume=volume)


def make_doji_candle(volume: int = 1000) -> Candle:
    """십자형: open ≈ close (0.1% 이내)."""
    return make_candle(open_p=100.0, close=100.05, high=105.0, low=95.0, volume=volume)


# ============================================================================
# 제1원칙 테스트
# ============================================================================


def test_p1_partial_40pct_bearish_volume_surge():
    """5일선 위 + 거래량 급증 + 음봉 → PARTIAL_40PCT."""
    candles = make_candles(15)
    candles[-1] = make_bearish_candle(volume=1000)
    result = check_sell_principle_1(
        current_price=115.0,
        ma5=110.0,
        ma20=100.0,
        candles=candles,
        current_volume=2500,   # > 1000 * 2.0
        volume_ma20=1000.0,
    )
    assert result is not None
    assert result.principle == 1
    assert result.action == SellAction.PARTIAL_40PCT


def test_p1_partial_30pct_doji_volume_surge():
    """5일선 위 + 거래량 폭증 + 십자형 → PARTIAL_30PCT."""
    candles = make_candles(15)
    candles[-1] = make_doji_candle(volume=1000)
    result = check_sell_principle_1(
        current_price=115.0,
        ma5=110.0,
        ma20=100.0,
        candles=candles,
        current_volume=2500,
        volume_ma20=1000.0,
    )
    assert result is not None
    assert result.action == SellAction.PARTIAL_30PCT


def test_p1_full_exit_reverse_alignment():
    """역배열 전환: price < ma5 AND ma5 < ma20 → FULL_EXIT."""
    candles = make_candles(15)
    result = check_sell_principle_1(
        current_price=90.0,
        ma5=95.0,
        ma20=100.0,   # ma5(95) < ma20(100) → 역배열
        candles=candles,
        current_volume=500,
        volume_ma20=1000.0,
    )
    assert result is not None
    assert result.action == SellAction.FULL_EXIT


def test_p1_none_price_below_ma5_no_reverse():
    """price < ma5이지만 역배열 아닌 경우 → None (정배열 유지)."""
    candles = make_candles(15)
    candles[-1] = make_bearish_candle()
    result = check_sell_principle_1(
        current_price=104.0,
        ma5=107.0,
        ma20=100.0,   # ma5(107) > ma20(100) → 정배열, 역배열 조건 미충족
        candles=candles,
        current_volume=2500,
        volume_ma20=1000.0,
    )
    # price(104) <= ma5(107) 이므로 "5일선 위" 아님, 역배열도 아님 → None
    assert result is None


def test_p1_volume_insufficient():
    """거래량 부족 → None."""
    candles = make_candles(15)
    candles[-1] = make_bearish_candle(volume=1000)
    result = check_sell_principle_1(
        current_price=115.0,
        ma5=110.0,
        ma20=100.0,
        candles=candles,
        current_volume=1500,   # < 1000 * 2.0 = 2000
        volume_ma20=1000.0,
    )
    assert result is None


# ============================================================================
# 제2원칙 테스트
# ============================================================================


def test_p2_partial_50pct_bearish():
    """5~20일선 사이 + 거래량 증가 + 음봉 → PARTIAL_50PCT."""
    candles = make_candles(15)
    candles[-1] = make_bearish_candle(volume=1000)
    result = check_sell_principle_2(
        current_price=105.0,
        ma5=110.0,
        ma20=100.0,
        candles=candles,
        current_volume=1600,   # > 1000 * 1.5
        volume_ma20=1000.0,
    )
    assert result is not None
    assert result.principle == 2
    assert result.action == SellAction.PARTIAL_50PCT


def test_p2_full_exit_near_ma20_large_bearish():
    """20일선 바로 위 + 거래량 폭증 + 장대음봉 → FULL_EXIT."""
    candles = make_candles(15)
    candles[-1] = make_large_bearish_candle(volume=1000)
    # ma20=100, ma20*1.05=105 → current_price=103 ≤ 105 → near_ma20
    result = check_sell_principle_2(
        current_price=103.0,
        ma5=112.0,
        ma20=100.0,
        candles=candles,
        current_volume=2500,   # > 1000 * 2.0
        volume_ma20=1000.0,
    )
    assert result is not None
    assert result.action == SellAction.FULL_EXIT


def test_p2_not_near_ma20_stays_partial():
    """20일선에서 멀 때 (> ma20 * 1.05): 전량 매도 대신 일반 50% 매도."""
    candles = make_candles(15)
    candles[-1] = make_large_bearish_candle(volume=1000)
    # ma20=100, ma20*1.05=105. current_price=109 > 105 → near_ma20=False
    result = check_sell_principle_2(
        current_price=109.0,
        ma5=112.0,
        ma20=100.0,
        candles=candles,
        current_volume=2500,
        volume_ma20=1000.0,
    )
    # near_ma20=False → 특별 규칙 미충족 → 일반 50% 매도
    assert result is not None
    assert result.action == SellAction.PARTIAL_50PCT


def test_p2_price_not_in_range():
    """가격이 5~20일선 구간 밖 → None."""
    candles = make_candles(15)
    result = check_sell_principle_2(
        current_price=120.0,
        ma5=110.0,
        ma20=100.0,
        candles=candles,
        current_volume=2000,
        volume_ma20=1000.0,
    )
    assert result is None


def test_p2_no_bearish_candle():
    """양봉이면 매도 신호 없음 → None."""
    candles = make_candles(15)
    # 양봉
    candles[-1] = make_candle(open_p=102.0, close=108.0, high=110.0, low=100.0)
    result = check_sell_principle_2(
        current_price=108.0,
        ma5=112.0,
        ma20=100.0,
        candles=candles,
        current_volume=2000,
        volume_ma20=1000.0,
    )
    assert result is None


# ============================================================================
# detect_45_degree_decline 테스트
# ============================================================================


def test_45deg_decline_detected():
    """완만한 지속 하락 패턴 감지."""
    # 점진적 하락 캔들 12봉, 거래량 균등
    candles = []
    for i in range(12):
        price = 100.0 - i * 0.5
        candles.append(make_candle(open_p=price + 0.2, close=price, high=price + 0.5, low=price - 0.5, volume=1000))
    assert detect_45_degree_decline(candles, window=12) is True


def test_45deg_no_decline_flat():
    """가격 변화 없으면 감지 안됨."""
    candles = [make_candle(open_p=100.0, close=100.0, volume=1000) for _ in range(12)]
    assert not detect_45_degree_decline(candles, window=12)


def test_45deg_insufficient_candles(caplog):
    """캔들 수 < window → False + logger.warning."""
    candles = make_candles(count=5)
    result = detect_45_degree_decline(candles, window=12)
    assert result is False
    assert "조기 판단 방지" in caplog.text


def test_45deg_high_volume_variance():
    """거래량 변동이 크면 감지 안됨 (꾸준한 매도 아님)."""
    candles = []
    for i in range(12):
        price = 100.0 - i * 0.5
        vol = 1000 if i % 2 == 0 else 10000  # 급등락 거래량
        candles.append(make_candle(open_p=price + 0.2, close=price, high=price + 0.5, low=price - 0.5, volume=vol))
    result = detect_45_degree_decline(candles, window=12)
    # 거래량 변동계수 > 0.8 → False
    assert result is False


# ============================================================================
# evaluate_sell 통합 테스트
# ============================================================================


def test_evaluate_sell_p1_first():
    """제1원칙 충족 시 제1원칙 반환."""
    candles = make_candles(15)
    candles[-1] = make_bearish_candle(volume=1000)
    result = evaluate_sell(
        current_price=115.0,
        ma5=110.0,
        ma20=100.0,
        candles=candles,
        current_volume=2500,
        volume_ma20=1000.0,
    )
    assert result is not None
    assert result.principle == 1


def test_evaluate_sell_falls_to_p2():
    """제1원칙 미충족 시 제2원칙 확인."""
    candles = make_candles(15)
    candles[-1] = make_bearish_candle(volume=1000)
    # price가 5~20일선 사이
    result = evaluate_sell(
        current_price=105.0,
        ma5=110.0,
        ma20=100.0,
        candles=candles,
        current_volume=1600,
        volume_ma20=1000.0,
    )
    assert result is not None
    assert result.principle == 2


def test_evaluate_sell_none():
    """모든 원칙 미충족 → None."""
    candles = make_candles(15)
    result = evaluate_sell(
        current_price=105.0,
        ma5=110.0,
        ma20=100.0,
        candles=candles,
        current_volume=500,  # 거래량 부족
        volume_ma20=1000.0,
    )
    assert result is None
