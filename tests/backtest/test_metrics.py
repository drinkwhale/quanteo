"""성과 지표 계산 테스트.

MDD, 샤프지수 수식 검증, 거래 0건 엣지 케이스.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.backtest.engine import BacktestResult, PerformanceMetrics, Trade
from core.backtest.metrics import calculate_mdd, calculate_metrics, calculate_sharpe
from core.strategy.base import SignalSide


# ============================================================================
# 헬퍼
# ============================================================================

_TS = datetime(2026, 1, 2, tzinfo=UTC)


def _make_trade(side: SignalSide, price: float, qty: int, commission: float = 0.0, tax: float = 0.0) -> Trade:
    return Trade(
        symbol="000660",
        side=side,
        price=price,
        qty=qty,
        commission=commission,
        tax=tax,
        timestamp=_TS,
        signal_timestamp=_TS - timedelta(days=1),
    )


def _make_result(
    trades: list[Trade],
    equity_curve: list[float],
    initial_capital: float = 10_000_000.0,
) -> BacktestResult:
    result = BacktestResult()
    result.trades = trades
    result.equity_curve = equity_curve
    result.initial_capital = initial_capital
    return result


# ============================================================================
# MDD
# ============================================================================


def test_mdd_no_drawdown():
    """단조 상승 커브 → MDD=0."""
    equity = [1_000_000, 1_100_000, 1_200_000, 1_300_000]
    assert calculate_mdd(equity) == 0.0


def test_mdd_simple():
    """고점 1,000 → 저점 500 → MDD=0.5."""
    equity = [1_000_000, 1_100_000, 500_000, 700_000]
    mdd = calculate_mdd(equity)
    # 고점 1,100,000 → 최저 500,000 → (1,100,000 - 500,000) / 1,100,000
    expected = (1_100_000 - 500_000) / 1_100_000
    assert abs(mdd - expected) < 1e-6


def test_mdd_all_decline():
    """처음부터 지속 하락."""
    equity = [1_000_000, 900_000, 800_000, 600_000]
    mdd = calculate_mdd(equity)
    expected = (1_000_000 - 600_000) / 1_000_000
    assert abs(mdd - expected) < 1e-6


def test_mdd_recovery_after_drawdown():
    """낙폭 후 회복 — MDD는 낙폭 최대값 유지."""
    equity = [1_000_000, 1_200_000, 600_000, 1_500_000]
    mdd = calculate_mdd(equity)
    expected = (1_200_000 - 600_000) / 1_200_000
    assert abs(mdd - expected) < 1e-6


def test_mdd_single_element():
    """원소 1개 → MDD=0."""
    assert calculate_mdd([1_000_000]) == 0.0


def test_mdd_empty():
    """빈 리스트 → MDD=0."""
    assert calculate_mdd([]) == 0.0


# ============================================================================
# 샤프지수
# ============================================================================


def test_sharpe_positive_returns():
    """변동이 있는 양의 수익률 → 양의 샤프지수."""
    # 매일 평균 0.1% 수익이지만 변동 있음 (std > 0 보장)
    import math
    returns = [0.001 + 0.0005 * math.sin(i) for i in range(50)]
    sharpe = calculate_sharpe(returns)
    assert sharpe > 0


def test_sharpe_zero_std():
    """수익률 표준편차 0 → 0.0 반환."""
    returns = [0.0] * 100
    assert calculate_sharpe(returns) == 0.0


def test_sharpe_single_element():
    """원소 1개 → 0.0."""
    assert calculate_sharpe([0.01]) == 0.0


def test_sharpe_formula_check():
    """샤프지수 수식 수동 검증."""
    import math

    returns = [0.01, -0.005, 0.008, 0.003, -0.002]
    n = len(returns)
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(var)
    daily_rf = 0.035 / 250
    expected = (mean - daily_rf) / std * math.sqrt(250)
    result = calculate_sharpe(returns, risk_free=0.035)
    assert abs(result - expected) < 1e-6


# ============================================================================
# calculate_metrics
# ============================================================================


def test_metrics_no_trades():
    """거래 0건 — win_rate=0, total_trades=0."""
    result = _make_result([], [1_000_000, 1_000_000, 1_000_000])
    metrics = calculate_metrics(result)
    assert metrics.win_rate == 0.0
    assert metrics.total_trades == 0
    assert metrics.mdd >= 0.0


def test_metrics_single_win_trade():
    """단일 매수-매도 이익 거래 → win_rate=1.0."""
    buy = _make_trade(SignalSide.BUY, 100_000.0, 10, commission=150.0)
    sell = _make_trade(SignalSide.SELL, 120_000.0, 10, commission=180.0, tax=216.0)
    equity = [1_000_000, 1_000_000, 1_200_000]
    result = _make_result([buy, sell], equity)
    metrics = calculate_metrics(result)
    assert metrics.win_rate == 1.0
    assert metrics.total_trades == 2
    assert metrics.profit_loss_ratio > 0


def test_metrics_single_loss_trade():
    """단일 매수-매도 손실 거래 → win_rate=0.0."""
    buy = _make_trade(SignalSide.BUY, 120_000.0, 10, commission=180.0)
    sell = _make_trade(SignalSide.SELL, 100_000.0, 10, commission=150.0, tax=180.0)
    equity = [1_200_000, 1_200_000, 1_000_000]
    result = _make_result([buy, sell], equity)
    metrics = calculate_metrics(result)
    assert metrics.win_rate == 0.0


def test_metrics_mdd_positive():
    """낙폭 있으면 MDD > 0."""
    equity = [1_000_000, 1_200_000, 600_000, 900_000]
    result = _make_result([], equity)
    metrics = calculate_metrics(result)
    assert metrics.mdd > 0


def test_metrics_annualized_return_positive_growth():
    """자본 증가 시 연환산 수익률 양수."""
    initial = 10_000_000.0
    # 250일에 걸쳐 20% 성장
    n = 250
    growth_per_day = (1.20 ** (1 / n))
    equity = [initial * (growth_per_day ** i) for i in range(n)]
    result = _make_result([], equity, initial_capital=initial)
    metrics = calculate_metrics(result)
    assert metrics.annualized_return > 0.0
