"""Walk-Forward 검증.

인샘플 기간으로 전략 검증 → 아웃샘플로 성과 확인을 반복,
과최적화(과적합) 감지를 포함한다.

T080 구현.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.backtest.engine import BacktestEngine, BacktestResult
from core.backtest.metrics import calculate_metrics
from core.marketdata.models import Candle

logger = logging.getLogger(__name__)

# 과최적화 감지: 아웃샘플 샤프지수가 인샘플 대비 이 비율 이상 저하 시 경고
_OVERFITTING_THRESHOLD = 0.30


@dataclass
class WalkForwardFold:
    """단일 Walk-Forward 폴드 결과.

    Attributes:
        fold_idx: 폴드 번호 (0-based).
        in_sample_start: 인샘플 시작 캔들 인덱스.
        in_sample_end: 인샘플 종료 캔들 인덱스 (exclusive).
        out_sample_start: 아웃샘플 시작 캔들 인덱스.
        out_sample_end: 아웃샘플 종료 캔들 인덱스 (exclusive).
        in_sample_result: 인샘플 백테스트 결과.
        out_sample_result: 아웃샘플 백테스트 결과.
        is_overfit: 과최적화 감지 여부.
    """

    fold_idx: int
    in_sample_start: int
    in_sample_end: int
    out_sample_start: int
    out_sample_end: int
    in_sample_result: BacktestResult
    out_sample_result: BacktestResult
    is_overfit: bool = False


@dataclass
class WalkForwardResult:
    """Walk-Forward 전체 결과.

    Attributes:
        folds: 폴드별 결과 목록.
        n_overfit: 과최적화 감지된 폴드 수.
        overfit_ratio: 과최적화 비율 (n_overfit / total_folds).
    """

    folds: list[WalkForwardFold] = field(default_factory=list)
    n_overfit: int = 0
    overfit_ratio: float = 0.0

    def summary(self) -> str:
        """결과 요약 문자열."""
        lines = [f"Walk-Forward 결과: {len(self.folds)}개 폴드"]
        for fold in self.folds:
            in_m = calculate_metrics(fold.in_sample_result)
            out_m = calculate_metrics(fold.out_sample_result)
            overfit_str = " ⚠️ 과최적화" if fold.is_overfit else ""
            lines.append(
                f"  Fold {fold.fold_idx}: "
                f"인샘플 샤프={in_m.sharpe_ratio:.2f}, "
                f"아웃샘플 샤프={out_m.sharpe_ratio:.2f}{overfit_str}"
            )
        lines.append(f"과최적화 폴드: {self.n_overfit}/{len(self.folds)} ({self.overfit_ratio:.0%})")
        return "\n".join(lines)


class WalkForwardValidator:
    """Walk-Forward 검증기.

    인샘플 기간(in_sample_months)으로 전략을 평가하고,
    아웃샘플 기간(out_sample_months)으로 실제 성과를 검증한다.
    슬라이딩 윈도우 방식으로 전체 데이터에 걸쳐 반복한다.

    Args:
        engine: BacktestEngine 인스턴스.
        in_sample_months: 인샘플 기간 (월, 기본 12).
        out_sample_months: 아웃샘플 기간 (월, 기본 3).
        trading_days_per_month: 월평균 거래일 (기본 21).
    """

    def __init__(
        self,
        engine: BacktestEngine,
        in_sample_months: int = 12,
        out_sample_months: int = 3,
        trading_days_per_month: int = 21,
    ) -> None:
        self._engine = engine
        self._in_sample_days = in_sample_months * trading_days_per_month
        self._out_sample_days = out_sample_months * trading_days_per_month

    def validate(
        self,
        symbol: str,
        candles: list[Candle],
    ) -> WalkForwardResult:
        """Walk-Forward 검증 실행.

        Args:
            symbol: 종목 코드.
            candles: 전체 캔들 목록 (오래된 순).

        Returns:
            WalkForwardResult.
        """
        window = self._in_sample_days + self._out_sample_days
        n = len(candles)

        if n < window:
            logger.warning(
                "캔들 수 부족 — Walk-Forward 불가 (필요: %d, 현재: %d)", window, n
            )
            return WalkForwardResult()

        folds: list[WalkForwardFold] = []
        fold_idx = 0
        start = 0

        while start + window <= n:
            in_end = start + self._in_sample_days
            out_end = in_end + self._out_sample_days

            in_candles = candles[start:in_end]
            out_candles = candles[in_end:out_end]

            # 인샘플 백테스트
            in_result = self._engine.run(symbol, in_candles)
            in_metrics = calculate_metrics(in_result)

            # 아웃샘플 백테스트
            out_result = self._engine.run(symbol, out_candles)
            out_metrics = calculate_metrics(out_result)

            # 과최적화 감지: 아웃샘플 샤프가 인샘플 대비 30% 이상 저하
            is_overfit = self._detect_overfitting(in_metrics.sharpe_ratio, out_metrics.sharpe_ratio)

            if is_overfit:
                logger.warning(
                    "과최적화 감지 — Fold %d: 인샘플 샤프=%.2f, 아웃샘플 샤프=%.2f",
                    fold_idx,
                    in_metrics.sharpe_ratio,
                    out_metrics.sharpe_ratio,
                )

            folds.append(
                WalkForwardFold(
                    fold_idx=fold_idx,
                    in_sample_start=start,
                    in_sample_end=in_end,
                    out_sample_start=in_end,
                    out_sample_end=out_end,
                    in_sample_result=in_result,
                    out_sample_result=out_result,
                    is_overfit=is_overfit,
                )
            )

            fold_idx += 1
            start += self._out_sample_days  # 슬라이딩 스텝 = 아웃샘플 기간

        n_overfit = sum(1 for f in folds if f.is_overfit)
        overfit_ratio = n_overfit / len(folds) if folds else 0.0

        return WalkForwardResult(
            folds=folds,
            n_overfit=n_overfit,
            overfit_ratio=overfit_ratio,
        )

    @staticmethod
    def _detect_overfitting(in_sharpe: float, out_sharpe: float) -> bool:
        """과최적화 감지.

        인샘플 샤프지수 대비 아웃샘플 샤프지수 저하율이 30% 초과 시 과최적화.

        Args:
            in_sharpe: 인샘플 샤프지수.
            out_sharpe: 아웃샘플 샤프지수.

        Returns:
            True이면 과최적화 의심.
        """
        # 인샘플이 양수가 아니면 비교 불가 (의미없는 기준선)
        if in_sharpe <= 0:
            return False

        degradation = (in_sharpe - out_sharpe) / in_sharpe
        return degradation > _OVERFITTING_THRESHOLD
