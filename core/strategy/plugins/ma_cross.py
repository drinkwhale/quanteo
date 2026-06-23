"""
이동평균 교차(Moving Average Crossover) 전략 플러그인.

단기 이동평균(fast MA)이 장기 이동평균(slow MA)을 상향 돌파하면 BUY,
하향 돌파하면 SELL 시그널을 생성한다.

research-to-live parity:
    warmup()으로 과거 캔들의 close 가격을 로드해 MA를 초기화한 뒤,
    on_tick()은 매 틱의 price를 새 데이터 포인트로 사용한다.
"""

from __future__ import annotations

import logging
from collections import deque

from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, Signal, SignalSide

logger = logging.getLogger(__name__)


class MACrossStrategy:
    """이동평균 교차 전략.

    fast_period < slow_period 이어야 한다.
    slow_period 개 이상의 데이터가 쌓이기 전에는 시그널을 생성하지 않는다.

    Args:
        symbol: 대상 종목 코드.
        fast_period: 단기 이동평균 기간.
        slow_period: 장기 이동평균 기간.
        qty: 시그널 당 희망 수량.
        name: 전략 식별자 (기본값 자동 생성).
    """

    def __init__(
        self,
        symbol: str,
        fast_period: int = 5,
        slow_period: int = 20,
        qty: int = 1,
        name: str | None = None,
    ) -> None:
        if fast_period >= slow_period:
            raise ValueError(
                f"fast_period({fast_period})는 slow_period({slow_period})보다 작아야 합니다"
            )
        self._symbol = symbol
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._qty = qty
        self.name = name or f"ma-cross-{fast_period}-{slow_period}"

        # slow_period 개 가격만 유지하면 두 MA를 모두 계산할 수 있음
        self._prices: deque[float] = deque(maxlen=slow_period)
        # 이전 교차 상태: fast > slow = True, fast < slow = False, 미결정 = None
        self._prev_fast_above: bool | None = None

    # ------------------------------------------------------------------
    # Strategy Protocol 구현
    # ------------------------------------------------------------------

    def warmup(self, history: list[Candle]) -> None:
        """과거 캔들의 close 가격으로 MA 버퍼를 채운다."""
        self._prices.clear()
        self._prev_fast_above = None
        for candle in history:
            if candle.symbol == self._symbol:
                self._prices.append(candle.close)

        # 워밍업 후 초기 교차 상태 결정 (첫 on_tick에서 false-signal 방지)
        if len(self._prices) >= self._slow_period:
            fast_ma = self._moving_average(self._fast_period)
            slow_ma = self._moving_average(self._slow_period)
            if fast_ma is not None and slow_ma is not None:
                self._prev_fast_above = fast_ma > slow_ma

        logger.debug(
            "warmup 완료: strategy=%s 가격=%d개 initial_above=%s",
            self.name,
            len(self._prices),
            self._prev_fast_above,
        )

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        """틱 수신 시 가격을 버퍼에 추가하고 교차 여부를 판단한다."""
        if tick.symbol != self._symbol:
            return None

        self._prices.append(tick.price)

        # slow_period 미만이면 아직 계산 불가
        if len(self._prices) < self._slow_period:
            return None

        fast_ma = self._moving_average(self._fast_period)
        slow_ma = self._moving_average(self._slow_period)

        if fast_ma is None or slow_ma is None:
            return None

        curr_fast_above = fast_ma > slow_ma
        signal = self._detect_crossover(curr_fast_above, fast_ma, slow_ma)
        self._prev_fast_above = curr_fast_above
        return signal

    # ------------------------------------------------------------------
    # 내부 계산
    # ------------------------------------------------------------------

    def _moving_average(self, period: int) -> float | None:
        """최근 period 개 가격의 단순 이동평균을 반환한다."""
        prices = list(self._prices)
        if len(prices) < period:
            return None
        window = prices[-period:]
        return sum(window) / period

    def _detect_crossover(
        self,
        curr_fast_above: bool,
        fast_ma: float,
        slow_ma: float,
    ) -> Signal | None:
        """이전 상태와 현재 상태를 비교해 교차 시그널을 반환한다."""
        if self._prev_fast_above is None:
            # 첫 번째 유효 틱은 기준점으로만 사용
            return None

        if not self._prev_fast_above and curr_fast_above:
            # 하향 → 상향: 골든 크로스 → BUY
            reason = f"골든크로스 fast_ma={fast_ma:.2f} slow_ma={slow_ma:.2f}"
            logger.info("시그널: %s %s BUY (%s)", self.name, self._symbol, reason)
            return Signal(
                strategy=self.name,
                symbol=self._symbol,
                side=SignalSide.BUY,
                qty=self._qty,
                price=None,  # 시장가
                reason=reason,
            )

        if self._prev_fast_above and not curr_fast_above:
            # 상향 → 하향: 데드 크로스 → SELL
            reason = f"데드크로스 fast_ma={fast_ma:.2f} slow_ma={slow_ma:.2f}"
            logger.info("시그널: %s %s SELL (%s)", self.name, self._symbol, reason)
            return Signal(
                strategy=self.name,
                symbol=self._symbol,
                side=SignalSide.SELL,
                qty=self._qty,
                price=None,
                reason=reason,
            )

        return None

    # ------------------------------------------------------------------
    # 진단용 프로퍼티
    # ------------------------------------------------------------------

    @property
    def fast_ma(self) -> float | None:
        """현재 단기 이동평균값."""
        return self._moving_average(self._fast_period)

    @property
    def slow_ma(self) -> float | None:
        """현재 장기 이동평균값."""
        return self._moving_average(self._slow_period)

    @property
    def price_count(self) -> int:
        """버퍼에 저장된 가격 개수."""
        return len(self._prices)
