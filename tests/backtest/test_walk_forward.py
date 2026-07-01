"""Walk-Forward 검증 테스트.

기간 분리 정확도, 과최적화 감지 임계값 검증.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from core.backtest.engine import BacktestResult
from core.backtest.walk_forward import WalkForwardValidator
from core.marketdata.models import Candle


# ============================================================================
# 픽스처
# ============================================================================

_TS_BASE = datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)


def _make_candles(n: int, symbol: str = "000660") -> list[Candle]:
    return [
        Candle(
            symbol=symbol,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1000,
            timestamp=_TS_BASE + timedelta(days=i),
            market="domestic",
        )
        for i in range(n)
    ]


def _make_mock_engine(sharpe_sequence: list[float] | None = None):
    """BacktestEngine 모의 객체 — run()이 특정 샤프지수를 가진 결과를 반환."""
    engine = MagicMock()
    call_count = [0]

    def fake_run(symbol, candles):
        result = BacktestResult(initial_capital=10_000_000.0)
        # 에쿼티 커브를 인위적으로 설정해 샤프지수 제어
        n = len(candles)
        if sharpe_sequence and call_count[0] < len(sharpe_sequence):
            sharpe_target = sharpe_sequence[call_count[0]]
            # 샤프지수가 양수면 상승 커브, 0이면 플랫
            if sharpe_target > 0:
                result.equity_curve = [10_000_000 * (1 + 0.001 * i) for i in range(max(n, 2))]
            else:
                result.equity_curve = [10_000_000.0] * max(n, 2)
        else:
            result.equity_curve = [10_000_000.0] * max(n, 2)
        call_count[0] += 1
        return result

    engine.run.side_effect = fake_run
    return engine


# ============================================================================
# 기간 분리 정확도
# ============================================================================


def test_fold_period_split():
    """인샘플/아웃샘플 기간이 정확히 분리되어야 한다."""
    in_months = 3
    out_months = 1
    days_per_month = 21
    in_days = in_months * days_per_month  # 63
    out_days = out_months * days_per_month  # 21
    total = in_days + out_days + out_days  # 2 폴드 가능

    engine = _make_mock_engine()
    validator = WalkForwardValidator(engine, in_sample_months=in_months, out_sample_months=out_months, trading_days_per_month=days_per_month)

    candles = _make_candles(total)
    result = validator.validate("000660", candles)

    assert len(result.folds) >= 1
    fold0 = result.folds[0]

    assert fold0.in_sample_start == 0
    assert fold0.in_sample_end == in_days
    assert fold0.out_sample_start == in_days
    assert fold0.out_sample_end == in_days + out_days


def test_insufficient_candles_returns_empty():
    """캔들 부족 시 빈 결과 반환."""
    engine = _make_mock_engine()
    validator = WalkForwardValidator(engine, in_sample_months=12, out_sample_months=3)

    candles = _make_candles(10)  # 너무 부족
    result = validator.validate("000660", candles)

    assert result.folds == []
    assert result.n_overfit == 0


def test_multiple_folds_sliding_window():
    """슬라이딩 윈도우로 여러 폴드 생성."""
    in_months = 3
    out_months = 1
    days_per_month = 21
    # 4 폴드 가능한 데이터
    total = (in_months + 4 * out_months) * days_per_month

    engine = _make_mock_engine()
    validator = WalkForwardValidator(engine, in_sample_months=in_months, out_sample_months=out_months, trading_days_per_month=days_per_month)

    candles = _make_candles(total)
    result = validator.validate("000660", candles)

    assert len(result.folds) >= 2


def test_fold_indices_non_overlapping():
    """각 폴드의 인샘플과 아웃샘플이 겹치지 않아야 한다."""
    engine = _make_mock_engine()
    validator = WalkForwardValidator(engine, in_sample_months=3, out_sample_months=1, trading_days_per_month=21)

    candles = _make_candles(200)
    result = validator.validate("000660", candles)

    for fold in result.folds:
        assert fold.in_sample_end == fold.out_sample_start
        assert fold.in_sample_start < fold.in_sample_end
        assert fold.out_sample_start < fold.out_sample_end


# ============================================================================
# 과최적화 감지 임계값
# ============================================================================


def test_overfitting_detection_above_threshold():
    """30% 초과 저하 → 과최적화 감지."""
    # 인샘플 샤프 1.0, 아웃샘플 0.5 → 50% 저하 → 과최적화
    assert WalkForwardValidator._detect_overfitting(1.0, 0.5) is True


def test_overfitting_detection_below_threshold():
    """30% 이하 저하 → 정상."""
    # 인샘플 샤프 1.0, 아웃샘플 0.75 → 25% 저하 → 정상
    assert WalkForwardValidator._detect_overfitting(1.0, 0.75) is False


def test_overfitting_detection_just_below_threshold():
    """29% 저하 → 임계값(30%) 미만 → 정상."""
    # degradation ≈ 0.29, threshold = 0.30: 0.29 > 0.30 → False
    assert WalkForwardValidator._detect_overfitting(1.0, 0.71) is False


def test_overfitting_detection_negative_in_sharpe():
    """인샘플 샤프 음수 → 비교 의미없음 → False 반환."""
    assert WalkForwardValidator._detect_overfitting(-0.5, -1.0) is False


def test_overfitting_detection_zero_in_sharpe():
    """인샘플 샤프 0 → False (분모 0 방지)."""
    assert WalkForwardValidator._detect_overfitting(0.0, 0.0) is False


def test_overfit_ratio_calculated():
    """n_overfit과 overfit_ratio가 올바르게 계산된다."""
    engine = _make_mock_engine()
    validator = WalkForwardValidator(engine, in_sample_months=3, out_sample_months=1, trading_days_per_month=21)

    candles = _make_candles(200)
    result = validator.validate("000660", candles)

    total_folds = len(result.folds)
    if total_folds > 0:
        assert result.overfit_ratio == result.n_overfit / total_folds
