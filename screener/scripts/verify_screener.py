"""Phase 1 로컬 검증 스크립트 — 유니버스 필터 결과를 LLM/텔레그램 없이 확인한다.

사용법:
    uv run python -m screener.scripts.verify_screener --date 2026-07-21
    uv run python -m screener.scripts.verify_screener --date 2026-07-21 --csv out.csv
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import pandas as pd

from screener.data.collectors.pykrx_client import PykrxClient
from screener.pipeline.screener import (
    ScreenerConfig,
    compute_avg_trading_value_20d,
    filter_universe,
)

logger = logging.getLogger(__name__)


async def run(date: str, csv_path: str | None, config_path: str) -> pd.DataFrame:
    """유니버스 조회 → 필터 적용까지 실행하고 결과 DataFrame을 반환한다."""
    client = PykrxClient()
    config = ScreenerConfig.from_yaml(config_path)

    logger.info("유니버스 조회 중 (date=%s)...", date)
    universe = await client.fetch_universe(date)
    if universe.empty:
        print(f"[verify_screener] {date} 유니버스가 비어 있습니다 (휴장일이거나 API 오류).")
        return universe

    logger.info("20일 평균 거래대금 계산 중 (조회량이 많아 시간이 걸릴 수 있음)...")
    avg_trading_value = await compute_avg_trading_value_20d(client, date)

    result = filter_universe(universe, config, avg_trading_value_20d=avg_trading_value)

    print(f"\n=== 유니버스 필터 결과: {len(universe)}개 → {len(result)}개 ===\n")
    display_cols = [
        c
        for c in ("ticker", "name", "market", "close", "market_cap", "avg_trading_value_20d")
        if c in result.columns
    ]
    print(result[display_cols].sort_values("market_cap", ascending=False).to_string(index=False))

    if csv_path:
        result.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\nCSV 저장 완료: {csv_path}")

    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Stock Miner Phase 1 로컬 검증")
    parser.add_argument("--date", required=True, help="조회 일자 (YYYY-MM-DD 또는 YYYYMMDD)")
    parser.add_argument("--csv", default=None, help="결과를 CSV로도 저장할 경로")
    parser.add_argument(
        "--config", default="screener/config/settings.yaml", help="settings.yaml 경로"
    )
    args = parser.parse_args()

    date = args.date.replace("-", "")
    if len(date) != 8 or not date.isdigit():
        print(f"날짜 형식이 올바르지 않습니다: {args.date!r} (예: 2026-07-21)", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run(date, args.csv, args.config))


if __name__ == "__main__":
    main()
