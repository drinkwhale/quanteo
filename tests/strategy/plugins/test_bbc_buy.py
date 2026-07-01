"""박병창 매수 3원칙 테스트.

3원칙 각 조건 경계 케이스, 금지 조건 차단, peak_volume 20봉 미만 fallback 검증.
"""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from core.marketdata.models import Candle
from core.strategy.plugins.bbc_buy import (
    BbcBuySignal,
    EntryTime,
    _get_peak_volume,
    check_principle_1,
    check_principle_2,
    check_principle_3,
    evaluate_buy,
)


# ============================================================================
# Fixture
# ============================================================================


def make_candle(
    open_p: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: int = 1000,
    symbol: str = "TEST",
) -> Candle:
    return Candle(
        symbol=symbol,
        open=open_p,
        high=high,
        low=low,
        close=close,
        volume=volume,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        market="domestic",
    )


def make_candles(count: int = 25, base_volume: int = 1000) -> list[Candle]:
    return [make_candle(volume=base_volume) for _ in range(count)]


# ============================================================================
# _get_peak_volume 테스트
# ============================================================================


def test_peak_volume_normal():
    candles = [make_candle(volume=i * 100) for i in range(1, 26)]  # 100~2500
    assert _get_peak_volume(candles) == 2500.0


def test_peak_volume_uses_last_20():
    # 앞 5봉에 고거래량이 있어도, 최근 20봉 기준이므로 포함됨
    old = [make_candle(volume=5000) for _ in range(5)]
    recent = [make_candle(volume=1000) for _ in range(20)]
    candles = old + recent
    # 최근 20봉에는 volume 1000짜리만 있음
    assert _get_peak_volume(candles) == 1000.0


def test_peak_volume_fallback_less_than_20(caplog):
    """20봉 미만 시 전체 캔들 중 최대 거래량 사용."""
    candles = [make_candle(volume=i * 500) for i in range(1, 11)]  # 10봉
    result = _get_peak_volume(candles)
    assert result == 5000.0
    assert "fallback" in caplog.text


def test_peak_volume_empty():
    assert _get_peak_volume([]) == 0.0


# ============================================================================
# 제1원칙 테스트
# ============================================================================


def test_principle_1_morning_passes():
    """오전 조건: price > ma5, 시가 재돌파, 거래량 급증."""
    result = check_principle_1(
        current_price=110.0,
        ma5=100.0,
        current_time=time(9, 30),
        prev_high=108.0,
        current_volume=2000,
        volume_ma20=1000.0,
        current_open=105.0,  # 현재가(110) > 시가(105) → 재돌파
    )
    assert result is not None
    assert result.principle == 1
    assert result.entry_time == EntryTime.MORNING


def test_principle_1_morning_no_retrace():
    """오전: 시가 재돌파 없음(현재가 <= 시가) → None."""
    result = check_principle_1(
        current_price=104.0,
        ma5=100.0,
        current_time=time(9, 30),
        prev_high=108.0,
        current_volume=2000,
        volume_ma20=1000.0,
        current_open=105.0,  # 현재가(104) < 시가(105) → 재돌파 아님
    )
    assert result is None


def test_principle_1_afternoon_passes():
    """오후 조건: price > ma5, 거래량 급증."""
    result = check_principle_1(
        current_price=110.0,
        ma5=100.0,
        current_time=time(14, 30),
        prev_high=108.0,
        current_volume=2000,
        volume_ma20=1000.0,
        current_open=100.0,
    )
    assert result is not None
    assert result.entry_time == EntryTime.AFTERNOON


def test_principle_1_excluded_midday():
    """10:00~14:00 구간 — 제외."""
    result = check_principle_1(
        current_price=110.0,
        ma5=100.0,
        current_time=time(12, 0),
        prev_high=108.0,
        current_volume=2000,
        volume_ma20=1000.0,
        current_open=100.0,
    )
    assert result is None


def test_principle_1_price_below_ma5():
    """price <= ma5 → 즉시 None."""
    result = check_principle_1(
        current_price=99.0,
        ma5=100.0,
        current_time=time(9, 30),
        prev_high=105.0,
        current_volume=2000,
        volume_ma20=1000.0,
        current_open=98.0,
    )
    assert result is None


def test_principle_1_volume_insufficient():
    """거래량 부족 시 None."""
    result = check_principle_1(
        current_price=110.0,
        ma5=100.0,
        current_time=time(9, 30),
        prev_high=108.0,
        current_volume=500,   # volume_ma20 * 1.5 = 1500 미달
        volume_ma20=1000.0,
        current_open=105.0,
    )
    assert result is None


# ============================================================================
# 제2원칙 테스트
# ============================================================================


def test_principle_2_passes():
    """눌림목: 가격 ma20~ma5 사이, 거래량 급증, 양봉."""
    candles = make_candles(25, base_volume=500)
    # 마지막 캔들 양봉으로 설정
    candles[-1] = make_candle(open_p=100.0, close=103.0, high=105.0, low=98.0, volume=500)
    result = check_principle_2(
        current_price=103.0,
        ma5=110.0,
        ma20=95.0,
        candles=candles,
        volume_ma20=500.0,
        current_volume=1000,   # > volume_ma20 * 1.5 = 750
        current_time=time(9, 30),
    )
    assert result is not None
    assert result.principle == 2


