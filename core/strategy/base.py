"""
Strategy — 플러그인 인터페이스 & 공통 타입 정의.

모든 전략 플러그인이 따르는 Protocol과 Signal 타입을 정의한다.
전략은 시그널만 생성하며, 주문 실행 권한이 없다 (단방향 흐름 강제).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from core.marketdata.models import Candle, Tick

# ---------------------------------------------------------------------------
# 시그널 타입
# ---------------------------------------------------------------------------


class SignalSide(StrEnum):
    """매수/매도 방향."""

    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Signal:
    """전략이 생성하는 매매 시그널.

    전략은 이 객체를 반환하며, Risk Manager가 이를 받아 실제 주문으로 변환한다.
    수량(qty)은 희망 수량이며, Risk Manager가 변동성 스케일링 후 조정할 수 있다.

    Args:
        strategy: 시그널을 생성한 전략 이름.
        symbol: 종목 코드.
        side: 매수(BUY) 또는 매도(SELL).
        qty: 희망 수량 (≥1).
        price: 희망 가격 (None이면 시장가). 지정 시 반드시 양수.
        reason: 시그널 생성 근거 (디버깅·알림용).
        timestamp: 시그널 생성 시각 (UTC).
    """

    strategy: str
    symbol: str
    side: SignalSide
    qty: int
    price: float | None = None
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.qty < 1:
            raise ValueError(f"qty는 1 이상이어야 합니다, 입력값: {self.qty}")
        if self.price is not None and self.price <= 0:
            raise ValueError(f"price는 0보다 커야 합니다, 입력값: {self.price}")


# ---------------------------------------------------------------------------
# 시장 컨텍스트
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketContext:
    """전략이 on_tick 호출 시 함께 받는 시장 정보.

    최근 캔들·지표를 편리하게 접근할 수 있도록 Strategy Engine이 채워 전달한다.
    frozen=True로 선언되어 전략 플러그인이 필드를 재할당하거나 내용을 변경할 수 없다.

    Args:
        symbol: 종목 코드.
        recent_candles: 최근 캔들 tuple (오래된 것부터 최신 순). 읽기 전용.
    """

    symbol: str
    recent_candles: tuple[Candle, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Strategy Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Strategy(Protocol):
    """전략 플러그인 인터페이스.

    플러그인은 이 Protocol을 구조적으로 충족(structural subtyping)하면 된다.
    명시적 상속은 불필요하지만, base.py의 타입을 활용하는 편이 안전하다.

    research-to-live parity:
        warmup()으로 과거 캔들을 로드해 지표를 초기화한 뒤 on_tick()을 실행하면
        백테스트와 라이브 트레이딩이 동일한 경로를 따른다.
    """

    name: str
    """전략 고유 식별자. engine 로그·시그널 추적에 사용된다."""

    def warmup(self, history: list[Candle]) -> None:
        """과거 캔들로 지표를 초기화한다 (백테스트·라이브 공통 경로).

        Args:
            history: 오래된 것부터 최신 순의 캔들 목록.
        """
        ...

    def on_tick(self, tick: Tick, ctx: MarketContext) -> Signal | None:
        """새로운 틱 수신 시 호출된다.

        지표를 갱신하고, 매매 조건이 충족되면 Signal을 반환한다.
        조건 미충족 시 None을 반환한다.

        Args:
            tick: 방금 수신된 틱 데이터.
            ctx: 최근 캔들 컨텍스트 (읽기 전용).

        Returns:
            Signal: 매매 조건 충족 시.
            None: 조건 미충족 시.
        """
        ...
