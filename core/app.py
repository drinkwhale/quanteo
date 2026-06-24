"""
quanteo 애플리케이션 진입점.

모든 모듈을 조립하고 asyncio 이벤트 루프를 통해 동시 실행한다.

부팅 순서:
  1. Settings 로딩
  2. StateStore 초기화 (SQLite)
  3. EventBus 시작
  4. RiskManager 초기화
  5. Notifier 초기화 + Event Bus 연결
  6. MarketDataFeed 초기화 (선택적 — KIS 자격증명 없을 때 스킵)
  7. StrategyEngine 초기화 (선택적)
  8. OrderExecutor 초기화 (선택적)
  9. Control API (FastAPI/uvicorn) 시작
 10. 종료 시그널 대기 → 정상 종료

asyncio 이벤트 루프 구조 (NautilusTrader 패턴):
  asyncio.TaskGroup으로 각 모듈의 run()을 동시 실행.
  한 모듈이 예외로 종료되면 TaskGroup이 나머지도 취소한다.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

import uvicorn

from core.api.app import create_app
from core.api.deps import AppContainer
from core.config.settings import Env, Market, load_settings
from core.events.bus import EventBus
from core.notifier.factory import make_notifier
from core.notifier.wiring import wire_notifier
from core.risk.manager import RiskConfig, RiskManager
from core.store.db import StateStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 메인 부팅 함수
# ---------------------------------------------------------------------------


class ProdGateError(RuntimeError):
    """실전(prod) 환경 이중 확인 게이트 실패."""


def _check_prod_gate(env: Env, prod_confirmed: bool) -> None:
    """실전 환경 진입 전 이중 확인 게이트.

    prod 환경은 명시적으로 prod_confirmed=True 를 전달해야만 진입된다.
    누락 시 즉시 예외를 발생시켜 실수로 실전 주문이 나가는 것을 방지한다.

    Args:
        env: 투자 환경.
        prod_confirmed: CLI에서 --i-understand-real-money 플래그가 전달되었는지 여부.

    Raises:
        ProdGateError: prod 환경이지만 확인 플래그가 없을 때.
    """
    if env == Env.PROD and not prod_confirmed:
        raise ProdGateError(
            "\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⛔  실전(prod) 환경 진입 차단\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "--env prod 는 실제 돈을 사용합니다.\n"
            "의도적으로 실전 환경을 시작하려면 아래 플래그를 추가하세요:\n\n"
            "  uv run quanteo --env prod --i-understand-real-money\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


async def run(
    env: Env = Env.VPS,
    market: Market = Market.DOMESTIC,
    config_path: Path | None = None,
    api_host: str = "127.0.0.1",
    api_port: int = 8000,
    with_trading: bool = False,
    prod_confirmed: bool = False,
) -> None:
    """quanteo 코어 전체를 시작한다.

    Args:
        env: 투자 환경. 기본값 VPS(모의투자).
        market: 대상 시장. 기본값 DOMESTIC.
        config_path: kis_devlp.yaml 경로.
        api_host: Control API 바인드 호스트.
        api_port: Control API 바인드 포트.
        with_trading: True이면 MarketData / Strategy / Executor 도 시작.
                      False이면 Control API + Notifier만 구동 (개발/검수용).
        prod_confirmed: CLI --i-understand-real-money 플래그. prod 환경 진입 이중 확인용.

    Raises:
        ProdGateError: prod 환경인데 prod_confirmed=False 일 때.
    """
    _check_prod_gate(env, prod_confirmed)
    settings = load_settings(env=env, market=market, config_path=config_path)
    logger.info("quanteo 시작 (env=%s market=%s)", settings.env, settings.market)

    # -----------------------------------------------------------------------
    # 핵심 컴포넌트 초기화
    # -----------------------------------------------------------------------
    store = StateStore()
    await store.open()

    # 재시작 복구: 직전 상태(포지션·미체결 주문) 로드 및 로깅
    await _log_persisted_state(store, env.value)

    bus = EventBus()
    risk = RiskManager(config=RiskConfig(), bus=bus)
    notifier = make_notifier(settings)

    wire_notifier(bus, notifier)

    container = AppContainer(
        store=store,
        risk=risk,
        bus=bus,
        env=settings.env.value,
        market=settings.market.value,
    )
    fastapi_app = create_app(container)

    # -----------------------------------------------------------------------
    # 종료 시그널 처리
    # -----------------------------------------------------------------------
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _on_signal() -> None:
        logger.info("종료 시그널 수신")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    # -----------------------------------------------------------------------
    # uvicorn 서버 (Control API)
    # -----------------------------------------------------------------------
    uvicorn_config = uvicorn.Config(
        app=fastapi_app,
        host=api_host,
        port=api_port,
        log_level="info",
        loop="none",  # 이미 실행 중인 루프 사용
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)
    # uvicorn 내부 시그널 핸들러 비활성화 (우리가 직접 처리)
    uvicorn_server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

    # -----------------------------------------------------------------------
    # 모든 모듈을 TaskGroup으로 동시 실행
    # -----------------------------------------------------------------------
    tasks: list[asyncio.Task] = []

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


async def _log_persisted_state(store: StateStore, env: str) -> None:
    """재시작 시 State Store에서 직전 포지션·미체결 주문을 조회해 로깅한다.

    현재는 로그 출력만 수행한다. 운영자가 재시작 후 상태를 즉시 파악할 수 있게 한다.

    TODO: RiskManager·Executor에 포지션·미체결 주문을 실제로 주입하는
          심화 복구 로직 추가 (현재는 로그만 — 재시작 후 포지션이 0으로 초기화됨).
    """
    try:
        positions = await store.get_open_positions(env=env)
        orders = await store.get_pending_orders(env=env)

        if positions:
            logger.info("♻️  재시작 복구 — 오픈 포지션 %d개:", len(positions))
            for pos in positions:
                logger.info(
                    "  · %s %s | qty=%d avg_price=%.2f (env=%s)",
                    pos.market,
                    pos.symbol,
                    pos.qty,
                    pos.avg_price,
                    pos.env,
                )
        else:
            logger.info("♻️  재시작 복구 — 오픈 포지션 없음")

        if orders:
            logger.warning("♻️  재시작 복구 — 미체결 주문 %d개 (수동 확인 필요):", len(orders))
            for ord_ in orders:
                logger.warning(
                    "  · %s %s %s | qty=%d status=%s client_order_id=%s",
                    ord_.env,
                    ord_.side,
                    ord_.symbol,
                    ord_.qty,
                    ord_.status,
                    ord_.client_order_id,
                )
        else:
            logger.info("♻️  재시작 복구 — 미체결 주문 없음")

    except Exception as exc:
        # DB 오류 시 빈 상태로 부팅되므로 운영자에게 경고를 전달한다.
        # 미체결 주문이 있을 경우 수동 확인이 필요하다.
        logger.error(
            "재시작 복구 중 오류 — DB를 확인하세요. 포지션·주문 정보 없이 계속합니다: %s",
            exc,
            exc_info=True,
        )
        logger.warning(
            "⚠️  DB 복구 실패로 인해 빈 상태에서 시작합니다. "
            "미체결 주문이 있으면 수동으로 확인하세요."
        )


# ---------------------------------------------------------------------------
# 트레이딩 태스크 (with_trading=True 시 추가)
# ---------------------------------------------------------------------------


def _start_trading_tasks(
    tg: asyncio.TaskGroup,
    settings: object,
    bus: EventBus,
    risk: RiskManager,
    store: StateStore,
) -> None:
    """MarketDataFeed / StrategyEngine / OrderExecutor 태스크를 추가한다.

    KIS 자격증명이 없으면 ImportError·RuntimeError를 로깅하고 스킵한다.
    """
    try:
        from core.adapters.kis.auth import KisAuth
        from core.adapters.kis.rest import KisRestClient
        from core.adapters.kis.ws import KisWsClient
        from core.execution.executor import OrderExecutor
        from core.marketdata.feed import MarketDataFeed
        from core.strategy.engine import StrategyEngine

        auth = KisAuth(settings)  # type: ignore[arg-type]
        ws_client = KisWsClient(auth)
        rest_client = KisRestClient(auth)
        feed = MarketDataFeed(ws_client=ws_client, env=settings.env, market=settings.market)  # type: ignore[attr-defined]
        engine = StrategyEngine(bus=bus)
        executor = OrderExecutor(rest_client=rest_client, store=store, bus=bus)

        tg.create_task(feed.run(), name="market-data-feed")
        tg.create_task(engine.run(), name="strategy-engine")

        logger.info("트레이딩 모듈 시작 완료")
    except Exception as exc:
        logger.warning("트레이딩 모듈 시작 실패 (자격증명 없음?): %s", exc)


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

    parser = argparse.ArgumentParser(description="quanteo 자동매매 봇")
    parser.add_argument("--env", choices=["vps", "prod"], default="vps", help="투자 환경 (기본: vps)")
    parser.add_argument("--market", choices=["domestic", "overseas"], default="domestic")
    parser.add_argument("--host", default="127.0.0.1", help="Control API 호스트")
    parser.add_argument("--port", type=int, default=8000, help="Control API 포트")
    parser.add_argument("--with-trading", action="store_true", help="MarketData/Strategy/Executor 포함")
    parser.add_argument(
        "--i-understand-real-money",
        action="store_true",
        dest="prod_confirmed",
        help="실전(prod) 환경 이중 확인 플래그. --env prod 시 반드시 함께 지정.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        asyncio.run(
            run(
                env=Env(args.env),
                market=Market(args.market),
                api_host=args.host,
                api_port=args.port,
                with_trading=args.with_trading,
                prod_confirmed=args.prod_confirmed,
            )
        )
    except ProdGateError as exc:
        print(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