def test_principle_2_forbidden_bearish_volume():
    """금지: 거래량 증가 음봉."""
    candles = make_candles(25, base_volume=500)
    candles[-1] = make_candle(open_p=105.0, close=99.0, high=107.0, low=97.0, volume=500)
    result = check_principle_2(
        current_price=99.0,
        ma5=110.0,
        ma20=95.0,
        candles=candles,
        volume_ma20=500.0,
        current_volume=800,   # > volume_ma20 (음봉 + 거래량 증가)
        current_time=time(9, 30),
    )
    assert result is None


def test_principle_2_price_not_in_range():
    """가격이 눌림목 구간 밖 → None."""
    candles = make_candles(25)
    # price > ma5 → 범위 밖
    result = check_principle_2(
        current_price=120.0,
        ma5=110.0,
        ma20=95.0,
        candles=candles,
        volume_ma20=1000.0,
        current_volume=2000,
        current_time=time(9, 30),
    )
    assert result is None


def test_principle_2_decline_exceeds_50pct():
    """하락폭이 50% 초과 시 None."""
    # recent_high=110, current=50 → 하락폭 54.5% > 50%
    candles = [make_candle(high=110.0, volume=500) for _ in range(25)]
    candles[-1] = make_candle(open_p=48.0, close=50.0, high=55.0, low=47.0, volume=500)
    result = check_principle_2(
        current_price=50.0,
        ma5=60.0,
        ma20=45.0,
        candles=candles,
        volume_ma20=300.0,
        current_volume=700,
        current_time=time(9, 30),
    )
    assert result is None


# ============================================================================
# 제3원칙 테스트
# ============================================================================


def test_principle_3_passes():
    """급락 저점: price < ma20, 거래량 폭증, 양봉."""
    candles = make_candles(25)
    candles[-1] = make_candle(open_p=80.0, close=85.0, high=88.0, low=78.0, volume=1000)
    result = check_principle_3(
        current_price=85.0,
        ma20=90.0,
        candles=candles,
        volume_ma20=1000.0,
        current_volume=2500,   # > volume_ma20 * 2.0 = 2000
    )
    assert result is not None
    assert result.principle == 3


def test_principle_3_forbidden_bearish_decline():
    """금지: 거래량 증가 하락."""
    candles = make_candles(25)
    candles[-1] = make_candle(open_p=88.0, close=84.0, high=89.0, low=83.0, volume=1000)
    result = check_principle_3(
        current_price=84.0,
        ma20=90.0,
        candles=candles,
        volume_ma20=1000.0,
        current_volume=2500,  # 음봉 + 거래량 급증 → 금지
    )
    assert result is None


def test_principle_3_price_above_ma20():
    """price >= ma20 → None."""
    candles = make_candles(25)
    result = check_principle_3(
        current_price=95.0,
        ma20=90.0,
        candles=candles,
        volume_ma20=1000.0,
        current_volume=3000,
    )
    assert result is None


def test_principle_3_volume_insufficient():
    """거래량 부족 (< volume_ma20 * 2.0) → None."""
    candles = make_candles(25)
    candles[-1] = make_candle(open_p=80.0, close=85.0, high=88.0, low=78.0, volume=1000)
    result = check_principle_3(
        current_price=85.0,
        ma20=90.0,
        candles=candles,
        volume_ma20=1000.0,
        current_volume=1500,  # < 2000
    )
    assert result is None


def test_principle_3_doji_accepted():
    """십자형도 허용 (양봉/십자형)."""
    candles = make_candles(25)
    # open ≈ close → 십자형
    candles[-1] = make_candle(open_p=85.0, close=85.05, high=90.0, low=80.0, volume=1000)
    result = check_principle_3(
        current_price=85.0,
        ma20=90.0,
        candles=candles,
        volume_ma20=1000.0,
        current_volume=2500,
    )
    assert result is not None
    assert result.principle == 3


# ============================================================================
# evaluate_buy 통합 테스트
# ============================================================================


def test_evaluate_buy_returns_principle_1_first():
    """제1원칙 충족 시 제1원칙 반환."""
    candles = make_candles(25)
    result = evaluate_buy(
        current_price=115.0,
        ma5=100.0,
        ma20=80.0,
        current_volume=2000,
        volume_ma20=1000.0,
        candles=candles,
        current_time=time(9, 30),
        current_open=110.0,
    )
    assert result is not None
    assert result.principle == 1


def test_evaluate_buy_falls_through_to_principle_2():
    """제1원칙 미충족 시 제2원칙 확인."""
    candles = make_candles(25, base_volume=500)
    candles[-1] = make_candle(open_p=100.0, close=103.0, high=105.0, low=98.0, volume=500)
    result = evaluate_buy(
        current_price=103.0,
        ma5=110.0,   # price(103) <= ma5(110) → 제1원칙 X, 5일선 위 아님
        ma20=95.0,
        current_volume=1000,
        volume_ma20=500.0,
        candles=candles,
        current_time=time(9, 30),
        current_open=100.0,
    )
    # 제1원칙: price(103) <= ma5(110) → X
    # 제2원칙: ma20(95) < price(103) <= ma5(110) → 가능
    assert result is not None
    assert result.principle == 2


def test_evaluate_buy_none_when_no_conditions():
    """모든 원칙 미충족 시 None."""
    candles = make_candles(25)
    result = evaluate_buy(
        current_price=100.0,
        ma5=110.0,
        ma20=105.0,
        current_volume=500,
        volume_ma20=1000.0,
        candles=candles,
        current_time=time(12, 0),  # 10:00~14:00 제외 구간
        current_open=100.0,
    )
    assert result is None
