"""
quanteo 애플리케이션 진입점.

모든 모듈을 조립하고 asyncio 이벤트 루프를 통해 동시 실행한다.

부팅 순서:
  1. Settings 로딩
  2. StateStore 초기화 (SQLite)
  3. EventBus 시작
  4. RiskManager 초기화
  5. Notifier 초기화 + Event Bus 연결
  6. (선택) Toss 트레이딩 모듈 시작
  7. Control API (FastAPI/uvicorn) 시작
  8. 종료 시그널 대기 → 정상 종료
"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

from core.api.app import create_app
from core.api.deps import AppContainer
from core.config.settings import Market, load_settings
from core.events.bus import EventBus
from core.execution.position_sync import PositionSyncFeed
from core.notifier.factory import make_notifier
from core.notifier.wiring import wire_notifier
from core.risk.manager import RiskConfig, RiskManager
from core.store.db import StateStore

if TYPE_CHECKING:
    from core.adapters.toss.rest import TossRestClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 트레이딩 게이트 (실전 자금 이중 확인)
# ---------------------------------------------------------------------------


class TradingGateError(RuntimeError):
    """트레이딩 시작 전 이중 확인 게이트 실패."""


def _check_trading_gate(with_trading: bool, confirmed: bool) -> None:
    """트레이딩 시작 전 이중 확인 게이트.

    Toss증권은 항상 실제 자금을 사용한다.
    --with-trading 플래그를 사용할 때는 --i-understand-real-money 도 함께 전달해야 한다.

    Args:
        with_trading: 트레이딩 모듈(MarketData/Strategy/Executor) 시작 여부.
        confirmed: CLI에서 --i-understand-real-money 플래그가 전달되었는지 여부.

    Raises:
        TradingGateError: with_trading=True인데 confirmed=False일 때.
    """
    if with_trading and not confirmed:
        raise TradingGateError(
            "\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⛔  트레이딩 시작 차단\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Toss증권은 항상 실제 자금을 사용합니다.\n"
            "트레이딩을 시작하려면 아래 플래그를 추가하세요:\n\n"
            "  uv run quanteo --with-trading --i-understand-real-money\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


# ---------------------------------------------------------------------------
# 메인 부팅 함수
# ---------------------------------------------------------------------------


async def run(
    market: Market = Market.DOMESTIC,
    config_path: Path | None = None,
    api_host: str = "127.0.0.1",
    api_port: int = 8000,
    with_trading: bool = False,
    confirmed: bool = False,
    with_info: bool = False,
) -> None:
    """quanteo 코어 전체를 시작한다.

    Args:
        market: 대상 시장. 기본값 DOMESTIC.
        config_path: quanteo.yaml 경로.
        api_host: Control API 바인드 호스트.
        api_port: Control API 바인드 포트.
        with_trading: True이면 MarketData / Strategy / Executor 도 시작.
                      False이면 Control API + Notifier만 구동 (개발/검수용).
        confirmed: CLI --i-understand-real-money 플래그.
                   with_trading=True 시 반드시 함께 지정.
        with_info: True이면 정보 수집·알람 서브시스템(InfoSystem)도 함께 시작.
                   settings.info.enabled=True 여야 실제로 동작.

    Raises:
        TradingGateError: with_trading=True인데 confirmed=False일 때.
    """
    _check_trading_gate(with_trading, confirmed)
    settings = load_settings(market=market, config_path=config_path)
    logger.info("quanteo 시작 (market=%s)", settings.market)

    store = StateStore()
    await store.open()

    await _log_persisted_state(store)

    bus = EventBus()
    risk = RiskManager(config=RiskConfig(), bus=bus)
    notifier = make_notifier(settings)

    wire_notifier(bus, notifier)

    # Toss 브로커 초기화 — 읽기 전용 조회(잔고·체결)는 --with-trading과 무관하게
    # 항상 필요하므로, 트레이딩 모듈 시작 여부와 별개로 미리 구성한다.
    rest_client = await _init_broker(settings, with_trading)

    # InfoSystem 조립 (enabled 확인)
    info_system = None
    if with_info and settings.info.enabled:
        try:
            from info.main import InfoSystem
            info_system = InfoSystem(settings)
            logger.info("InfoSystem 초기화 완료")
        except Exception as exc:
            logger.error("InfoSystem 초기화 실패 — info 비활성화: %s", exc)

    container = AppContainer(
        store=store,
        risk=risk,
        bus=bus,
        env="prod",
        market=settings.market.value,
        broker=rest_client,
    )
    fastapi_app = create_app(container)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _on_signal() -> None:
        logger.info("종료 시그널 수신")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    uvicorn_config = uvicorn.Config(
        app=fastapi_app,
        host=api_host,
        port=api_port,
        log_level="info",
        loop="none",
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)
    uvicorn_server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

    async def _serve_api() -> None:
        logger.info("Control API 시작: http://%s:%d", api_host, api_port)
        await uvicorn_server.serve()

    async def _wait_stop() -> None:
        await stop_event.wait()
        logger.info("정상 종료 시작...")
        uvicorn_server.should_exit = True
        await _shutdown(bus, notifier, store, info_system=info_system)

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(bus.start(), name="event-bus")
            tg.create_task(notifier.run(), name="notifier")
            tg.create_task(_serve_api(), name="control-api")

            if with_trading:
                _start_trading_tasks(tg, rest_client, bus, risk, store)

            if rest_client is not None:
                position_sync = PositionSyncFeed(
                    rest_client=rest_client, store=store, env=container.env, bus=bus
                )
                tg.create_task(position_sync.run(), name="position-sync")

            if info_system is not None:
                tg.create_task(info_system.start(), name="info-system")

            tg.create_task(_wait_stop(), name="shutdown-watcher")

    except* asyncio.CancelledError:
        logger.info("태스크 취소 완료")
    except* Exception as eg:
        for exc in eg.exceptions:
            logger.error("태스크 오류: %s", exc, exc_info=True)
    finally:
        await store.close()
        logger.info("quanteo 종료 완료")


# ---------------------------------------------------------------------------
# 재시작 복구
# ---------------------------------------------------------------------------


async def _log_persisted_state(store: StateStore) -> None:
    """재시작 시 State Store에서 직전 포지션·미체결 주문을 조회해 로깅한다."""
    try:
        positions = await store.get_open_positions()
        orders = await store.get_pending_orders()

        if positions:
            logger.info("♻️  재시작 복구 — 오픈 포지션 %d개:", len(positions))
            for pos in positions:
                logger.info(
                    "  · %s %s | qty=%s avg_price=%.2f",
                    pos.market,
                    pos.symbol,
                    pos.qty,
                    pos.avg_price,
                )
        else:
            logger.info("♻️  재시작 복구 — 오픈 포지션 없음")

        if orders:
            logger.warning("♻️  재시작 복구 — 미체결 주문 %d개 (수동 확인 필요):", len(orders))
            for ord_ in orders:
                logger.warning(
                    "  · %s %s | qty=%d status=%s client_order_id=%s",
                    ord_.side,
                    ord_.symbol,
                    ord_.qty,
                    ord_.status,
                    ord_.client_order_id,
                )
        else:
            logger.info("♻️  재시작 복구 — 미체결 주문 없음")

    except Exception as exc:
        logger.error(
            "재시작 복구 중 오류 — DB를 확인하세요: %s",
            exc,
            exc_info=True,
        )
        logger.warning("⚠️  DB 복구 실패로 인해 빈 상태에서 시작합니다.")


# ---------------------------------------------------------------------------
# Toss 브로커 초기화 (읽기 전용 조회는 --with-trading과 무관하게 필요)
# ---------------------------------------------------------------------------


async def _init_broker(settings: object, with_trading: bool) -> TossRestClient | None:
    """Toss REST 클라이언트를 초기화한다.

    포지션/체결 조회 같은 읽기 전용 API는 실전 주문 게이트(--with-trading)와
    무관하게 항상 쓸 수 있어야 하므로, 트레이딩 시작 여부와 별개로 여기서
    미리 초기화한다.

    with_trading=True인데 초기화가 실패하면 실전 주문을 낼 수 없으므로 예외를
    던져 부팅을 중단한다. with_trading=False인 경우엔 자격증명 미비/네트워크
    오류가 있어도 포지션 동기화·체결 조회 없이 Control API는 계속 띄운다
    (개발/검수 편의).
    """
    from core.adapters.toss.auth import TossAuth
    from core.adapters.toss.rest import TossRestClient

    creds = getattr(settings, "credentials", None)
    if creds is None:
        msg = "quanteo.yaml에 Toss 자격증명이 없습니다."
        if with_trading:
            raise RuntimeError(f"트레이딩 모듈 초기화 실패 — 실전 주문 불가: {msg}")
        logger.warning("%s 포지션 동기화·체결 조회 없이 시작합니다.", msg)
        return None

    try:
        rest_client = TossRestClient(TossAuth(creds))
        await rest_client.initialize()
        return rest_client
    except Exception as exc:
        if with_trading:
            logger.error("Toss 브로커 초기화 실패: %s", exc, exc_info=True)
            raise RuntimeError(f"트레이딩 모듈 초기화 실패 — 실전 주문 불가: {exc}") from exc
        logger.warning("Toss 브로커 초기화 실패 — 포지션 동기화·체결 조회 없이 시작합니다: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 트레이딩 태스크
# ---------------------------------------------------------------------------


def _start_trading_tasks(
    tg: asyncio.TaskGroup,
    rest_client: object,
    bus: EventBus,
    risk: RiskManager,
    store: StateStore,
) -> None:
    """MarketData/Strategy/Executor를 조립한다.

    rest_client는 run()에서 _init_broker()로 이미 initialize()까지 끝낸
    인스턴스를 그대로 재사용한다 (읽기 전용 포지션 동기화와 별도 인스턴스를
    만들지 않기 위함).
    """
    try:
        from core.execution.executor import OrderExecutor
        from core.marketdata.feed import MarketDataFeed
        from core.strategy.engine import StrategyEngine

        async def _run_trading() -> None:
            feed = MarketDataFeed(rest_client=rest_client, poll_interval=2.0)
            engine = StrategyEngine(bus=bus)
            OrderExecutor(rest_client=rest_client, store=store, bus=bus)

            logger.info("Toss 트레이딩 모듈 시작 완료 (REST 폴링 모드)")
            async with asyncio.TaskGroup() as inner_tg:
                inner_tg.create_task(feed.run(), name="toss-market-data-feed")
                inner_tg.create_task(engine.run(), name="strategy-engine")

        tg.create_task(_run_trading(), name="toss-trading")

    except Exception as exc:
        logger.error("Toss 트레이딩 모듈 시작 실패: %s", exc, exc_info=True)
        raise RuntimeError(f"트레이딩 모듈 초기화 실패 — 실전 주문 불가: {exc}") from exc


# ---------------------------------------------------------------------------
# 정상 종료
# ---------------------------------------------------------------------------


async def _shutdown(
    bus: EventBus,
    notifier: object,
    store: StateStore,
    info_system: object | None = None,
) -> None:
    """Event Bus → Notifier → InfoSystem → StateStore 순으로 정상 종료한다."""
    for name, obj in [("EventBus", bus), ("Notifier", notifier)]:
        try:
            await obj.stop()  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("%s 종료 오류: %s", name, exc)

    if info_system is not None:
        try:
            await info_system.stop()  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("InfoSystem 종료 오류: %s", exc)


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI 진입점."""
    import argparse

    parser = argparse.ArgumentParser(description="quanteo 자동매매 봇 (Toss증권)")
    parser.add_argument("--market", choices=["domestic", "overseas"], default="domestic")
    parser.add_argument("--host", default="127.0.0.1", help="Control API 호스트")
    parser.add_argument("--port", type=int, default=8000, help="Control API 포트")
    parser.add_argument("--with-trading", action="store_true", help="MarketData/Strategy/Executor 포함")
    parser.add_argument("--with-info", action="store_true", dest="with_info", help="정보 수집·알람 서브시스템 포함 (settings.info.enabled 필요)")
    parser.add_argument(
        "--i-understand-real-money",
        action="store_true",
        dest="confirmed",
        help="실제 자금 사용 확인 플래그. --with-trading 시 반드시 함께 지정.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        asyncio.run(
            run(
                market=Market(args.market),
                api_host=args.host,
                api_port=args.port,
                with_trading=args.with_trading,
                confirmed=args.confirmed,
                with_info=args.with_info,
            )
        )
    except TradingGateError as exc:
        logger.critical(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
