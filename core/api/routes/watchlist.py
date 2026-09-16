"""GET /watchlist — Stock Miner(screener)가 선정한 관심종목 리스트 조회.

core.app(매매 코어)과 screener는 런타임이 완전히 분리돼 있다(CLAUDE.md) —
여기서는 screener가 파일로 남긴 결과물(JSON)만 읽는다. screener 모듈을
import하거나 실행하지 않는다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.api.models import WatchlistItem, WatchlistResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# screener/scripts/build_watchlist.py의 _DEFAULT_OUTPUT_DIR과 동일한 경로.
# 두 프로세스 모두 저장소 루트에서 실행된다는 전제(README 실행 커맨드 기준).
_WATCHLIST_DIR = Path("screener/data/watchlist")
_FILENAME_PREFIX = "watchlist_"
_FILENAME_SUFFIX = ".json"


def _latest_watchlist_file() -> Path | None:
    """가장 최근 날짜의 watchlist_YYYY-MM-DD.json 파일을 찾는다.

    파일명이 YYYY-MM-DD 형식이라 문자열 정렬이 곧 날짜순 정렬이다 — mtime은
    파일이 재복사/재생성될 때 날짜와 어긋날 수 있어 신뢰하지 않는다.
    """
    if not _WATCHLIST_DIR.is_dir():
        return None
    files = sorted(_WATCHLIST_DIR.glob(f"{_FILENAME_PREFIX}*{_FILENAME_SUFFIX}"))
    return files[-1] if files else None


@router.get("/watchlist", response_model=WatchlistResponse, summary="관심종목 리스트 조회")
async def get_watchlist() -> WatchlistResponse:
    """Stock Miner(screener)가 선정한 가장 최근 관심종목 리스트를 조회한다.

    Raises:
        HTTPException(404): 아직 생성된 관심종목 파일이 없을 때.
        HTTPException(502): 파일이 있으나 읽기·파싱에 실패했을 때(손상된 결과물).
    """
    latest_file = _latest_watchlist_file()
    if latest_file is None:
        raise HTTPException(status_code=404, detail="아직 생성된 관심종목이 없습니다.")

    try:
        raw = json.loads(latest_file.read_text(encoding="utf-8"))
        items = [WatchlistItem(**row) for row in raw]
    except Exception as exc:
        logger.exception("관심종목 파일 파싱 실패: %s", latest_file)
        raise HTTPException(
            status_code=502, detail="관심종목 데이터를 읽는 데 실패했습니다."
        ) from exc

    # watchlist_YYYY-MM-DD.json → YYYY-MM-DD
    date = latest_file.stem.removeprefix(_FILENAME_PREFIX)

    return WatchlistResponse(date=date, items=items)
