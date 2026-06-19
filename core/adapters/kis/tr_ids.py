"""
KIS API TR_ID 및 도메인 매핑 테이블.

환경(prod/vps) × 시장(domestic/overseas) 조합별로 TR_ID와
REST/WebSocket 도메인을 관리한다.

상위 모듈(rest.py, ws.py)은 이 모듈만 참조하고 원시 TR_ID 문자열을 직접 다루지 않는다.

참조: open-trading-api 공식 문서 및 샘플
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from core.config.settings import Env, Market

# ---------------------------------------------------------------------------
# 도메인 상수
# ---------------------------------------------------------------------------

REST_DOMAIN: Final[dict[Env, str]] = {
    Env.PROD: "https://openapi.koreainvestment.com:9443",
    Env.VPS:  "https://openapivts.koreainvestment.com:29443",
}

WS_DOMAIN: Final[dict[Env, str]] = {
    Env.PROD: "ws://ops.koreainvestment.com:21000",
    Env.VPS:  "ws://ops.koreainvestment.com:31000",
}

# ---------------------------------------------------------------------------
# TR_ID 상수
# ---------------------------------------------------------------------------

# ── 국내 주식 ────────────────────────────────────────────────────────────────

# 현재가 조회
DOMESTIC_PRICE_PROD: Final = "FHKST01010100"
DOMESTIC_PRICE_VPS:  Final = "FHKST01010100"  # 동일

# 잔고 조회
DOMESTIC_BALANCE_PROD: Final = "TTTC8434R"
DOMESTIC_BALANCE_VPS:  Final = "VTTC8434R"

# 매수 주문
DOMESTIC_BUY_PROD: Final = "TTTC0802U"
DOMESTIC_BUY_VPS:  Final = "VTTC0802U"

# 매도 주문
DOMESTIC_SELL_PROD: Final = "TTTC0801U"
DOMESTIC_SELL_VPS:  Final = "VTTC0801U"

# 주문 취소
DOMESTIC_CANCEL_PROD: Final = "TTTC0803U"
DOMESTIC_CANCEL_VPS:  Final = "VTTC0803U"

# 주문 수정
DOMESTIC_MODIFY_PROD: Final = "TTTC0803U"
DOMESTIC_MODIFY_VPS:  Final = "VTTC0803U"

# 주문 조회
DOMESTIC_ORDER_QUERY_PROD: Final = "TTTC8001R"
DOMESTIC_ORDER_QUERY_VPS:  Final = "VTTC8001R"

# WebSocket 실시간 체결가
DOMESTIC_WS_PRICE: Final = "H0STCNT0"

# WebSocket 실시간 호가
DOMESTIC_WS_QUOTE: Final = "H0STASP0"

# WebSocket 실시간 체결통보
DOMESTIC_WS_FILL: Final = "H0STCNI0"

# ── 해외 주식 ────────────────────────────────────────────────────────────────

# 현재가 조회 (미국)
OVERSEAS_PRICE_PROD: Final = "HHDFS76200200"
OVERSEAS_PRICE_VPS:  Final = "HHDFS76200200"

# 잔고 조회
OVERSEAS_BALANCE_PROD: Final = "TTTS3012R"
OVERSEAS_BALANCE_VPS:  Final = "VTTS3012R"

# 매수 주문 (미국)
OVERSEAS_BUY_PROD: Final = "TTTT1002U"
OVERSEAS_BUY_VPS:  Final = "VTTT1002U"

# 매도 주문 (미국)
OVERSEAS_SELL_PROD: Final = "TTTT1006U"
OVERSEAS_SELL_VPS:  Final = "VTTT1006U"

# WebSocket 실시간 체결가 (미국)
OVERSEAS_WS_PRICE: Final = "HDFSCNT0"


# ---------------------------------------------------------------------------
# 매핑 조회 API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrIdSet:
    """특정 환경×시장 조합의 TR_ID 집합."""

    price: str
    balance: str
    buy: str
    sell: str
    cancel: str
    order_query: str
    ws_price: str
    ws_quote: str | None
    ws_fill: str | None


_TR_ID_MAP: Final[dict[tuple[Env, Market], TrIdSet]] = {
    (Env.PROD, Market.DOMESTIC): TrIdSet(
        price=DOMESTIC_PRICE_PROD,
        balance=DOMESTIC_BALANCE_PROD,
        buy=DOMESTIC_BUY_PROD,
        sell=DOMESTIC_SELL_PROD,
        cancel=DOMESTIC_CANCEL_PROD,
        order_query=DOMESTIC_ORDER_QUERY_PROD,
        ws_price=DOMESTIC_WS_PRICE,
        ws_quote=DOMESTIC_WS_QUOTE,
        ws_fill=DOMESTIC_WS_FILL,
    ),
    (Env.VPS, Market.DOMESTIC): TrIdSet(
        price=DOMESTIC_PRICE_VPS,
        balance=DOMESTIC_BALANCE_VPS,
        buy=DOMESTIC_BUY_VPS,
        sell=DOMESTIC_SELL_VPS,
        cancel=DOMESTIC_CANCEL_VPS,
        order_query=DOMESTIC_ORDER_QUERY_VPS,
        ws_price=DOMESTIC_WS_PRICE,
        ws_quote=DOMESTIC_WS_QUOTE,
        ws_fill=DOMESTIC_WS_FILL,
    ),
    (Env.PROD, Market.OVERSEAS): TrIdSet(
        price=OVERSEAS_PRICE_PROD,
        balance=OVERSEAS_BALANCE_PROD,
        buy=OVERSEAS_BUY_PROD,
        sell=OVERSEAS_SELL_PROD,
        cancel=OVERSEAS_BUY_PROD,   # 해외 취소는 별도 확인 필요 — 현재는 buy TR_ID 임시 사용
        order_query=OVERSEAS_BALANCE_PROD,
        ws_price=OVERSEAS_WS_PRICE,
        ws_quote=None,
        ws_fill=None,
    ),
    (Env.VPS, Market.OVERSEAS): TrIdSet(
        price=OVERSEAS_PRICE_VPS,
        balance=OVERSEAS_BALANCE_VPS,
        buy=OVERSEAS_BUY_VPS,
        sell=OVERSEAS_SELL_VPS,
        cancel=OVERSEAS_BUY_VPS,
        order_query=OVERSEAS_BALANCE_VPS,
        ws_price=OVERSEAS_WS_PRICE,
        ws_quote=None,
        ws_fill=None,
    ),
}


def get_tr_ids(env: Env, market: Market) -> TrIdSet:
    """환경과 시장에 맞는 TR_ID 집합을 반환한다."""
    key = (env, market)
    if key not in _TR_ID_MAP:
        raise ValueError(f"지원하지 않는 환경/시장 조합: {env.value}/{market.value}")
    return _TR_ID_MAP[key]


def get_rest_domain(env: Env) -> str:
    """환경별 REST API 도메인을 반환한다."""
    return REST_DOMAIN[env]


def get_ws_domain(env: Env) -> str:
    """환경별 WebSocket 도메인을 반환한다."""
    return WS_DOMAIN[env]
