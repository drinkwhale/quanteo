"""
Risk Manager — 시그널 검증 및 주문 생성.

단방향 흐름의 게이트키퍼:
    Signal → RiskManager.evaluate() → Order | Rejection

모든 주문은 이 모듈을 반드시 통과한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from core.events.bus import EventBus
from core.events.types import Event, EventType
from core.risk.models import (
    HaltLevel,
    Order,
    OrderSide,
    OrderType,
    Portfolio,
    Position,
    Rejection,
)
from core.strategy.base import Signal, SignalSide

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------


@dataclass
class RiskConfig:
    """Risk Manager 파라미터.

    Args:
        max_position_value: 종목당 최대 보유 금액 (원). 기본 100만원.
        max_daily_orders: 일일 최대 주문 횟수. 기본 20회.
        max_total_exposure: 총 주식 노출 한도 (원). 기본 500만원.
        stop_loss_pct: 손절 기준 손익률 (음수, 예: -0.05 = -5%). 기본 -5%.
        take_profit_pct: 익절 기준 손익률 (양수, 예: 0.15 = +15%). 기본 +15%.
        reduce_ratio: REDUCE 수준에서 신규 주문 수량 축소 비율. 기본 0.5 (50%).
    """

    max_position_value: float = 1_000_000.0
    max_daily_orders: int = 20
    max_total_exposure: float = 5_000_000.0
    stop_loss_pct: float = -0.05
    take_profit_pct: float = 0.15
    reduce_ratio: float = 0.5


# ---------------------------------------------------------------------------
# Risk Manager
# ---------------------------------------------------------------------------


class RiskManager:
    """시그널 검증, 포지션 한도, 킬스위치를 관리하는 게이트키퍼.

    Args:
        config: 리스크 파라미터.
        bus: Event Bus — RISK_BREACH, KILL_SWITCH 이벤트 발행에 사용.
    """

    def __init__(self, config: RiskConfig | None = None, bus: EventBus | None = None) -> None:
        self._config = config or RiskConfig()
        self._bus = bus
        self._halt: HaltLevel = HaltLevel.NONE
        self._daily_order_count: int = 0
        self._daily_reset_date: date = datetime.now(UTC).date()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def evaluate(self, signal: Signal, portfolio: Portfolio) -> Order | Rejection:
        """시그널을 검증해 주문 또는 거부를 반환한다.

        검증 순서:
        1. 킬스위치 수준 확인
        2. 일일 주문 횟수 한도
        3. 총 노출 한도 (BUY만)
        4. 종목당 포지션 가치 한도 (BUY만)
        5. 수량 스케일링 (REDUCE 수준)
        6. Order 생성

        Args:
            signal: Strategy Engine이 발행한 시그널.
            portfolio: 현재 포트폴리오 스냅샷.

        Returns:
            Order: 검증 통과 시.
            Rejection: 검증 실패 시.
        """
        self._refresh_daily_counter()

        # 1) 킬스위치
        if rejection := self._check_halt(signal):
            return rejection

        # 1.5) 시장가 BUY 거부 — 가격 없이는 노출 한도 계산 불가
        if signal.side == SignalSide.BUY and signal.price is None:
            return Rejection(
                signal=signal,
                reason="시장가 BUY 주문은 리스크 체크 불가 — 지정가(price 지정) 사용",
            )

        # 2) 일일 주문 횟수
        if rejection := self._check_daily_orders(signal):
            return rejection

        # 3) 총 노출 한도 (BUY)
        if signal.side == SignalSide.BUY:
            if rejection := self._check_total_exposure(signal, portfolio):
                return rejection

        # 4) 종목당 포지션 가치 한도 (BUY)
        if signal.side == SignalSide.BUY:
            if rejection := self._check_position_value(signal, portfolio):
                return rejection

        # 5) REDUCE 수준 수량 축소 — BUY 신규 진입에만 적용 (SELL 청산은 전량 유지)
        qty = self._apply_reduce(signal.qty) if signal.side == SignalSide.BUY else signal.qty
        if qty < 1:
            return Rejection(signal=signal, reason="REDUCE 적용 후 수량이 0 이하")

        # 6) 주문 생성
        order = self._build_order(signal, qty)
        self._daily_order_count += 1
        logger.info(
            "주문 승인: %s %s %s %d주 (client_id=%s)",
            signal.symbol,
            signal.side,
            order.order_type.value,
            qty,
            order.client_order_id,
        )
        return order

    def check_exit(self, position: Position, current_price: float) -> Order | None:
        """보유 포지션의 손절/익절 조건을 확인하고 청산 주문을 반환한다.

        Args:
            position: 대상 포지션.
            current_price: 현재 시세.

        Returns:
            Order: 손절/익절 조건 충족 시 SELL 주문.
            None: 조건 미충족 시.
        """
        if position.qty <= 0:
            return None

        pnl_pct = position.unrealized_pnl_pct(current_price)

        if pnl_pct <= self._config.stop_loss_pct:
            reason = f"손절 ({pnl_pct:.2%} <= {self._config.stop_loss_pct:.2%})"
            logger.warning("손절 트리거: %s %s", position.symbol, reason)
            signal = self._make_exit_signal(position, reason)
            return self._build_order(signal, position.qty)

        if pnl_pct >= self._config.take_profit_pct:
            reason = f"익절 ({pnl_pct:.2%} >= {self._config.take_profit_pct:.2%})"
            logger.info("익절 트리거: %s %s", position.symbol, reason)
            signal = self._make_exit_signal(position, reason)
            return self._build_order(signal, position.qty)

        return None

    @property
    def halt_level(self) -> HaltLevel:
        """현재 킬스위치 수준."""
        return self._halt

    async def graduated_halt(self, level: HaltLevel) -> None:
        """킬스위치 수준을 설정하고 이벤트를 발행한다.

        수준은 단조 증가만 허용한다 (KILL → PAUSE 강등 불가).

        Args:
            level: 새로 적용할 HaltLevel.
        """
        levels = list(HaltLevel)
        current_idx = levels.index(self._halt)
        new_idx = levels.index(level)

        if new_idx <= current_idx:
            logger.debug("킬스위치 강등 무시: %s → %s", self._halt, level)
            return

        prev = self._halt
        self._halt = level
        logger.warning("킬스위치 변경: %s → %s", prev, level)

        if self._bus:
            event_type = EventType.KILL_SWITCH if level == HaltLevel.KILL else EventType.RISK_BREACH
            self._bus.publish_nowait(Event(type=event_type, payload={"level": level.value}))

    def reset_halt(self) -> None:
        """킬스위치를 NONE으로 초기화한다 (운영자 수동 복구용)."""
        prev = self._halt
        self._halt = HaltLevel.NONE
        logger.info("킬스위치 초기화: %s → NONE", prev)

    @property
    def daily_order_count(self) -> int:
        """오늘 승인된 주문 수."""
        self._refresh_daily_counter()
        return self._daily_order_count

    # ------------------------------------------------------------------
    # 내부 검증 메서드
    # ------------------------------------------------------------------

    def _check_halt(self, signal: Signal) -> Rejection | None:
        """킬스위치 수준에 따른 검증."""
        if self._halt == HaltLevel.KILL:
            # KILL: 손절(SELL)만 허용
            if signal.side == SignalSide.BUY:
                return Rejection(signal=signal, reason=f"킬스위치 활성 ({self._halt.value}) — 신규 BUY 차단")
        elif self._halt == HaltLevel.PAUSE:
            # PAUSE: 신규 진입 불가
            if signal.side == SignalSide.BUY:
                return Rejection(signal=signal, reason=f"일시정지 활성 ({self._halt.value}) — 신규 BUY 차단")
        return None

    def _check_daily_orders(self, signal: Signal) -> Rejection | None:
        """일일 주문 횟수 한도 검증."""
        if self._daily_order_count >= self._config.max_daily_orders:
            return Rejection(
                signal=signal,
                reason=f"일일 주문 한도 초과 ({self._daily_order_count}/{self._config.max_daily_orders})",
            )
        return None

    def _check_total_exposure(self, signal: Signal, portfolio: Portfolio) -> Rejection | None:
        """총 노출 한도 검증 (BUY 전용)."""
        estimated_add = signal.qty * (signal.price or 0.0)
        projected = portfolio.total_exposure + estimated_add
        if projected > self._config.max_total_exposure:
            return Rejection(
                signal=signal,
                reason=(
                    f"총 노출 한도 초과 (현재 {portfolio.total_exposure:,.0f}원"
                    f" + 신규 {estimated_add:,.0f}원 > 한도 {self._config.max_total_exposure:,.0f}원)"
                ),
            )
        return None

    def _check_position_value(self, signal: Signal, portfolio: Portfolio) -> Rejection | None:
        """종목당 포지션 가치 한도 검증 (BUY 전용)."""
        existing = portfolio.positions.get(signal.symbol)
        existing_value = existing.book_value if existing else 0.0
        add_value = signal.qty * (signal.price or 0.0)
        projected = existing_value + add_value
        if projected > self._config.max_position_value:
            return Rejection(
                signal=signal,
                reason=(
                    f"종목 한도 초과 ({signal.symbol}: 현재 {existing_value:,.0f}원"
                    f" + 신규 {add_value:,.0f}원 > 한도 {self._config.max_position_value:,.0f}원)"
                ),
            )
        return None

    def _apply_reduce(self, qty: int) -> int:
        """REDUCE 수준이면 수량을 축소한다."""
        if self._halt == HaltLevel.REDUCE:
            reduced = max(1, int(qty * self._config.reduce_ratio))
            if reduced < qty:
                logger.info("REDUCE 적용: %d → %d주", qty, reduced)
            return reduced
        return qty

    def _build_order(self, signal: Signal, qty: int) -> Order:
        """Signal로부터 Order를 생성한다."""
        from core.config.settings import Env, Market

        return Order(
            symbol=signal.symbol,
            market=Market.DOMESTIC,  # 추후 Signal에 market 필드 추가 시 변경
            env=Env.VPS,             # 기본값 VPS — 실전은 명시적 override
            side=OrderSide.BUY if signal.side == SignalSide.BUY else OrderSide.SELL,
            order_type=OrderType.LIMIT if signal.price else OrderType.MARKET,
            qty=qty,
            price=signal.price or 0.0,
            source_signal=signal,
        )

    def _make_exit_signal(self, position: Position, reason: str) -> Signal:
        """포지션 청산용 Signal을 생성한다 (check_exit 내부용)."""
        from core.strategy.base import SignalSide

        return Signal(
            strategy="risk-manager",
            symbol=position.symbol,
            side=SignalSide.SELL,
            qty=position.qty,
            price=None,
            reason=reason,
        )

    def _refresh_daily_counter(self) -> None:
        """날짜가 바뀌면 일일 주문 카운터를 리셋한다."""
        today = datetime.now(UTC).date()
        if today != self._daily_reset_date:
            self._daily_order_count = 0
            self._daily_reset_date = today
