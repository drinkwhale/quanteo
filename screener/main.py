"""Stock Miner 독립 실행 엔트리포인트.

core/app.py(매매 코어)·info/main.py(정보 수집)와는 별도 프로세스로 기동한다.

사용법:
    uv run python -m screener.main
"""

from __future__ import annotations

import asyncio
import logging

import yaml

from core.config.settings import load_settings
from core.notifier.telegram import TelegramNotifier
from screener.agents.analyst_agent import AnalystAgent
from screener.data.collectors.dart_client import DartClient
from screener.data.collectors.pykrx_client import PykrxClient
from screener.notify.telegram_reporter import ScreenerNotifier
from screener.pipeline.screener import ScreenerConfig
from screener.scheduler.daily_job import DailyJob, DailyJobScheduler

logger = logging.getLogger(__name__)


def _load_pipeline_settings(config_path: str) -> tuple[dict[str, float], int]:
    """settings.yaml의 scoring_weights·report.top_n을 읽는다."""
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    weights = raw.get("scoring_weights") or None
    report_top_n = int((raw.get("report") or {}).get("top_n", 10))
    return weights, report_top_n


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = load_settings()
    if not settings.screener.enabled:
        logger.warning("screener.enabled=false — Stock Miner를 시작하지 않고 종료합니다.")
        return

    screener_config = ScreenerConfig.from_yaml(settings.screener.config_path)
    scoring_weights, report_top_n = _load_pipeline_settings(settings.screener.config_path)

    telegram = TelegramNotifier(
        bot_token=settings.telegram.bot_token.get_secret_value(),
        chat_id=settings.screener.telegram_chat_id or settings.telegram.chat_id,
    )
    notifier = ScreenerNotifier(telegram_notifier=telegram)

    job = DailyJob(
        pykrx_client=PykrxClient(),
        dart_client=DartClient(api_key=settings.screener.dart_api_key),
        analyst_agent=AnalystAgent(api_key=settings.screener.anthropic_api_key),
        notifier=notifier,
        screener_config=screener_config,
        scoring_weights=scoring_weights,
        report_top_n=report_top_n,
    )
    scheduler = DailyJobScheduler(job)
    scheduler.start()

    logger.info("Stock Miner 스케줄러 시작 (평일 15:40 KST)")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.stop()
        await telegram.close()


if __name__ == "__main__":
    asyncio.run(main())
