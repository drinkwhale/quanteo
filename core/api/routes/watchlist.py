"""GET /watchlist — 사용자가 Telegram에서 승인한 관심종목 조회.

Stock Miner(screener)가 매일 후보를 Telegram 리포트로 보내면, 사용자가
인라인 버튼("워치리스트 등록")을 눌러야만 StateStore의 watchlist 테이블에
기록된다(screener/notify/callback_handler.py). core.app(이 Control API가
속한 프로세스)과 screener는 런타임이 분리된 별도 Docker 컨테이너이지만,
둘 다 같은 SQLite 파일(~/quanteo/data/quanteo.db)을 공유하도록 배포되어
있어(docker-compose.yml) StateStore를 통해서만 두 프로세스 간에 안전하게
공유된다. screener가 파일로 남기는 산출물(screener/data/watchlist/*.json)은
컨테이너 로컬 파일이라 공유되지 않으므로 여기서 읽지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter

from core.api.deps import ContainerDep
from core.api.models import WatchlistItem, WatchlistResponse

router = APIRouter()


@router.get("/watchlist", response_model=WatchlistResponse, summary="관심종목 조회")
async def get_watchlist(container: ContainerDep) -> WatchlistResponse:
    """사용자가 승인한 관심종목 전체를 등록일 순으로 반환한다.

    아직 등록된 종목이 없으면 빈 목록을 반환한다(404가 아니다) — watchlist
    테이블 자체는 항상 존재하고, "비어 있음"은 정상 상태이기 때문이다.
    """
    entries = await container.store.get_watchlist()
    items = [
        WatchlistItem(
            symbol=e.symbol,
            name=e.name,
            added_at=e.added_at,
            source=e.source,
            score_snapshot=e.score_snapshot,
        )
        for e in entries
    ]
    return WatchlistResponse(items=items)
