"""
FastAPI 의존성 주입 (Dependency Injection).

앱 컨테이너가 보유한 객체를 라우터에 주입한다.
Request-scoped DI 대신 앱 단위 싱글톤 컨테이너를 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from core.events.bus import EventBus
from core.risk.manager import RiskManager
from core.store.db import StateStore

if TYPE_CHECKING:
    from core.adapters.toss.rest import TossRestClient


@dataclass
class AppContainer:
    """Control API가 사용하는 핵심 컴포넌트 컨테이너.

    app.py에서 생성 후 FastAPI app.state.container 에 저장한다.
    """

    store: StateStore
    risk: RiskManager
    bus: EventBus
    env: str = "prod"
    market: str = "domestic"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Toss 브로커 어댑터 (선택: Toss 환경에서만 주입)
    broker: "TossRestClient | None" = None


def _get_container(conn: HTTPConnection) -> AppContainer:
    """HTTP Request와 WebSocket 양쪽에서 재사용 가능한 컨테이너 조회.

    Request/WebSocket은 둘 다 HTTPConnection을 상속하므로, 이 타입으로
    받아야 /stream(WebSocket) 라우트에서도 동일 의존성을 쓸 수 있다.
    """
    return conn.app.state.container  # type: ignore[no-any-return]


ContainerDep = Annotated[AppContainer, Depends(_get_container)]
