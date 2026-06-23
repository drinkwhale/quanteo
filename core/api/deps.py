"""
FastAPI 의존성 주입 (Dependency Injection).

앱 컨테이너가 보유한 객체를 라우터에 주입한다.
Request-scoped DI 대신 앱 단위 싱글톤 컨테이너를 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request

from core.events.bus import EventBus
from core.risk.manager import RiskManager
from core.store.db import StateStore


@dataclass
class AppContainer:
    """Control API가 사용하는 핵심 컴포넌트 컨테이너.

    app.py에서 생성 후 FastAPI app.state.container 에 저장한다.
    """

    store: StateStore
    risk: RiskManager
    bus: EventBus
    env: str = "vps"
    market: str = "domestic"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[no-any-return]


ContainerDep = Annotated[AppContainer, Depends(_get_container)]
