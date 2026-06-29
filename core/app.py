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

import uvicorn

from core.api.app import create_app
from core.api.deps import AppContainer
from core.config.settings import Market, load_settings
from core.events.bus import EventBus
from core.notifier.factory import make_notifier
from core.notifier.wiring import wire_notifier
from core.risk.manager import RiskConfig, RiskManager
from core.store.db import StateStore

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

    container = AppContainer(
        store=store,
        risk=risk,
        bus=bus,
        env="prod",
        market=settings.market.value,
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
        await _shutdown(bus, notifier, store)

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(bus.start(), name="event-bus")
            tg.create_task(notifier.run(), name="notifier")
            tg.create_task(_serve_api(), name="control-api")

            if with_trading:
                _start_trading_tasks(tg, settings, bus, risk, store)

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
                    "  · %s %s | qty=%d avg_price=%.2f",
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
# 트레이딩 태스크
# ---------------------------------------------------------------------------


def _start_trading_tasks(
    tg: asyncio.TaskGroup,
    settings: object,
    bus: EventBus,
    risk: RiskManager,
    store: StateStore,
) -> None:
    """Toss 어댑터 조립 (REST 폴링 피드)."""
    try:
        from core.adapters.toss.auth import TossAuth
        from core.adapters.toss.rest import TossRestClient
        from core.execution.executor import OrderExecutor
        from core.marketdata.feed import MarketDataFeed
        from core.strategy.engine import StrategyEngine

        creds = getattr(settings, "credentials", None)
        if creds is None:
            raise ValueError("quanteo.yaml에 toss 자격증명이 없습니다.")

        auth = TossAuth(creds)
        rest_client = TossRestClient(auth)

        async def _init_and_run() -> None:
            await rest_client.initialize()
            feed = MarketDataFeed(rest_client=rest_client, poll_interval=2.0)
            engine = StrategyEngine(bus=bus)
            OrderExecutor(rest_client=rest_client, store=store, bus=bus)

            logger.info("Toss 트레이딩 모듈 시작 완료 (REST 폴링 모드)")
            async with asyncio.TaskGroup() as inner_tg:
                inner_tg.create_task(feed.run(), name="toss-market-data-feed")
                inner_tg.create_task(engine.run(), name="strategy-engine")

        tg.create_task(_init_and_run(), name="toss-trading")

    except Exception as exc:
        logger.error("Toss 트레이딩 모듈 시작 실패: %s", exc, exc_info=True)
        raise RuntimeError(f"트레이딩 모듈 초기화 실패 — 실전 주문 불가: {exc}") from exc


# ---------------------------------------------------------------------------
# 정상 종료
# ---------------------------------------------------------------------------


async def _shutdown(bus: EventBus, notifier: object, store: StateStore) -> None:
    """Event Bus → Notifier → StateStore 순으로 정상 종료한다."""
    for name, obj in [("EventBus", bus), ("Notifier", notifier)]:
        try:
            await obj.stop()  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("%s 종료 오류: %s", name, exc)


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
            )
        )
    except TradingGateError as exc:
        logger.critical(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
