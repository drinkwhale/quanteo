"""
Strategy Engine — 플러그인 로드·지표 갱신·시그널 생성 루프.

Event Bus의 TICK 이벤트를 수신해 등록된 모든 Strategy 플러그인에 전달하고,
반환된 Signal을 SIGNAL 이벤트로 Event Bus에 다시 발행한다.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from core.events.bus import EventBus
from core.events.types import Event, EventType
from core.marketdata.models import Candle, Tick
from core.strategy.base import MarketContext, Signal, Strategy

logger = logging.getLogger(__name__)

# 심볼별 캔들 버퍼 크기 (워밍업 + 지표 계산에 충분한 범위)
_DEFAULT_CANDLE_BUFFER = 200


class StrategyEngine:
    """전략 플러그인 실행 엔진.

    등록된 Strategy 플러그인 목록을 관리하며, Event Bus의 TICK 이벤트를 수신해
    각 플러그인의 on_tick()을 호출한다. 반환된 Signal은 SIGNAL 이벤트로 발행된다.

    모든 전략은 반드시 warmup() 이후 on_tick()이 호출된다.
    역방향 캔들 버퍼(최근 N개)는 엔진이 자동 관리하며 MarketContext로 전달된다.

    Args:
        bus: Event Bus 인스턴스.
        candle_buffer_size: 심볼별 유지할 최대 캔들 수.
    """

    def __init__(
        self,
        bus: EventBus,
        candle_buffer_size: int = _DEFAULT_CANDLE_BUFFER,
    ) -> None:
        self._bus = bus
        self._candle_buffer_size = candle_buffer_size
        # 플러그인 목록 (name → Strategy)
        self._strategies: dict[str, Strategy] = {}
        # 심볼별 캔들 링버퍼 (오래된 것부터 최신 순)
        self._candle_buffers: dict[str, deque[Candle]] = {}
        self._running = False

    # ------------------------------------------------------------------
    # 플러그인 관리
    # ------------------------------------------------------------------

    def register(self, strategy: Strategy) -> None:
        """전략 플러그인을 등록한다.

        동일 name의 전략이 이미 있으면 덮어쓴다.

        Args:
            strategy: Strategy Protocol을 구현한 인스턴스.
        """
        self._strategies[strategy.name] = strategy
        logger.info("전략 등록: %s", strategy.name)

    def unregister(self, name: str) -> None:
        """전략 플러그인을 제거한다."""
        self._strategies.pop(name, None)
        logger.info("전략 제거: %s", name)

    @property
    def strategy_names(self) -> list[str]:
        """등록된 전략 이름 목록."""
        return list(self._strategies.keys())

    # ------------------------------------------------------------------
    # 워밍업
    # ------------------------------------------------------------------

    def warmup(self, history: list[Candle]) -> None:
        """과거 캔들로 모든 전략의 초기 지표를 설정하고 캔들 버퍼를 채운다.

        run() 호출 전에 한 번 실행해야 research-to-live parity가 보장된다.

        Args:
            history: 오래된 것부터 최신 순의 캔들 목록.
        """
        if not history:
            return

        symbol = history[0].symbol

        # 캔들 버퍼 초기화 (버퍼 크기 내로 잘라서 채움)
        buf = deque(history[-self._candle_buffer_size :], maxlen=self._candle_buffer_size)
        self._candle_buffers[symbol] = buf

        for strategy in self._strategies.values():
            try:
                strategy.warmup(list(history))
                logger.debug("warmup 완료: strategy=%s symbol=%s", strategy.name, symbol)
            except Exception as exc:
                logger.error(
                    "warmup 실패: strategy=%s symbol=%s error=%s",
                    strategy.name,
                    symbol,
                    exc,
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # 라이프사이클 (asyncio.gather 패턴)
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """엔진 실행 루프.

        Event Bus에 TICK/CANDLE 핸들러를 등록하고 종료 신호까지 대기한다.
        asyncio.gather()에 포함되어 실행된다.
        """
        self._running = True
        self._bus.subscribe(EventType.TICK, self._handle_tick_event)
        self._bus.subscribe(EventType.CANDLE, self._handle_candle_event)
        logger.info("StrategyEngine 시작 (전략 %d개)", len(self._strategies))

        # 실행 루프: stop() 호출 전까지 대기
        while self._running:
            await asyncio.sleep(0.1)

        logger.info("StrategyEngine 종료")

    async def stop(self) -> None:
        """실행 루프를 종료한다."""
        self._running = False

    # ------------------------------------------------------------------
    # 이벤트 핸들러
    # ------------------------------------------------------------------

    def _handle_tick_event(self, event: Event) -> None:
        """TICK 이벤트 수신 시 각 전략의 on_tick()을 호출한다."""
        tick: Tick = event.payload
        ctx = self._build_context(tick.symbol)

        for strategy in self._strategies.values():
            try:
                signal: Signal | None = strategy.on_tick(tick, ctx)
                if signal is not None:
                    self._publish_signal(signal)
            except Exception as exc:
                logger.error(
                    "on_tick 예외: strategy=%s symbol=%s error=%s",
                    strategy.name,
                    tick.symbol,
                    exc,
                    exc_info=True,
                )

    def _handle_candle_event(self, event: Event) -> None:
        """CANDLE 이벤트 수신 시 캔들 버퍼를 갱신한다."""
        candle: Candle = event.payload
        buf = self._candle_buffers.setdefault(
            candle.symbol, deque(maxlen=self._candle_buffer_size)
        )
        buf.append(candle)

    def _build_context(self, symbol: str) -> MarketContext:
        """심볼에 대한 MarketContext를 생성한다."""
        buf = self._candle_buffers.get(symbol)
        candles = list(buf) if buf else []
        return MarketContext(symbol=symbol, recent_candles=candles)

    def _publish_signal(self, signal: Signal) -> None:
        """Signal을 Event Bus에 SIGNAL 이벤트로 발행한다."""
        event = Event(type=EventType.SIGNAL, payload=signal, source=signal.strategy)
        self._bus.publish_nowait(event)
        logger.info(
            "시그널 발행: strategy=%s symbol=%s side=%s qty=%s reason=%s",
            signal.strategy,
            signal.symbol,
            signal.side,
            signal.qty,
            signal.reason,
        )
