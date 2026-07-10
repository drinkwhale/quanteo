"""core.app 정상 종료(_shutdown) / 잔여 태스크 취소(_cancel_pending_tasks) 테스트.

버그 배경: asyncio.TaskGroup은 그룹 내 모든 태스크가 끝나야 빠져나간다.
_wait_stop()이 정상 반환되는 것만으로는 position-sync 같은 무한 폴링 태스크가
취소되지 않아 SIGTERM을 받아도 프로세스가 종료되지 않았다 (PositionSyncFeed.stop()을
_shutdown()이 호출하지 않았기 때문). 이 테스트는 그 회귀를 막는다.
"""

from __future__ import annotations

import asyncio

import pytest

from core.app import _cancel_pending_tasks, _shutdown


class _FakeStoppable:
    """bus/notifier/info_system/position_sync 공통 인터페이스를 흉내내는 페이크."""

    def __init__(self, raise_on_stop: bool = False) -> None:
        self.stop_called = False
        self._raise_on_stop = raise_on_stop

    async def stop(self) -> None:
        self.stop_called = True
        if self._raise_on_stop:
            raise RuntimeError("stop 실패")


class _FakeStore:
    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_shutdown_stops_bus_and_notifier() -> None:
    bus = _FakeStoppable()
    notifier = _FakeStoppable()

    await _shutdown(bus, notifier, _FakeStore())

    assert bus.stop_called
    assert notifier.stop_called


@pytest.mark.asyncio
async def test_shutdown_stops_position_sync_when_provided() -> None:
    """회귀 테스트 — position_sync.stop()이 호출되지 않던 버그."""
    bus = _FakeStoppable()
    notifier = _FakeStoppable()
    position_sync = _FakeStoppable()

    await _shutdown(bus, notifier, _FakeStore(), position_sync=position_sync)

    assert position_sync.stop_called


@pytest.mark.asyncio
async def test_shutdown_stops_info_system_when_provided() -> None:
    bus = _FakeStoppable()
    notifier = _FakeStoppable()
    info_system = _FakeStoppable()

    await _shutdown(bus, notifier, _FakeStore(), info_system=info_system)

    assert info_system.stop_called


@pytest.mark.asyncio
async def test_shutdown_swallows_position_sync_stop_exception() -> None:
    """position_sync.stop()이 실패해도 나머지 종료 절차는 계속돼야 한다."""
    bus = _FakeStoppable()
    notifier = _FakeStoppable()
    position_sync = _FakeStoppable(raise_on_stop=True)
    info_system = _FakeStoppable()

    await _shutdown(
        bus, notifier, _FakeStore(), info_system=info_system, position_sync=position_sync
    )

    assert position_sync.stop_called
    assert info_system.stop_called  # position_sync 실패에도 계속 진행돼야 함


@pytest.mark.asyncio
async def test_shutdown_without_position_sync_does_not_raise() -> None:
    """position_sync=None(기본값)일 때 기존 동작 그대로 유지."""
    bus = _FakeStoppable()
    notifier = _FakeStoppable()

    await _shutdown(bus, notifier, _FakeStore())  # position_sync 생략


@pytest.mark.asyncio
async def test_cancel_pending_tasks_cancels_only_undone_tasks() -> None:
    """완료된 태스크는 건드리지 않고, 남은 태스크만 취소해야 한다."""

    async def _finishes_immediately() -> None:
        return None

    async def _runs_forever() -> None:
        await asyncio.sleep(3600)

    done_task = asyncio.create_task(_finishes_immediately())
    pending_task = asyncio.create_task(_runs_forever())
    await asyncio.sleep(0)  # done_task가 끝날 시간을 준다
    assert done_task.done()
    assert not pending_task.done()

    _cancel_pending_tasks([done_task, pending_task])

    with pytest.raises(asyncio.CancelledError):
        await pending_task

    assert pending_task.cancelled()
    # done_task는 이미 끝났으므로 취소 요청이 영향을 주지 않아야 함
    assert done_task.done()
    assert not done_task.cancelled()
