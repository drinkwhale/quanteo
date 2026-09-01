"""관심종목 다단계 필터링 실행 스크립트.

Usage:
    uv run python -m screener.scripts.build_watchlist --date 2026-08-28
    → 지정된 날짜 기준 관심종목 리스트 생성 (CSV/JSON)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from argparse import ArgumentParser
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from core.config.settings import load_settings, Settings
from screener.data.collectors.dart_client import DartClient
from screener.data.collectors.pykrx_client import PykrxClient
from screener.pipeline.watchlist_filter import (
    apply_watchlist_filters,
    calculate_yoy_growth,
)

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = Path("screener/data/watchlist")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def build_watchlist(
    date: str | None = None,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
    settings: Settings | None = None,
) -> list[dict]:
    """관심종목 리스트 생성.

    Args:
        date: 기준일 (YYYY-MM-DD). None이면 어제. 휴장일이면 직전 영업일 자동 폴백.
        output_dir: 결과 저장 디렉토리 (자동 생성)
        settings: 설정 (None이면 기본 설정 로드)

    Returns:
        WatchlistCandidate 객체 리스트 (dict 변환)

    Raises:
        ValueError: 유니버스 또는 재무 데이터 수집 실패
    """
    if date is None:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    if settings is None:
        settings = load_settings()

    logger.info(f"관심종목 필터링 시작 — 기준일: {date}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 시장 데이터 수집 (시총, 시세)
    logger.info("Step 1: 코스피/코스닥 시장 데이터 수집 중...")
    pykrx = PykrxClient()
    universe_df = await pykrx.fetch_universe(date)
    if universe_df.empty:
        msg = f"유니버스 데이터 없음 (날짜: {date})"
        logger.error(msg)
        raise ValueError(msg)

    logger.info(f"총 {len(universe_df)}개 종목 수집")

    # 2. 재무 데이터 수집 (3년간 자산/영업이익/매출)
    logger.info("Step 2: DART 재무제표 수집 중...")
    dart = DartClient(api_key=settings.screener.dart_api_key)

    financials_list = []
    failed_count = 0
    for ticker in universe_df["ticker"]:
        try:
            stmt = await dart.fetch_financials(ticker, years=3)
            if not stmt.years:
                logger.debug(f"{ticker}: 재무제표 없음")
                continue

            # 가장 최근 2개년 조회
            if len(stmt.years) >= 2:
                current_year = stmt.years[-1]
                prior_year = stmt.years[-2]
            else:
                logger.debug(f"{ticker}: 2개년 데이터 부족")
                continue

            financials_list.append({
                "ticker": ticker,
                "asset_current_year": current_year.total_equity,
                "asset_prior_year": prior_year.total_equity,
                "operating_income_current_year": current_year.operating_income,
                "operating_income_prior_year": prior_year.operating_income,
                "revenue_current_year": current_year.revenue,
                "revenue_prior_year": prior_year.revenue,
            })
        except AttributeError as e:
            logger.error(f"{ticker}: 타입 오류 (async 함수 await 누락?) — {e}", exc_info=True)
            failed_count += 1
        except (TimeoutError, ConnectionError) as e:
            logger.error(f"{ticker}: 네트워크 오류 — {e}", exc_info=True)
            failed_count += 1
            if failed_count > 5:
                logger.error("연속된 네트워크 오류 발생 — 수집 중단")
                raise
        except Exception as e:
            logger.debug(f"{ticker}: 재무 수집 실패 — {e}")
            continue

    if not financials_list:
        msg = f"재무 데이터 수집 실패 (수집 시도: {len(universe_df)}, 성공: 0)"
        logger.error(msg)
        raise ValueError(msg)

    financials_df = pd.DataFrame(financials_list).set_index("ticker")
    logger.info(f"재무 데이터 수집: {len(financials_df)}개 종목 (성공률 {len(financials_df)/len(universe_df)*100:.1f}%)")

    # 3. 증가율 계산
    logger.info("Step 3: 연간 증가율 계산 중...")
    financials_df["asset_growth"] = calculate_yoy_growth(
        financials_df.reset_index(), "asset"
    ).set_index(
        financials_df.index
    )
    financials_df["operating_income_growth"] = calculate_yoy_growth(
        financials_df.reset_index(), "operating_income"
    ).set_index(
        financials_df.index
    )
    financials_df["revenue_growth"] = calculate_yoy_growth(
        financials_df.reset_index(), "revenue"
    ).set_index(
        financials_df.index
    )

    # 4. 필터링 적용
    logger.info("Step 4: 다단계 필터링 적용 중...")
    candidates = apply_watchlist_filters(
        universe_df.set_index("ticker"),
        financials_df,
    )

    logger.info(f"최종 관심종목: {len(candidates)}개")

    # 5. 결과 저장
    results = [
        {
            "ticker": c.ticker,
            "name": c.name,
            "market_cap_billion": c.market_cap / 1e9,
            "asset_growth_pct": round(c.asset_growth, 2),
            "oi_growth_pct": round(c.operating_income_growth, 2),
            "revenue_growth_pct": round(c.revenue_growth, 2),
        }
        for c in candidates
    ]

    csv_path = output_dir / f"watchlist_{date}.csv"
    json_path = output_dir / f"watchlist_{date}.json"

    # CSV 저장
    if results:
        results_df = pd.DataFrame(results)
        results_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.info(f"CSV 저장: {csv_path}")

        # JSON 저장
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"JSON 저장: {json_path}")
    else:
        logger.warning("필터링 결과 없음")

    return results


def main():
    parser = ArgumentParser(description="관심종목 다단계 필터링 스크립트")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="기준일 (YYYY-MM-DD). 기본값: 어제",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"결과 저장 디렉토리. 기본값: {_DEFAULT_OUTPUT_DIR}",
    )

    args = parser.parse_args()

    setup_logging()

    try:
        results = asyncio.run(
            build_watchlist(date=args.date, output_dir=args.output_dir)
        )
    except (ValueError, Exception) as e:
        logger.error(f"관심종목 생성 실패: {e}", exc_info=True)
        print(f"❌ 관심종목 생성 실패: {e}")
        sys.exit(1)

    if results:
        print(f"\n✅ 관심종목 {len(results)}개 생성 완료")
        print("\n상위 10개:")
        for i, r in enumerate(results[:10], 1):
            print(
                f"{i}. {r['ticker']} {r['name']:20} | "
                f"시총 {r['market_cap_billion']:.1f}B | "
                f"자산↑{r['asset_growth_pct']:.1f}% "
                f"영업↑{r['oi_growth_pct']:.1f}% "
                f"매출↑{r['revenue_growth_pct']:.1f}%"
            )
        sys.exit(0)
    else:
        logger.error("관심종목 생성 실패 — 결과 없음")
        print("❌ 관심종목 생성 실패")
        sys.exit(1)


if __name__ == "__main__":
    main()
