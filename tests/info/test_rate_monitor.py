"""FxRateMonitor 단위 테스트."""

from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz

from info.fx.rate_monitor import FxRateMonitor, FxSnapshot, ALERT_THRESHOLDS

KST = pytz.timezone("Asia/Seoul")


def _base_snap(usdkrw=1380.0, dxy=104.0) -> FxSnapshot:
    return FxSnapshot(usdkrw=usdkrw, dxy=dxy, jpykrw=9.2, cnykrw=190.0, eurusd=1.07)


def _make_monitor(notifier=None, base: FxSnapshot | None = None) -> FxRateMonitor:
    m = FxRateMonitor(info_notifier=notifier, base_snapshot=base)
    return m


# ---------------------------------------------------------------------------
# 임계값 경계 케이스
# ---------------------------------------------------------------------------


def test_exceeds_threshold_just_below():
    snap = FxSnapshot(
        usdkrw=1393.79,  # +0.999% (< 1%) — 임계값 미달
        usdkrw_change_pct=0.999,
    )
    assert not snap.exceeds_threshold("usdkrw")


def test_exceeds_threshold_just_above():
    snap = FxSnapshot(
        usdkrw=1393.80,  # +1.001% (> 1%) — 임계값 초과
        usdkrw_change_pct=1.001,
    )
    assert snap.exceeds_threshold("usdkrw")


# ---------------------------------------------------------------------------
# 09:00 이후 기동 시 history() 호출
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_after_0900_uses_history():
    monitor = _make_monitor()

    current_snap = _base_snap()
    open_snap = FxSnapshot(usdkrw=1370.0, dxy=103.0, jpykrw=9.0, cnykrw=188.0, eurusd=1.06)

    after_9am = datetime(2026, 6, 29, 10, 0, 0, tzinfo=KST)

    with patch("info.fx.rate_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = after_9am

        with patch.object(monitor, "_fetch_sync", return_value=current_snap):
            with patch.object(monitor, "_fetch_open_prices", return_value=open_snap) as mock_open:
                await monitor.snapshot()

    mock_open.assert_called_once()
    assert monitor._base.usdkrw == 1370.0


# ---------------------------------------------------------------------------
# yfinance None/NaN 반환 시 알람 미발송
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_value_no_alert(caplog):
    mock_notifier = AsyncMock()
    mock_notifier.send_fx_alert = AsyncMock()

    # usdkrw=0 → 변동률 계산 생략, 알람 없음
    base = FxSnapshot(usdkrw=1380.0)
    monitor = _make_monitor(notifier=mock_notifier, base=base)

    zero_snap = FxSnapshot(usdkrw=0.0, usdkrw_change_pct=0.0)

    with patch.object(monitor, "_fetch_sync", return_value=zero_snap):
        with caplog.at_level(logging.WARNING):
            await monitor.check_and_alert()

    mock_notifier.send_fx_alert.assert_not_called()


# ---------------------------------------------------------------------------
# 급변 감지 → 알람 발송
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_threshold_exceeded_triggers_alert():
    mock_notifier = AsyncMock()
    mock_notifier.send_fx_alert = AsyncMock()

    base = FxSnapshot(usdkrw=1380.0, dxy=104.0, jpykrw=9.2, cnykrw=190.0, eurusd=1.07)
    monitor = _make_monitor(notifier=mock_notifier, base=base)

    # +1.5% 급변
    current = FxSnapshot(usdkrw=1400.7, dxy=104.0, jpykrw=9.2, cnykrw=190.0, eurusd=1.07)

    with patch.object(monitor, "_fetch_sync", return_value=current):
        await monitor.check_and_alert()

    mock_notifier.send_fx_alert.assert_called_once()


# ---------------------------------------------------------------------------
# 임계값 미달 → 알람 없음
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_below_threshold_no_alert():
    mock_notifier = AsyncMock()
    mock_notifier.send_fx_alert = AsyncMock()

    base = FxSnapshot(usdkrw=1380.0, dxy=104.0, jpykrw=9.2, cnykrw=190.0, eurusd=1.07)
    monitor = _make_monitor(notifier=mock_notifier, base=base)

    # +0.3% — 임계값(1%) 미달
    current = FxSnapshot(usdkrw=1384.1, dxy=104.0, jpykrw=9.2, cnykrw=190.0, eurusd=1.07)

    with patch.object(monitor, "_fetch_sync", return_value=current):
        await monitor.check_and_alert()

    mock_notifier.send_fx_alert.assert_not_called()
