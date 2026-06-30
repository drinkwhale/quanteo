"""
통합 테스트: FxRateMonitor 급변 감지 → Telegram 알람 라운드트립.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz

from info.fx.daily_report import FxDailyReport
from info.fx.rate_monitor import FxSnapshot


# ────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ────────────────────────────────────────────────────────────────────────────


def _snapshot(usdkrw_change_pct: float = 0.0) -> FxSnapshot:
    return FxSnapshot(
        usdkrw=1350.0,
        dxy=104.0,
        jpykrw=9.1,
        cnykrw=185.0,
        eurusd=1.08,
        usdkrw_change_pct=usdkrw_change_pct,
        dxy_change_pct=0.0,
        jpykrw_change_pct=0.0,
        cnykrw_change_pct=0.0,
        eurusd_change_pct=0.0,
    )


# ────────────────────────────────────────────────────────────────────────────
# 테스트
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fx_alert_sent_on_threshold_breach():
    """USD/KRW가 임계값을 초과하면 InfoNotifier.send_fx_alert를 호출해야 한다."""
    from info.fx.rate_monitor import FxRateMonitor

    mock_notifier = MagicMock()
    mock_notifier.send_fx_alert = AsyncMock()

    monitor = FxRateMonitor(info_notifier=mock_notifier)
    # 기준 스냅샷 설정 (임계값 1% 기본)
    monitor._base = _snapshot(usdkrw_change_pct=0.0)

    # 현재 값이 임계값(1%) 초과
    big_move_snap = _snapshot(usdkrw_change_pct=1.5)
    with patch.object(monitor, "snapshot", AsyncMock(return_value=big_move_snap)):
        result = await monitor.check_and_alert()

    mock_notifier.send_fx_alert.assert_called_once_with(big_move_snap)


@pytest.mark.asyncio
async def test_fx_no_alert_within_threshold():
    """USD/KRW가 임계값 이하이면 알람이 발생하지 않아야 한다."""
    from info.fx.rate_monitor import FxRateMonitor

    mock_notifier = MagicMock()
    mock_notifier.send_fx_alert = AsyncMock()

    monitor = FxRateMonitor(info_notifier=mock_notifier)
    monitor._base = _snapshot(usdkrw_change_pct=0.0)

    small_snap = _snapshot(usdkrw_change_pct=0.3)
    with patch.object(monitor, "snapshot", AsyncMock(return_value=small_snap)):
        await monitor.check_and_alert()

    mock_notifier.send_fx_alert.assert_not_called()


@pytest.mark.asyncio
async def test_fx_zero_value_skips_alert():
    """현재 환율이 0.0이면 알람이 발생하지 않아야 한다 (오발 방지)."""
    from info.fx.rate_monitor import FxRateMonitor

    mock_notifier = MagicMock()
    mock_notifier.send_fx_alert = AsyncMock()

    monitor = FxRateMonitor(info_notifier=mock_notifier)
    monitor._base = _snapshot()

    zero_snap = FxSnapshot(
        usdkrw=0.0,  # yfinance 조회 실패
        dxy=0.0,
        jpykrw=0.0,
        cnykrw=0.0,
        eurusd=0.0,
        usdkrw_change_pct=0.0,
        dxy_change_pct=0.0,
        jpykrw_change_pct=0.0,
        cnykrw_change_pct=0.0,
        eurusd_change_pct=0.0,
    )
    with patch.object(monitor, "snapshot", AsyncMock(return_value=zero_snap)):
        await monitor.check_and_alert()

    mock_notifier.send_fx_alert.assert_not_called()


@pytest.mark.asyncio
async def test_fx_daily_report_pipeline():
    """FxDailyReporter.generate() → InfoNotifier.send_fx_daily_report 파이프라인."""
    from info.fx.daily_report import FxDailyReporter, FxDailyReport
    from info.telegram.info_notifier import InfoNotifier

    mock_base_notifier = MagicMock()
    notifier = InfoNotifier(telegram_notifier=mock_base_notifier, chat_id="test")
    notifier._send_text = AsyncMock()

    fake_report = FxDailyReport(
        date=datetime(2026, 7, 14, 16, 0, tzinfo=pytz.timezone("Asia/Seoul")),
        usdkrw=1350.0,
        dxy=104.0,
        jpykrw=9.1,
        cnykrw=185.0,
        usdkrw_change_pct=-0.5,
        dxy_change_pct=0.1,
        jpykrw_change_pct=0.0,
        cnykrw_change_pct=0.0,
        summary="달러 소폭 약세",
    )

    with patch.object(FxDailyReporter, "generate", AsyncMock(return_value=fake_report)):
        reporter = FxDailyReporter(info_notifier=notifier)
        report = await reporter.generate()
        await notifier.send_fx_daily_report(report)

    notifier._send_text.assert_called_once()
