"""백테스트 성과 지표 계산.

MDD, 샤프지수, 승률, 손익비, 연환산 수익률을 계산한다.

T078 구현.
"""

from __future__ import annotations

import logging
import math

from core.backtest.engine import BacktestResult, PerformanceMetrics, Trade
from core.strategy.base import SignalSide

logger = logging.getLogger(__name__)

# 연간 거래일 (국내 기준)
_TRADING_DAYS_PER_YEAR = 250
# 무위험수익률 기본값 (국고채 3.5%)
_DEFAULT_RISK_FREE = 0.035


def calculate_mdd(equity_curve: list[float]) -> float:
    """최대낙폭(MDD) 계산.

    Args:
        equity_curve: 일자별 자산 가치 리스트.

    Returns:
        MDD (0~1 비율, 0이면 낙폭 없음). 음수가 아닌 비율.
    """
    if len(equity_curve) < 2:
        return 0.0

    peak = equity_curve[0]
    mdd = 0.0

    for value in equity_curve[1:]:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0.0
        mdd = max(mdd, drawdown)

    return mdd


def calculate_sharpe(
    returns: list[float],
    risk_free: float = _DEFAULT_RISK_FREE,
) -> float:
    """연환산 샤프지수 계산.

    Args:
        returns: 일별 수익률 리스트.
        risk_free: 무위험수익률 (연 기준).

    Returns:
        샤프지수 (거래 없거나 표준편차 0이면 0.0).
    """
    if len(returns) < 2:
        return 0.0

    n = len(returns)
    mean_return = sum(returns) / n
    variance = sum((r - mean_return) ** 2 for r in returns) / (n - 1)
    std_dev = math.sqrt(variance)

    if std_dev < 1e-10:
        return 0.0

    daily_rf = risk_free / _TRADING_DAYS_PER_YEAR
    daily_excess = mean_return - daily_rf
    return (daily_excess / std_dev) * math.sqrt(_TRADING_DAYS_PER_YEAR)


def _pair_trades(trades: list[Trade]) -> list[tuple[Trade, Trade]]:
    """매수-매도 쌍으로 묶는다 (FIFO 방식).

    단순 구현: 매수-매도 순서대로 쌍을 만든다.
    분할 매수/매도는 쌍이 맞지 않을 수 있으므로 FIFO 방식 적용.
    미청산 매수(orphaned buy)는 메트릭에서 제외되며 WARNING으로 기록한다.
    """
    pairs: list[tuple[Trade, Trade]] = []
    buy_queue: list[Trade] = []

    for trade in trades:
        if trade.side == SignalSide.BUY:
            buy_queue.append(trade)
        elif trade.side == SignalSide.SELL and buy_queue:
            buy = buy_queue.pop(0)
            pairs.append((buy, trade))

    if buy_queue:
        logger.warning(
            "미청산 매수 %d건이 메트릭 계산에서 제외됨 (미실현 손익 미반영). "
            "symbols=%s",
            len(buy_queue),
            [t.symbol for t in buy_queue],
        )

    return pairs


def calculate_metrics(result: BacktestResult, risk_free: float = _DEFAULT_RISK_FREE) -> PerformanceMetrics:
    """BacktestResult로부터 성과 지표를 계산한다.

    Args:
        result: 백테스트 결과.
        risk_free: 무위험수익률 (연 기준).

    Returns:
        PerformanceMetrics.
    """
    equity_curve = result.equity_curve
    trades = result.trades

    # 거래 0건 처리
    if not trades:
        mdd = calculate_mdd(equity_curve)
        daily_returns = _equity_to_returns(equity_curve)
        sharpe = calculate_sharpe(daily_returns, risk_free)
        annual = _annualized_return(equity_curve, result.initial_capital)
        return PerformanceMetrics(
            win_rate=0.0,
            profit_loss_ratio=0.0,
            mdd=mdd,
            sharpe_ratio=sharpe,
            total_trades=0,
            annualized_return=annual,
        )

    # 매수-매도 쌍 생성
    pairs = _pair_trades(trades)
    wins = 0
    losses = 0
    total_profit = 0.0
    total_loss = 0.0

    for buy, sell in pairs:
        pnl = sell.net_amount + buy.net_amount  # 매도(양수) + 매수(음수) = 순손익
        if pnl > 0:
            wins += 1
            total_profit += pnl
        else:
            losses += 1
            total_loss += abs(pnl)

    total_closed = wins + losses
    win_rate = wins / total_closed if total_closed > 0 else 0.0
    avg_profit = total_profit / wins if wins > 0 else 0.0
    avg_loss = total_loss / losses if losses > 0 else 0.0
    # losses=0이면 손실 거래 없음 → 손익비 = inf (비율이므로 금액 반환 금지)
    pl_ratio = avg_profit / avg_loss if avg_loss > 0 else float("inf")

    mdd = calculate_mdd(equity_curve)
    daily_returns = _equity_to_returns(equity_curve)
    sharpe = calculate_sharpe(daily_returns, risk_free)
    annual = _annualized_return(equity_curve, result.initial_capital)

    return PerformanceMetrics(
        win_rate=win_rate,
        profit_loss_ratio=pl_ratio,
        mdd=mdd,
        sharpe_ratio=sharpe,
        total_trades=len(trades),
        annualized_return=annual,
    )


def _equity_to_returns(equity_curve: list[float]) -> list[float]:
    """에쿼티 커브 → 일별 수익률 변환."""
    if len(equity_curve) < 2:
        return []
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev > 0:
            returns.append((equity_curve[i] - prev) / prev)
        else:
            returns.append(0.0)
    return returns


def _annualized_return(equity_curve: list[float], initial_capital: float) -> float:
    """연환산 수익률 계산.

    Args:
        equity_curve: 일자별 에쿼티.
        initial_capital: 초기 자본금.

    Returns:
        연환산 수익률 (소수 비율, 예: 0.15 = 15%).
    """
    if len(equity_curve) < 2 or initial_capital <= 0:
        return 0.0

    final = equity_curve[-1]
    n_days = len(equity_curve)

    if n_days < 2 or final <= 0:
        return 0.0

    total_return = final / initial_capital
    years = n_days / _TRADING_DAYS_PER_YEAR

    try:
        return total_return ** (1 / years) - 1
    except (ValueError, ZeroDivisionError):
        return 0.0
