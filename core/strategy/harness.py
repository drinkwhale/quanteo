"""
전략 경량 검증 하니스 (Lightweight Backtest Harness).

과거 캔들 시퀀스를 Strategy에 순차 재생해 시그널 목록을 반환한다.
외부 I/O 없이 순수 Python으로 동작하므로 빠르고 결정론적이다.

research-to-live parity 보장:
    라이브와 동일한 warmup() → on_tick() 경로를 따르므로,
    하니스에서 검증된 전략 동작은 라이브에서도 그대로 재현된다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, Signal, Strategy

logger = logging.getLogger(__name__)


@dataclass
class HarnessResult:
    """하니스 실행 결과.

    Attributes:
        signals: 전략이 생성한 Signal 목록 (시간순).
        total_ticks: 재생된 틱(캔들) 수.
        strategy_name: 검증 대상 전략 이름.
        symbol: 종목 코드.
        start_at: 첫 캔들 타임스탬프.
        end_at: 마지막 캔들 타임스탬프.
    """

    signals: list[Signal] = field(default_factory=list)
    total_ticks: int = 0
    strategy_name: str = ""
    symbol: str = ""
    start_at: datetime | None = None
    end_at: datetime | None = None

    @property
    def buy_count(self) -> int:
        """BUY 시그널 수."""
        return sum(1 for s in self.signals if s.side.value == "BUY")

    @property
    def sell_count(self) -> int:
        """SELL 시그널 수."""
        return sum(1 for s in self.signals if s.side.value == "SELL")


def run_backtest(
    strategy: Strategy,
    candles: list[Candle],
    *,
    warmup_size: int | None = None,
) -> HarnessResult:
    """과거 캔들로 전략을 재생해 시그널 목록을 반환한다.

    warmup_size 개 캔들로 warmup()을 수행한 뒤, 나머지 캔들을
    Tick으로 변환해 on_tick()을 순차 호출한다.

    warmup_size가 None이면 전체 캔들의 절반을 warmup에 사용한다.
    warmup_size가 0이면 warmup 없이 바로 재생한다.

    Args:
        strategy: 검증할 Strategy 인스턴스.
        candles: 과거 캔들 목록 (오래된 것부터 최신 순).
        warmup_size: warmup에 사용할 캔들 수.

    Returns:
        HarnessResult: 시그널 목록 및 통계.
    """
    if not candles:
        logger.warning("run_backtest: 캔들 목록이 비어 있습니다")
        return HarnessResult(strategy_name=strategy.name)

    symbol = candles[0].symbol

    # warmup 구간과 재생 구간 분리
    if warmup_size is None:
        warmup_size = len(candles) // 2
    warmup_size = max(0, min(warmup_size, len(candles)))

    warmup_candles = candles[:warmup_size]
    replay_candles = candles[warmup_size:]

    # warmup
    strategy.warmup(warmup_candles)
    logger.debug(
        "하니스 warmup 완료: strategy=%s candles=%d", strategy.name, len(warmup_candles)
    )

    # 캔들 버퍼 (MarketContext 구성용)
    candle_buffer = list(warmup_candles)
    result = HarnessResult(
        strategy_name=strategy.name,
        symbol=symbol,
        start_at=replay_candles[0].timestamp if replay_candles else None,
        end_at=replay_candles[-1].timestamp if replay_candles else None,
    )

    # 재생 루프
    for candle in replay_candles:
        tick = _candle_to_tick(candle)
        ctx = MarketContext(symbol=symbol, recent_candles=list(candle_buffer))

        try:
            signal = strategy.on_tick(tick, ctx)
            if signal is not None:
                result.signals.append(signal)
        except Exception as exc:
            logger.error(
                "하니스 on_tick 예외: strategy=%s ts=%s error=%s",
                strategy.name,
                candle.timestamp,
                exc,
                exc_info=True,
            )

        candle_buffer.append(candle)
        result.total_ticks += 1

    logger.info(
        "하니스 완료: strategy=%s ticks=%d signals=%d (BUY=%d SELL=%d)",
        strategy.name,
        result.total_ticks,
        len(result.signals),
        result.buy_count,
        result.sell_count,
    )
    return result


def _candle_to_tick(candle: Candle) -> Tick:
    """캔들의 close 가격을 Tick으로 변환한다."""
    return Tick(
        symbol=candle.symbol,
        price=candle.close,
        volume=candle.volume,
        timestamp=candle.timestamp,
        market=candle.market,
    )
