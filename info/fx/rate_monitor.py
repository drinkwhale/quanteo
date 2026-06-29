"""
환율 수집 및 급변 감지.

yfinance로 USD/KRW, DXY, JPY/KRW, CNY/KRW, EUR/USD를 조회하고
임계값 초과 시 InfoNotifier로 알람을 발송한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytz

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

# yfinance 티커 매핑
FX_TICKERS = {
    "usdkrw": "USDKRW=X",
    "dxy": "DX-Y.NYB",
    "jpykrw": "JPYKRW=X",
    "cnykrw": "CNYKRW=X",
    "eurusd": "EURUSD=X",
}

# 급변 임계값 (%)
ALERT_THRESHOLDS = {
    "usdkrw": 1.0,   # ±1% 이상 → 🔴 즉시 / ±0.5~1% → 🟡
    "dxy": 0.5,
    "jpykrw": 1.5,
    "cnykrw": 1.0,
    "eurusd": 0.7,
}

WARN_THRESHOLD_USDKRW = 0.5  # 🟡 경보 임계값 (USD/KRW 전용)


@dataclass
class FxSnapshot:
    """환율 스냅샷 데이터."""

    usdkrw: float = 0.0
    dxy: float = 0.0
    jpykrw: float = 0.0
    cnykrw: float = 0.0
    eurusd: float = 0.0

    usdkrw_change_pct: float = 0.0
    dxy_change_pct: float = 0.0
    jpykrw_change_pct: float = 0.0
    cnykrw_change_pct: float = 0.0
    eurusd_change_pct: float = 0.0

    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=pytz.UTC))

    def exceeds_threshold(self, pair: str) -> bool:
        """해당 환율 쌍이 급변 임계값을 초과했는지 확인."""
        change = abs(getattr(self, f"{pair}_change_pct", 0.0))
        return change >= ALERT_THRESHOLDS.get(pair, float("inf"))


class FxRateMonitor:
    """환율 수집 및 급변 감지 모니터."""

    def __init__(
        self,
        info_notifier=None,
        base_snapshot: FxSnapshot | None = None,
    ) -> None:
        self._notifier = info_notifier
        self._base: FxSnapshot | None = base_snapshot
        self._base_is_provisional = False

    async def snapshot(self) -> FxSnapshot:
        """현재 환율 스냅샷을 조회한다."""
        loop = asyncio.get_event_loop()
        snap = await loop.run_in_executor(None, self._fetch_sync)

        # 기준가 초기화
        if self._base is None:
            now_kst = datetime.now(tz=KST)
            if now_kst.hour >= 9:
                # 09:00 이후 기동: yfinance history로 시가 역산
                self._base = await loop.run_in_executor(None, self._fetch_open_prices)
                if self._base is None:
                    self._base = snap
                    self._base_is_provisional = True
            else:
                # 09:00 이전 기동: 잠정 base
                self._base = snap
                self._base_is_provisional = True

        snap = self._calc_changes(snap)
        return snap

    def _fetch_sync(self) -> FxSnapshot:
        """yfinance 동기 조회."""
        import yfinance as yf

        tickers = list(FX_TICKERS.values())
        data = yf.download(
            tickers,
            period="1d",
            interval="1m",
            progress=False,
            auto_adjust=True,
        )

        result: dict[str, float] = {}
        for key, ticker in FX_TICKERS.items():
            try:
                if "Close" in data.columns:
                    close = data["Close"][ticker].dropna()
                else:
                    close = data[ticker]["Close"].dropna()

                if close.empty:
                    logger.warning("yfinance None/NaN 반환: %s — 알람 계산 생략", ticker)
                    result[key] = 0.0
                else:
                    result[key] = float(close.iloc[-1])
            except Exception as exc:
                logger.warning("환율 파싱 실패 %s: %s", ticker, exc)
                result[key] = 0.0

        return FxSnapshot(
            usdkrw=result.get("usdkrw", 0.0),
            dxy=result.get("dxy", 0.0),
            jpykrw=result.get("jpykrw", 0.0),
            cnykrw=result.get("cnykrw", 0.0),
            eurusd=result.get("eurusd", 0.0),
        )

    def _fetch_open_prices(self) -> FxSnapshot | None:
        """당일 09:00 KST 시가를 yfinance history로 역산한다."""
        import yfinance as yf

        tickers = list(FX_TICKERS.values())
        try:
            data = yf.download(
                tickers,
                period="1d",
                interval="1m",
                progress=False,
                auto_adjust=True,
            )
        except Exception as exc:
            logger.warning("yfinance history 조회 실패: %s", exc)
            return None

        # 09:00 KST = 00:00 UTC
        result: dict[str, float] = {}
        for key, ticker in FX_TICKERS.items():
            try:
                if "Close" in data.columns:
                    series = data["Close"][ticker].dropna()
                else:
                    series = data[ticker]["Close"].dropna()

                if series.empty:
                    result[key] = 0.0
                else:
                    result[key] = float(series.iloc[0])  # 당일 첫 캔들 = 시가
            except Exception:
                result[key] = 0.0

        if all(v == 0.0 for v in result.values()):
            return None

        return FxSnapshot(
            usdkrw=result.get("usdkrw", 0.0),
            dxy=result.get("dxy", 0.0),
            jpykrw=result.get("jpykrw", 0.0),
            cnykrw=result.get("cnykrw", 0.0),
            eurusd=result.get("eurusd", 0.0),
        )

    def _calc_changes(self, current: FxSnapshot) -> FxSnapshot:
        """기준가 대비 변동률을 계산한 새 FxSnapshot 반환."""
        if self._base is None:
            return current

        def pct(cur: float, base: float) -> float:
            if base == 0:
                return 0.0
            return (cur - base) / base * 100

        return FxSnapshot(
            usdkrw=current.usdkrw,
            dxy=current.dxy,
            jpykrw=current.jpykrw,
            cnykrw=current.cnykrw,
            eurusd=current.eurusd,
            usdkrw_change_pct=pct(current.usdkrw, self._base.usdkrw),
            dxy_change_pct=pct(current.dxy, self._base.dxy),
            jpykrw_change_pct=pct(current.jpykrw, self._base.jpykrw),
            cnykrw_change_pct=pct(current.cnykrw, self._base.cnykrw),
            eurusd_change_pct=pct(current.eurusd, self._base.eurusd),
            timestamp=current.timestamp,
        )

    async def check_and_alert(self) -> FxSnapshot:
        """스냅샷 조회 후 임계값 초과 시 알람 발송."""
        snap = await self.snapshot()

        if self._notifier:
            for pair in ALERT_THRESHOLDS:
                current_val = getattr(snap, pair, 0.0)
                if current_val == 0.0:
                    continue  # 데이터 없음(None/NaN) — 알람 오발 방지
                if snap.exceeds_threshold(pair):
                    try:
                        await self._notifier.send_fx_alert(snap)
                        break  # 한 번만 발송
                    except Exception as exc:
                        logger.error("환율 알람 발송 실패: %s", exc)

        return snap
