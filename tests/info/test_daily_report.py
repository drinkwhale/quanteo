"""FxDailyReporter 및 rate_rule 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from info.fx.daily_report import FxDailyReport, FxDailyReporter
from info.fx.rate_rule import interpret_fx, interpret_jpy


# ---------------------------------------------------------------------------
# rate_rule 매핑
# ---------------------------------------------------------------------------


def test_usd_up_dxy_up_risk_off():
    result = interpret_fx(usdkrw_change_pct=1.2, dxy_change_pct=0.5)
    assert "리스크오프" in result


def test_usd_up_dxy_flat_positive():
    result = interpret_fx(usdkrw_change_pct=0.8, dxy_change_pct=0.1)
    assert "긍정" in result


def test_usd_down_dxy_up_negative():
    result = interpret_fx(usdkrw_change_pct=-0.5, dxy_change_pct=0.4)
    assert "부정" in result


def test_usd_down_dxy_flat_negative():
    result = interpret_fx(usdkrw_change_pct=-0.3, dxy_change_pct=0.1)
    assert "부정" in result


def test_jpy_weak_positive():
    result = interpret_jpy(jpykrw_change_pct=-1.5)
    assert "긍정" in result


def test_jpy_strong_caution():
    result = interpret_jpy(jpykrw_change_pct=1.2)
    assert "주의" in result


def test_jpy_stable():
    result = interpret_jpy(jpykrw_change_pct=0.3)
    assert "안정" in result


# ---------------------------------------------------------------------------
# FxDailyReporter 리포트 생성
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_report():
    reporter = FxDailyReporter()

    mock_report = FxDailyReport(
        date=__import__("datetime").datetime.now(tz=__import__("pytz").UTC),
        usdkrw=1380.0,
        dxy=104.0,
        jpykrw=9.2,
        cnykrw=190.0,
        usdkrw_change_pct=0.5,
        dxy_change_pct=0.2,
        jpykrw_change_pct=-0.3,
        cnykrw_change_pct=0.1,
        summary="원화 소폭 약세 — 긍정",
    )

    with patch.object(reporter, "_generate_sync", return_value=mock_report):
        report = await reporter.generate()

    assert report.usdkrw == 1380.0
    assert "긍정" in report.summary


@pytest.mark.asyncio
async def test_generate_sends_notification():
    mock_notifier = AsyncMock()
    mock_notifier.send_fx_daily_report = AsyncMock()
    reporter = FxDailyReporter(info_notifier=mock_notifier)

    import datetime
    import pytz

    mock_report = FxDailyReport(
        date=datetime.datetime.now(tz=pytz.UTC),
        usdkrw=1380.0, dxy=104.0, jpykrw=9.2, cnykrw=190.0,
        usdkrw_change_pct=0.5, dxy_change_pct=0.2,
        jpykrw_change_pct=-0.3, cnykrw_change_pct=0.1,
        summary="테스트",
    )

    with patch.object(reporter, "_generate_sync", return_value=mock_report):
        await reporter.generate()

    mock_notifier.send_fx_daily_report.assert_called_once_with(mock_report)
