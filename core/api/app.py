"""
Control API FastAPI 앱 팩토리.

create_app()으로 앱 인스턴스를 생성하고 AppContainer를 주입한다.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.api.deps import AppContainer
from core.api.routes import control, market, orders, positions, status, stream, trades

logger = logging.getLogger(__name__)


def create_app(container: AppContainer) -> FastAPI:
    """FastAPI 앱을 생성하고 라우터와 컨테이너를 등록한다.

    Args:
        container: 앱이 공유할 컴포넌트 컨테이너.

    Returns:
        설정이 완료된 FastAPI 인스턴스.
    """

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        logger.info("Control API 시작")
        yield
        logger.info("Control API 종료")

    app = FastAPI(
        title="quanteo Control API",
        version="0.1.0",
        description="quanteo 자동매매 봇 제어 및 모니터링 API",
        lifespan=_lifespan,
    )
    app.state.container = container

    app.include_router(status.router, tags=["모니터링"])
    app.include_router(positions.router, tags=["모니터링"])
    app.include_router(orders.router, tags=["모니터링"])
    app.include_router(trades.router, tags=["모니터링"])
    app.include_router(market.router, tags=["마켓"])
    app.include_router(control.router, prefix="/control", tags=["제어"])
    app.include_router(stream.router, tags=["스트림"])

    return app
