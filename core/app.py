"""
quanteo 애플리케이션 진입점 (스켈레톤).

현재는 Event Bus + Notifier 조립만 포함한다.
Phase 5 (T024)에서 전체 모듈 부팅으로 확장 예정:
  MarketDataFeed / StrategyEngine / RiskManager / OrderExecutor / ControlAPI
"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from core.config.settings import Env, Market, load_settings
from core.events.bus import EventBus
from core.notifier.factory import make_notifier
from core.notifier.wiring import wire_notifier

logger = logging.getLogger(__name__)


async def run(
    env: Env = Env.VPS,
    market: Market = Market.DOMESTIC,
    config_path: Path | None = None,
) -> None:
    """quanteo 코어를 시작한다.

    Args:
        env: 투자 환경. 기본값 VPS(모의투자).
        market: 대상 시장. 기본값 DOMESTIC.
        config_path: kis_devlp.yaml 경로. 기본값은 ~/KIS/config/kis_devlp.yaml.
    """
    settings = load_settings(env=env, market=market, config_path=config_path)
    logger.info("quanteo 시작 (env=%s market=%s)", settings.env, settings.market)

    bus = EventBus()
    notifier = make_notifier(settings)

    wire_notifier(bus, notifier)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _on_signal() -> None:
        logger.info("종료 시그널 수신")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(bus.start(), name="event-bus-start")
        tg.create_task(notifier.run(), name="notifier")
        tg.create_task(_wait_for_stop(stop_event, bus, notifier), name="shutdown-watcher")


async def _wait_for_stop(
    stop_event: asyncio.Event,
    bus: EventBus,
    notifier: object,
) -> None:
    """종료 이벤트를 기다렸다가 버스와 Notifier를 정상 종료한다."""
    await stop_event.wait()
    logger.info("종료 중...")
    await bus.stop()
    if hasattr(notifier, "stop"):
        await notifier.stop()  # type: ignore[union-attr]


def main() -> None:
    """CLI 진입점."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
