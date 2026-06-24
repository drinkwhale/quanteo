"""
GET /stream — WebSocket 실시간 스트림.

Event Bus의 모든 이벤트를 JSON으로 클라이언트에 브로드캐스트한다.
연결 수는 소규모(대시보드 1~2개)를 가정한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.api.deps import ContainerDep
from core.events.types import Event

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_event(event: Event) -> str:
    """Event를 JSON 문자열로 변환한다."""
    payload = event.payload
    # dataclass/frozen 객체는 __dict__ 로 풀기
    if hasattr(payload, "__dict__"):
        payload = payload.__dict__
    elif hasattr(payload, "_asdict"):
        payload = payload._asdict()

    return json.dumps(
        {
            "event_type": event.type.value,
            "payload": payload,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source,
        },
        default=str,  # datetime, Enum 등 직렬화 폴백
    )


@router.websocket("/stream")
async def stream(websocket: WebSocket, container: ContainerDep) -> None:
    """Event Bus의 모든 이벤트를 실시간으로 스트리밍한다.

    클라이언트가 연결되면 개인 큐를 생성하고 EventBus 와일드카드로 구독한다.
    연결이 끊기면 구독을 해제한다.
    """
    await websocket.accept()
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=500)

    def _enqueue(event: Event) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("스트림 큐 포화 — 이벤트 드롭 (type=%s)", event.type)

    container.bus.subscribe_all(_enqueue)
    logger.info("WebSocket 클라이언트 연결: %s", websocket.client)

    try:
        # 연결 확인 메시지
        await websocket.send_text(
            json.dumps({"event_type": "connected", "timestamp": datetime.now(UTC).isoformat()})
        )

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_text(_serialize_event(event))
            except TimeoutError:
                # 30초 heartbeat — 연결 유지 확인
                await websocket.send_text(
                    json.dumps({"event_type": "heartbeat", "timestamp": datetime.now(UTC).isoformat()})
                )
    except WebSocketDisconnect:
        logger.info("WebSocket 클라이언트 연결 해제: %s", websocket.client)
    except Exception as exc:
        logger.error("WebSocket 오류: %s", exc, exc_info=True)
    finally:
        container.bus.unsubscribe_all(_enqueue) if hasattr(container.bus, "unsubscribe_all") else None
        container.bus._wildcard_handlers.remove(_enqueue) if _enqueue in container.bus._wildcard_handlers else None
