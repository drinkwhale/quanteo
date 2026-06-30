"""InfoSystem 초기화·라이프사이클 단위 테스트."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 모든 deferred import는 소스 모듈 경로로 패치
_PATCH_MAKE_NOTIFIER = "core.notifier.factory.make_notifier"
_PATCH_SCHEDULER = "info.scheduler.InfoScheduler"
_PATCH_GCAL = "info.calendar.google_cal.GoogleCalendarClient"


def _make_settings():
    cfg = MagicMock()
    cfg.anthropic_api_key = "test-anthropic-key"
    cfg.finnhub_api_key = "test-finnhub-key"
    cfg.google_calendar_credentials_path = None
    cfg.telegram_chat_id = "test-chat-id"

    settings = MagicMock()
    settings.info = cfg
    settings.info.enabled = True
    return settings


@pytest.mark.asyncio
async def test_build_components_creates_all_components():
    """_build_components()가 모든 컴포넌트를 올바르게 생성하는지 확인."""
    from info.main import InfoSystem

    settings = _make_settings()

    with patch(_PATCH_MAKE_NOTIFIER, return_value=MagicMock()):
        with patch(_PATCH_SCHEDULER):
            with patch(_PATCH_GCAL):
                system = InfoSystem(settings)

    assert system.claude_filter is not None
    assert system.rss_collector is not None
    assert system.finnhub_collector is not None
    assert system.fx_monitor is not None
    assert system.fx_reporter is not None
    assert system.calendar_client is not None
    assert system.notifier is not None


@pytest.mark.asyncio
async def test_build_components_injects_notifier_to_fx():
    """fx_monitor·fx_reporter가 생성자에서 notifier를 받는지 확인 (역주입 없음)."""
    from info.main import InfoSystem
    from info.telegram.info_notifier import InfoNotifier

    settings = _make_settings()

    with patch(_PATCH_MAKE_NOTIFIER, return_value=MagicMock()):
        with patch(_PATCH_SCHEDULER):
            with patch(_PATCH_GCAL):
                system = InfoSystem(settings)

    # notifier가 생성자 주입으로 설정되어 있어야 함
    assert system.fx_monitor._notifier is system.notifier
    assert system.fx_reporter._notifier is system.notifier
    assert isinstance(system.notifier, InfoNotifier)


@pytest.mark.asyncio
async def test_start_stores_dlq_task_reference():
    """start()가 DLQ 태스크 참조를 저장하는지 확인."""
    from info.main import InfoSystem

    settings = _make_settings()

    mock_sched = MagicMock()
    mock_sched.start = MagicMock()

    with patch(_PATCH_MAKE_NOTIFIER, return_value=MagicMock()):
        with patch(_PATCH_SCHEDULER, return_value=mock_sched):
            with patch(_PATCH_GCAL):
                system = InfoSystem(settings)

    assert system._dlq_task is None  # 시작 전

    with patch.object(system.notifier, "retry_dlq", AsyncMock()):
        with patch("asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)):
            await system.start()

    assert system._dlq_task is not None
    assert isinstance(system._dlq_task, asyncio.Task)

    # 정리
    system._dlq_task.cancel()
    try:
        await system._dlq_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_stop_cancels_dlq_task():
    """stop()이 DLQ 태스크를 취소하고 await하는지 확인."""
    from info.main import InfoSystem

    settings = _make_settings()

    mock_sched = MagicMock()
    mock_sched.start = MagicMock()
    mock_sched.stop = MagicMock()

    with patch(_PATCH_MAKE_NOTIFIER, return_value=MagicMock()):
        with patch(_PATCH_SCHEDULER, return_value=mock_sched):
            with patch(_PATCH_GCAL):
                system = InfoSystem(settings)

    async def _cancelable():
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            raise

    with patch.object(system.notifier, "retry_dlq", AsyncMock()):
        with patch("asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)):
            await system.start()

    assert system._dlq_task is not None

    await system.stop()

    mock_sched.stop.assert_called_once()
    assert system._dlq_task.cancelled() or system._dlq_task.done()
