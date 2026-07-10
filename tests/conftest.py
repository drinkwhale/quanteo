import sqlite3
from pathlib import Path

import pytest

# core.store.db.StateStore의 기본 경로와 반드시 동일해야 한다 — 이 값이
# 갈라지면 안전장치가 조용히 무력화된다.
_PRODUCTION_DB_PATH = Path.home() / "quanteo" / "data" / "quanteo.db"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _orders_row_count() -> int | None:
    """프로덕션 DB의 orders 행 수를 읽는다.

    파일이 없거나(신규 클론) 마침 봇 프로세스가 쓰기 잠금 중이면 None을
    반환해 관대하게 넘어간다 — 안전장치 자체의 오탐이 무관한 테스트를
    깨뜨리면 안 되기 때문. orders 테이블만 보는 이유는 살아있는 봇
    프로세스도 positions/candles 등 다른 테이블은 정상적으로 계속 쓰므로,
    그 정상 활동과 "테스트가 만든 가짜 주문"을 구분하려면 orders 테이블
    행 수만 비교해야 한다.
    """
    if not _PRODUCTION_DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{_PRODUCTION_DB_PATH}?mode=ro", uri=True, timeout=1)
        try:
            return conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return None


@pytest.fixture(autouse=True)
def _guard_production_orders_table(request):
    """테스트가 실수로 프로덕션 DB에 주문을 남기면 즉시 실패시킨다.

    배경: tests/integration/test_toss_roundtrip.py가 StateStore()를 인자
    없이 생성해(기본 경로 = 프로덕션 DB) MockTossRestClient가 만든 가짜
    'submitted' 주문을 실행할 때마다 프로덕션 orders 테이블에 실제로
    삽입한 사고가 있었다. 그 테스트는 StateStore(":memory:")로 고쳤지만,
    같은 실수가 다른 테스트에서 재발해도 조용히 넘어가지 않도록 세션
    전체에 이 안전망을 둔다.
    """
    before = _orders_row_count()
    yield
    after = _orders_row_count()
    if before is not None and after is not None:
        assert before == after, (
            f"{request.node.nodeid} 테스트가 프로덕션 DB({_PRODUCTION_DB_PATH})의 "
            f"orders 테이블을 변경했습니다({before} → {after}행). "
            'StateStore(":memory:") 또는 tmp_path 기반 경로를 사용하세요.'
        )
