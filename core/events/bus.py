"""
Event Bus — 발행/구독(Pub/Sub) 구현.

asyncio.Queue 기반의 비동기 이벤트 버스.
동기 핸들러와 비동기 핸들러를 모두 지원한다.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Union

from core.events.types import Event, EventType

logger = logging.getLogger(__name__)

SyncHandler = Callable[[Event], None]
AsyncHandler = Callable[[Event], Awaitable[None]]
Handler = Union[SyncHandler, AsyncHandler]


class EventBus:
    """비동기 Event Bus.

    사용 예::

        bus = EventBus()
        bus.subscribe(EventType.TICK, my_handler)
        await bus.start()

        await bus.publish(Event(type=EventType.TICK, payload=tick))

        await bus.stop()
    """

    def __init__(self, queue_maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=queue_maxsize)
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._wildcard_handlers: list[Handler] = []
        self._task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # 구독
    # ------------------------------------------------------------------

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        """특정 이벤트 타입을 구독한다."""
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: Handler) -> None:
        """모든 이벤트 타입을 구독한다 (와일드카드)."""
        self._wildcard_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        """구독을 해제한다."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    # ------------------------------------------------------------------
    # 발행
    # ------------------------------------------------------------------

    async def publish(self, event: Event) -> None:
        """이벤트를 큐에 넣는다. 큐가 가득 차면 새 이벤트를 버린다."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("EventBus 큐 포화 — 이벤트 드롭 (type=%s)", event.type)

    def publish_nowait(self, event: Event) -> bool:
        """동기 컨텍스트에서 이벤트를 발행한다. 성공 여부를 반환한다."""
        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            logger.warning("EventBus 큐 포화 — 이벤트 드롭 (type=%s)", event.type)
            return False

    # ------------------------------------------------------------------
    # 라이프사이클
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """디스패치 루프를 백그라운드 태스크로 시작한다."""
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop(), name="event-bus")
        logger.info("EventBus 시작")

    async def stop(self) -> None:
        """디스패치 루프를 종료한다."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("EventBus 종료")

    async def _dispatch_loop(self) -> None:
        """큐에서 이벤트를 꺼내 핸들러를 호출한다."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            await self._dispatch(event)
            self._queue.task_done()

    async def _dispatch(self, event: Event) -> None:
        """이벤트를 등록된 모든 핸들러에 전달한다."""
        handlers = list(self._handlers.get(event.type, [])) + self._wildcard_handlers

        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as exc:
                logger.error(
                    "EventBus 핸들러 예외 (type=%s handler=%s): %s",
                    event.type,
                    getattr(handler, "__name__", repr(handler)),
                    exc,
                    exc_info=True,
                )

    async def join(self) -> None:
        """큐의 모든 이벤트가 처리될 때까지 기다린다 (주로 테스트용)."""
        await self._queue.join()

    @property
    def qsize(self) -> int:
        return self._queue.qsize()
