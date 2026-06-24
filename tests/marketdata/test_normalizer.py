"""MarketData 정규화 테스트."""

from __future__ import annotations

from core.marketdata.models import Candle, Quote, Tick
from core.marketdata.normalizer import (
    normalize_domestic_quote,
    normalize_domestic_tick,
    normalize_overseas_tick,
    normalize_price_to_candle,
)

# ---------------------------------------------------------------------------
# Tick 정규화
# ---------------------------------------------------------------------------

# H0STCNT0 파이프 포맷: 41개 필드, 인덱스 2=체결단가, 9=체결거래량
_DOMESTIC_TICK_BODY = "^".join(
    ["000000", "153000"] +      # 0=tr_key, 1=HHMMSS
    ["75000"] +                 # 2=stck_cntg_unpr (체결단가)
    ["0"] * 6 +                 # 3~8
    ["5000"] +                  # 9=cntg_vol (체결거래량)
    ["0"] * 31                  # 나머지
)


def test_normalize_domestic_tick_basic():
    tick = normalize_domestic_tick("005930", _DOMESTIC_TICK_BODY)
    assert tick is not None
    assert isinstance(tick, Tick)
    assert tick.symbol == "005930"
    assert tick.price == 75000.0
    assert tick.volume == 5000
    assert tick.market == "domestic"


def test_normalize_domestic_tick_invalid_body():
    result = normalize_domestic_tick("005930", "bad_data")
    assert result is None


def test_normalize_overseas_tick():
    # HDFSCNT0: 인덱스 11=현재가, 12=거래량
    parts = ["0"] * 13
    parts[11] = "150.5"
    parts[12] = "1000000"
    body = "^".join(parts)
    tick = normalize_overseas_tick("AAPL", body)
    assert tick is not None
    assert tick.price == 150.5
    assert tick.volume == 1000000
    assert tick.market == "overseas"


# ---------------------------------------------------------------------------
# Quote 정규화
# ---------------------------------------------------------------------------

# H0STASP0: 인덱스 3=매도호가1, 13=매수호가1, 23=매도잔량1, 33=매수잔량1
_DOMESTIC_QUOTE_BODY = "^".join(
    ["0"] * 3 +       # 0~2
    ["76000"] +        # 3=askp1
    ["0"] * 9 +        # 4~12
    ["75500"] +        # 13=bidp1
    ["0"] * 9 +        # 14~22
    ["100"] +          # 23=askp_rsqn1
    ["0"] * 9 +        # 24~32
    ["200"] +          # 33=bidp_rsqn1
    ["0"] * 7          # 나머지
)


def test_normalize_domestic_quote():
    quote = normalize_domestic_quote("005930", _DOMESTIC_QUOTE_BODY)
    assert quote is not None
    assert isinstance(quote, Quote)
    assert quote.ask_price == 76000.0
    assert quote.bid_price == 75500.0
    assert quote.ask_qty == 100
    assert quote.bid_qty == 200


# ---------------------------------------------------------------------------
# Candle 정규화
# ---------------------------------------------------------------------------


def test_normalize_price_to_candle_domestic():
    output = {
        "stck_oprc": "74000",
        "stck_hgpr": "76000",
        "stck_lwpr": "73500",
        "stck_prpr": "75000",
        "acml_vol": "1234567",
    }
    candle = normalize_price_to_candle("005930", output, "domestic")
    assert isinstance(candle, Candle)
    assert candle.close == 75000.0
    assert candle.volume == 1234567
    assert candle.market == "domestic"


def test_normalize_price_to_candle_overseas():
    output = {
        "open": "149.0",
        "high": "152.0",
        "low": "148.5",
        "last": "151.0",
        "tvol": "50000000",
    }
    candle = normalize_price_to_candle("AAPL", output, "overseas")
    assert candle.close == 151.0
    assert candle.market == "overseas"
