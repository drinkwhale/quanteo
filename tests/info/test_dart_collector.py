"""DartCollector 단위 테스트."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from info.news.dart_collector import DartCollector, IMPORTANT_REPORT_TYPES


def _make_dart_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 공시 유형 필터링
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_important_report_filtered():
    collector = DartCollector(api_key="test-key")
    df = _make_dart_df([
        {
            "report_nm": "유상증자결정",
            "rcept_dt": "20260629",
            "rcept_no": "20260629000001",
        }
    ])

    mock_dart = MagicMock()
    mock_dart.list.return_value = df

    with patch("info.news.dart_collector.OpenDartReader", return_value=mock_dart):
        items = await collector.fetch()

    assert len(items) == 1
    assert items[0].source == "DART"


@pytest.mark.asyncio
async def test_unimportant_report_excluded():
    collector = DartCollector(api_key="test-key")
    df = _make_dart_df([
        {
            "report_nm": "분기보고서",
            "rcept_dt": "20260629",
            "rcept_no": "20260629000002",
        }
    ])

    mock_dart = MagicMock()
    mock_dart.list.return_value = df

    with patch("info.news.dart_collector.OpenDartReader", return_value=mock_dart):
        items = await collector.fetch()

    assert len(items) == 0


# ---------------------------------------------------------------------------
# HIGH 강제 알람
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_important_report_triggers_high_alert():
    mock_notifier = AsyncMock()
    mock_notifier.send_news_alert = AsyncMock()

    collector = DartCollector(api_key="test-key", info_notifier=mock_notifier)
    df = _make_dart_df([
        {
            "report_nm": "주요사항보고서",
            "rcept_dt": "20260629",
            "rcept_no": "20260629000003",
        }
    ])

    mock_dart = MagicMock()
    mock_dart.list.return_value = df

    with patch("info.news.dart_collector.OpenDartReader", return_value=mock_dart):
        await collector.fetch()

    mock_notifier.send_news_alert.assert_called_once()
    args = mock_notifier.send_news_alert.call_args[0]
    assert args[1].score == "HIGH"


# ---------------------------------------------------------------------------
# API 장애 처리
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_error_returns_empty(caplog):
    collector = DartCollector(api_key="test-key")

    with patch(
        "info.news.dart_collector.OpenDartReader",
        side_effect=Exception("network error"),
    ):
        with caplog.at_level(logging.ERROR):
            items = await collector.fetch()

    assert items == []
    assert any("DART" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_auth_failure_returns_empty():
    collector = DartCollector(api_key="bad-key")

    mock_dart = MagicMock()
    mock_dart.list.side_effect = Exception("인증 실패")

    with patch("info.news.dart_collector.OpenDartReader", return_value=mock_dart):
        items = await collector.fetch()

    assert items == []


# ---------------------------------------------------------------------------
# 공시 없음 — Telegram 미발송
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_result_no_telegram():
    mock_notifier = AsyncMock()
    mock_notifier.send_news_alert = AsyncMock()

    collector = DartCollector(api_key="test-key", info_notifier=mock_notifier)
    mock_dart = MagicMock()
    mock_dart.list.return_value = pd.DataFrame()

    with patch("info.news.dart_collector.OpenDartReader", return_value=mock_dart):
        items = await collector.fetch()

    assert items == []
    mock_notifier.send_news_alert.assert_not_called()
