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
async def test_shutdown_stops_order_sync_when_provided() -> None:
    bus = _FakeStoppable()
    notifier = _FakeStoppable()
    order_sync = _FakeStoppable()

    await _shutdown(bus, notifier, _FakeStore(), order_sync=order_sync)

    assert order_sync.stop_called


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


@pytest.mark.asyncio
async def test_real_taskgroup_exits_after_stop_even_with_hookless_task() -> None:
    """실제 asyncio.TaskGroup으로 원래 버그 시나리오를 재현하는 통합 테스트.

    core/app.py의 run()이 실제로 하는 일을 축소 재현한다:
    - position_sync 같은 "stop() 훅이 있는" 무한 루프 태스크
    - toss-trading(feed/engine) 같은 "stop() 훅이 없는" 무한 루프 태스크
    - _wait_stop() 같은 조정 태스크: stop_event를 기다렸다가 _shutdown() 호출 후
      _cancel_pending_tasks()로 나머지를 정리

    수정 전 코드였다면 이 테스트는 타임아웃으로 실패했을 것이다 (TaskGroup이
    hookless 태스크가 끝나길 무한정 기다리므로).
    """
    stop_event = asyncio.Event()
    position_sync = _FakeStoppable()
    tasks: list[asyncio.Task] = []

    async def _position_sync_loop() -> None:
        while not position_sync.stop_called:
            await asyncio.sleep(0.01)
            if position_sync.stop_called:
                return
        return

    async def _hookless_trading_loop() -> None:
        # 자체 stop() 훅이 없는 태스크 — 강제 취소로만 끝난다.
        await asyncio.sleep(3600)

    async def _wait_stop() -> None:
        await stop_event.wait()
        await _shutdown(_FakeStoppable(), _FakeStoppable(), _FakeStore(), position_sync=position_sync)
        _cancel_pending_tasks(tasks)

    async def _run_group() -> None:
        async with asyncio.TaskGroup() as tg:
            tasks.append(tg.create_task(_position_sync_loop(), name="position-sync"))
            tasks.append(tg.create_task(_hookless_trading_loop(), name="toss-trading"))
            tg.create_task(_wait_stop(), name="shutdown-watcher")
            await asyncio.sleep(0.02)
            stop_event.set()

    # contextlib.suppress는 except*(exception group) 문법을 지원하지 않아 여기서는
    # try/except*를 그대로 사용한다.
    try:  # noqa: SIM105
        await asyncio.wait_for(_run_group(), timeout=2.0)
    except* asyncio.CancelledError:
        pass  # 취소된 hookless 태스크의 CancelledError는 정상 종료의 일부

    assert position_sync.stop_called
