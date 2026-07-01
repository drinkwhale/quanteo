"""타임프레임 계층 방향 판단 모듈.

4개 타임프레임(월봉, 주봉, 일봉, 60분봉)의 CCI 지표를 기반으로 시장 방향을 판단하고,
매매 가능 여부를 결정한다.

T072 구현:
- MarketDirection: 시장 방향 (BULLISH, BEARISH, NEUTRAL)
- TimeframeJudge.assess() — 4개 타임프레임별 방향 반환
- TimeframeJudge.is_trade_allowed() — 월봉 BULLISH 시에만 거래 허용
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from core.strategy.multi_timeframe import MultiTimeframeData, TimeframeState

logger = logging.getLogger(__name__)


# ============================================================================
# MarketDirection: 시장 방향 열거형
# ============================================================================


class MarketDirection(StrEnum):
    """시장 방향 표시.

    Values:
        BULLISH: 강세 (매매 허용)
        BEARISH: 약세 (관망)
        NEUTRAL: 중립 (데이터 부족 또는 사용 불가)
    """

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


# ============================================================================
# TimeframeJudge: 타임프레임 방향 판단
# ============================================================================


@dataclass
class TimeframeJudge:
    """4개 타임프레임 CCI 기반 방향 판단.

    Attributes:
        None (stateless).
    """

    # 박병창 매매기법 기준 20기간. 일봉·주봉·월봉 모두 동일하게 적용.
    CCI_PERIOD = 20

    def assess(self, mtf: MultiTimeframeData) -> dict[str, MarketDirection]:
        """4개 타임프레임별 방향 판단.

        Args:
            mtf: MultiTimeframeData (4개 타임프레임 상태).

        Returns:
            dict[str, MarketDirection] with keys:
                - "monthly": 월봉 방향
                - "weekly": 주봉 방향
                - "daily": 일봉 방향
                - "sixty_min": 60분봉 방향

        Logic:
            - 월봉: cci[-1] > cci_signal[-1] AND cci[-1] > 0 → BULLISH, else BEARISH
            - 주봉: cci[-1] > cci_signal[-1] → BULLISH, else BEARISH
            - 일봉: cci[-1] > cci_signal[-1] → BULLISH, else BEARISH
            - 60분봉: cci[-1] > cci_signal[-1] → BULLISH, else BEARISH

            데이터 미비 처리 (NEUTRAL):
            - candles가 비어 있음
            - cci 길이 < CCI_PERIOD (20)
        """
        return {
            "monthly": self._assess_timeframe(
                mtf.monthly,
                "monthly",
                require_positive_cci=True,
            ),
            "weekly": self._assess_timeframe(
                mtf.weekly,
                "weekly",
                require_positive_cci=False,
            ),
            "daily": self._assess_timeframe(
                mtf.daily,
                "daily",
                require_positive_cci=False,
            ),
            "sixty_min": self._assess_timeframe(
                mtf.sixty_min,
                "sixty_min",
                require_positive_cci=False,
            ),
        }

    def _assess_timeframe(
        self,
        state: TimeframeState,
        timeframe_name: str,
        require_positive_cci: bool = False,
    ) -> MarketDirection:
        """단일 타임프레임 방향 판단.

        Args:
            state: TimeframeState.
            timeframe_name: 타임프레임 이름 (로깅용).
            require_positive_cci: True이면 cci[-1] > 0도 확인 (월봉용).

        Returns:
            MarketDirection (BULLISH, BEARISH, 또는 NEUTRAL).
        """
        # API 장애 + 이전 캐시 없음: "데이터 없음"을 명시적으로 구분해 로깅
        if state.is_empty:
            logger.warning(
                "%s 데이터 없음 (API 장애, 이전 캐시도 없음) — NEUTRAL 처리", timeframe_name
            )
            return MarketDirection.NEUTRAL

        # 데이터 미비 검사
        if not state.candles or len(state.cci) < self.CCI_PERIOD:
            logger.warning(
                f"{timeframe_name} 데이터 부족 — NEUTRAL 처리 "
                f"(candles={len(state.candles)}, cci={len(state.cci)})"
            )
            return MarketDirection.NEUTRAL

        # CCI와 signal 길이 확인
        if len(state.cci_signal) == 0:
            logger.warning(f"{timeframe_name} CCI 시그널 데이터 부족 — NEUTRAL 처리")
            return MarketDirection.NEUTRAL

        # 최신 CCI 값
        cci_latest = state.cci[-1]
        signal_latest = state.cci_signal[-1]

        # 월봉: cci[-1] > cci_signal[-1] AND cci[-1] > 0
        if require_positive_cci:
            if cci_latest > signal_latest and cci_latest > 0:
                return MarketDirection.BULLISH
            else:
                return MarketDirection.BEARISH

        # 주봉, 일봉, 60분봉: cci[-1] > cci_signal[-1]
        if cci_latest > signal_latest:
            return MarketDirection.BULLISH
        else:
            return MarketDirection.BEARISH

    def is_trade_allowed(self, direction: dict[str, MarketDirection]) -> bool:
        """거래 가능 여부 판단.

        월봉이 BULLISH일 때만 거래 허용.

        Args:
            direction: assess() 반환값.

        Returns:
            bool: True if monthly == BULLISH, False otherwise.
                  monthly 키 누락 시 logger.error + False 반환 (fail-safe).
        """
        monthly_direction = direction.get("monthly")

        if monthly_direction is None:
            logger.error("월봉 데이터 없음 — 거래 불가")
            return False

        return monthly_direction == MarketDirection.BULLISH
