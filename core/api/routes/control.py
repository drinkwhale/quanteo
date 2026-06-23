"""POST /control/pause|resume|kill — 봇 제어 명령."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from core.api.deps import ContainerDep
from core.api.models import ApiResponse
from core.events.types import Event, EventType
from core.risk.models import HaltLevel

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/pause", response_model=ApiResponse, summary="봇 일시정지")
async def pause(container: ContainerDep) -> ApiResponse:
    """신규 포지션 진입을 중단한다. 기존 포지션은 유지된다."""
    prev = container.risk._halt
    if prev == HaltLevel.KILL:
        raise HTTPException(status_code=409, detail="킬스위치 상태에서는 pause로 되돌릴 수 없습니다.")

    container.risk._halt = HaltLevel.PAUSE
    await container.bus.publish(
        Event(type=EventType.STATUS, payload={"halt_level": HaltLevel.PAUSE}, source="control-api")
    )
    logger.info("봇 일시정지 (prev=%s)", prev)
    return ApiResponse(success=True, message="일시정지 완료")


@router.post("/resume", response_model=ApiResponse, summary="봇 재개")
async def resume(container: ContainerDep) -> ApiResponse:
    """일시정지 또는 REDUCE 상태를 정상 운영으로 되돌린다."""
    prev = container.risk._halt
    if prev == HaltLevel.KILL:
        raise HTTPException(status_code=409, detail="킬스위치 상태는 resume으로 해제할 수 없습니다.")

    container.risk._halt = HaltLevel.NONE
    await container.bus.publish(
        Event(type=EventType.STATUS, payload={"halt_level": HaltLevel.NONE}, source="control-api")
    )
    logger.info("봇 재개 (prev=%s)", prev)
    return ApiResponse(success=True, message="재개 완료")


@router.post("/kill", response_model=ApiResponse, summary="킬스위치 — 모든 신규 주문 차단")
async def kill(container: ContainerDep) -> ApiResponse:
    """모든 신규 주문을 차단한다. 손절 주문만 허용된다.

    이 상태는 봇 재시작 없이는 해제되지 않는다.
    """
    container.risk._halt = HaltLevel.KILL
    await container.bus.publish(
        Event(type=EventType.KILL_SWITCH, payload={"activated_by": "control-api"}, source="control-api")
    )
    logger.warning("킬스위치 활성화 (source=control-api)")
    return ApiResponse(success=True, message="킬스위치 활성화 — 모든 신규 주문 차단")
