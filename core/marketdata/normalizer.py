"""
KIS 원시 데이터 → 내부 표준(Tick/Quote/Candle) 정규화.

KIS WebSocket 파이프 포맷과 REST 응답을 각각 정규화한다.
파이프 포맷 참조: open-trading-api 실시간 시세 필드 정의
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from core.marketdata.models import Candle, Quote, Tick

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WebSocket 파이프 포맷 정규화
# ---------------------------------------------------------------------------
# KIS 국내 실시간 체결가(H0STCNT0) 파이프 포맷 필드 인덱스
_D_PRICE_STCK_CNTG_UNPR = 2   # 체결 단가
_D_PRICE_CNTG_VOL = 9         # 체결 거래량
_D_PRICE_STCK_CNTG_HOUR = 1   # 체결 시간 (HHMMSS)

# KIS 국내 호가(H0STASP0) 파이프 포맷 필드 인덱스
_D_QUOTE_ASKP1 = 3    # 매도호가1
_D_QUOTE_BIDP1 = 13   # 매수호가1
_D_QUOTE_ASKP_RSQN1 = 23  # 매도호가잔량1
_D_QUOTE_BIDP_RSQN1 = 33  # 매수호가잔량1


def normalize_domestic_tick(symbol: str, data_body: str) -> Tick | None:
    """국내 실시간 체결가(H0STCNT0) 파이프 문자열을 Tick으로 변환한다."""
    parts = data_body.split("^")
    try:
        price = float(parts[_D_PRICE_STCK_CNTG_UNPR])
        volume = int(parts[_D_PRICE_CNTG_VOL])
        return Tick(
            symbol=symbol,
            price=price,
            volume=volume,
            timestamp=datetime.now(UTC),
            market="domestic",
        )
    except (IndexError, ValueError) as exc:
        logger.warning("국내 체결가 파싱 실패 (%s): %s | body=%s", symbol, exc, data_body[:80])
        return None


def normalize_domestic_quote(symbol: str, data_body: str) -> Quote | None:
    """국내 실시간 호가(H0STASP0) 파이프 문자열을 Quote로 변환한다."""
    parts = data_body.split("^")
    try:
        return Quote(
            symbol=symbol,
            bid_price=float(parts[_D_QUOTE_BIDP1]),
            ask_price=float(parts[_D_QUOTE_ASKP1]),
            bid_qty=int(parts[_D_QUOTE_BIDP_RSQN1]),
            ask_qty=int(parts[_D_QUOTE_ASKP_RSQN1]),
            timestamp=datetime.now(UTC),
        )
    except (IndexError, ValueError) as exc:
        logger.warning("국내 호가 파싱 실패 (%s): %s | body=%s", symbol, exc, data_body[:80])
        return None


def normalize_overseas_tick(symbol: str, data_body: str) -> Tick | None:
    """해외 실시간 체결가(HDFSCNT0) 파이프 문자열을 Tick으로 변환한다."""
    parts = data_body.split("^")
    try:
        price = float(parts[11])   # OVRS_STCK_PRPR (해외 현재가)
        volume = int(parts[12])    # ACML_VOL
        return Tick(
            symbol=symbol,
            price=price,
            volume=volume,
            timestamp=datetime.now(UTC),
            market="overseas",
        )
    except (IndexError, ValueError) as exc:
        logger.warning("해외 체결가 파싱 실패 (%s): %s | body=%s", symbol, exc, data_body[:80])
        return None


# ---------------------------------------------------------------------------
# REST 응답 정규화
# ---------------------------------------------------------------------------


def normalize_price_to_candle(symbol: str, price_output: dict, market: str = "domestic") -> Candle:
    """REST 현재가 응답(output dict)을 Candle로 변환한다.

    국내: stck_prpr / stck_oprc / stck_hgpr / stck_lwpr / acml_vol
    해외: last / open / high / low / tvol
    """
    if market == "domestic":
        return Candle(
            symbol=symbol,
            open=float(price_output.get("stck_oprc", 0)),
            high=float(price_output.get("stck_hgpr", 0)),
            low=float(price_output.get("stck_lwpr", 0)),
            close=float(price_output.get("stck_prpr", 0)),
            volume=int(price_output.get("acml_vol", 0)),
            timestamp=datetime.now(UTC),
            market=market,
            interval="1d",
        )
    return Candle(
        symbol=symbol,
        open=float(price_output.get("open", 0)),
        high=float(price_output.get("high", 0)),
        low=float(price_output.get("low", 0)),
        close=float(price_output.get("last", 0)),
        volume=int(price_output.get("tvol", 0)),
        timestamp=datetime.now(UTC),
        market=market,
        interval="1d",
    )
