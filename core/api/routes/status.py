"""GET /status — 봇 운영 상태 조회."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from core.api.deps import ContainerDep
from core.api.models import BotStatus

router = APIRouter()


@router.get("/status", response_model=BotStatus, summary="봇 상태 조회")
async def get_status(container: ContainerDep) -> BotStatus:
    """현재 봇의 실행 상태, halt_level, 환경 정보를 반환한다."""
    now = datetime.now(UTC)
    uptime = (now - container.started_at).total_seconds()
    halt_level = container.risk._halt.value  # type: ignore[attr-defined]

    return BotStatus(
        running=True,
        halt_level=halt_level,
        env=container.env,
        market=container.market,
        uptime_seconds=uptime,
        started_at=container.started_at,
    )
