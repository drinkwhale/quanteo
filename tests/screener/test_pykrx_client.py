"""PykrxClient 단위 테스트."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from screener.data.collectors.pykrx_client import PykrxClient


def _ohlcv_df(tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {"종가": [10000] * len(tickers), "거래량": [1000] * len(tickers), "등락률": [1.0] * len(tickers)},
        index=pd.Index(tickers, name="티커"),
    )


def _cap_df(tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {"시가총액": [100_000_000_000] * len(tickers), "상장주식수": [10_000_000] * len(tickers)},
        index=pd.Index(tickers, name="티커"),
    )


def _fund_df(tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {"PER": [10.0] * len(tickers), "PBR": [1.0] * len(tickers), "DIV": [2.0] * len(tickers)},
        index=pd.Index(tickers, name="티커"),
    )


@pytest.mark.asyncio
async def test_fetch_universe_merges_ohlcv_cap_fundamental(tmp_path: Path) -> None:
    client = PykrxClient(cache_dir=tmp_path)

    def ohlcv_side_effect(date, market):
        return _ohlcv_df(["005930"]) if market == "KOSPI" else _ohlcv_df(["247540"])

    def cap_side_effect(date, market):
        return _cap_df(["005930"] if market == "KOSPI" else ["247540"])

    def fund_side_effect(date, market):
        return _fund_df(["005930"] if market == "KOSPI" else ["247540"])

    with (
        patch("pykrx.stock.get_market_ohlcv", side_effect=ohlcv_side_effect),
        patch("pykrx.stock.get_market_cap", side_effect=cap_side_effect),
        patch("pykrx.stock.get_market_fundamental", side_effect=fund_side_effect),
        patch("pykrx.stock.get_market_ticker_name", return_value="테스트종목"),
    ):
        df = await client.fetch_universe("20260721")

    assert set(df["ticker"]) == {"005930", "247540"}
    assert "market_cap" in df.columns
    assert "per" in df.columns
    assert set(df["market"]) == {"KOSPI", "KOSDAQ"}


@pytest.mark.asyncio
async def test_fetch_universe_maps_sector(tmp_path: Path) -> None:
    client = PykrxClient(cache_dir=tmp_path)

    def ohlcv_side_effect(date, market):
        return _ohlcv_df(["005930"]) if market == "KOSPI" else pd.DataFrame()

    sector_df = pd.DataFrame({"업종명": ["반도체"]}, index=pd.Index(["005930"], name="티커"))

    with (
        patch("pykrx.stock.get_market_ohlcv", side_effect=ohlcv_side_effect),
        patch("pykrx.stock.get_market_cap", return_value=_cap_df(["005930"])),
        patch("pykrx.stock.get_market_fundamental", return_value=_fund_df(["005930"])),
        patch("pykrx.stock.get_market_ticker_name", return_value="삼성전자"),
        patch(
            "pykrx.stock.get_market_sector_classifications",
            side_effect=lambda date, market: sector_df if market == "KOSPI" else pd.DataFrame(),
        ),
    ):
        df = await client.fetch_universe("20260721")

    assert df.iloc[0]["sector"] == "반도체"


@pytest.mark.asyncio
async def test_fetch_universe_sector_failure_falls_back_to_unknown(tmp_path: Path) -> None:
    client = PykrxClient(cache_dir=tmp_path)

    def ohlcv_side_effect(date, market):
        return _ohlcv_df(["005930"]) if market == "KOSPI" else pd.DataFrame()

    with (
        patch("pykrx.stock.get_market_ohlcv", side_effect=ohlcv_side_effect),
        patch("pykrx.stock.get_market_cap", return_value=_cap_df(["005930"])),
        patch("pykrx.stock.get_market_fundamental", return_value=_fund_df(["005930"])),
        patch("pykrx.stock.get_market_ticker_name", return_value="삼성전자"),
        patch(
            "pykrx.stock.get_market_sector_classifications",
            side_effect=Exception("network error"),
        ),
    ):
        df = await client.fetch_universe("20260721")

    assert df.iloc[0]["sector"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_fetch_universe_falls_back_to_previous_business_day(tmp_path: Path) -> None:
    client = PykrxClient(cache_dir=tmp_path)
    call_dates: list[str] = []

    def ohlcv_side_effect(date, market):
        call_dates.append(date)
        if date == "20260721":
            return pd.DataFrame()
        return _ohlcv_df(["005930"]) if market == "KOSPI" else pd.DataFrame()

    with (
        patch("pykrx.stock.get_market_ohlcv", side_effect=ohlcv_side_effect),
        patch("pykrx.stock.get_market_cap", return_value=_cap_df(["005930"])),
        patch("pykrx.stock.get_market_fundamental", return_value=_fund_df(["005930"])),
        patch("pykrx.stock.get_market_ticker_name", return_value="테스트종목"),
    ):
        df = await client.fetch_universe("20260721")

    assert "20260720" in call_dates
    assert not df.empty


@pytest.mark.asyncio
async def test_fetch_universe_cache_hit_skips_pykrx_call(tmp_path: Path) -> None:
    client = PykrxClient(cache_dir=tmp_path)
    cache_path = tmp_path / "20260721_ohlcv.parquet"
    tmp_path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": ["005930"], "close": [10000]}).to_parquet(cache_path)

    with patch("pykrx.stock.get_market_ohlcv") as mock_ohlcv:
        df = await client.fetch_universe("20260721")

    mock_ohlcv.assert_not_called()
    assert df["ticker"].tolist() == ["005930"]


@pytest.mark.asyncio
async def test_fetch_investor_trading_merges_foreign_and_institution(tmp_path: Path) -> None:
    client = PykrxClient(cache_dir=tmp_path)

    def net_purchases_side_effect(fromdate, todate, market, investor):
        col = "순매수거래대금"
        ticker = "005930" if market == "KOSPI" else "247540"
        value = 1000 if investor == "외국인" else 2000
        return pd.DataFrame({col: [value]}, index=pd.Index([ticker], name="티커"))

    with patch(
        "pykrx.stock.get_market_net_purchases_of_equities", side_effect=net_purchases_side_effect
    ):
        df = await client.fetch_investor_trading("20260721")

    kospi_row = df[df["ticker"] == "005930"].iloc[0]
    kosdaq_row = df[df["ticker"] == "247540"].iloc[0]
    assert kospi_row["foreign_net"] == 1000
    assert kospi_row["institution_net"] == 2000
    assert kosdaq_row["foreign_net"] == 1000


@pytest.mark.asyncio
async def test_fetch_investor_trading_sums_overlapping_ticker(tmp_path: Path) -> None:
    """비정상 상황(동일 티커가 KOSPI/KOSDAQ 양쪽에서 반환)에도 합산되어야 한다."""
    client = PykrxClient(cache_dir=tmp_path)

    def net_purchases_side_effect(fromdate, todate, market, investor):
        col = "순매수거래대금"
        if investor != "외국인":
            return pd.DataFrame({col: []}, index=pd.Index([], name="티커"))
        return pd.DataFrame({col: [1000]}, index=pd.Index(["005930"], name="티커"))

    with patch(
        "pykrx.stock.get_market_net_purchases_of_equities", side_effect=net_purchases_side_effect
    ):
        df = await client.fetch_investor_trading("20260721")

    row = df[df["ticker"] == "005930"].iloc[0]
    assert row["foreign_net"] == 2000  # KOSPI + KOSDAQ 양쪽에서 1000씩 합산


@pytest.mark.asyncio
async def test_fetch_short_balance(tmp_path: Path) -> None:
    client = PykrxClient(cache_dir=tmp_path)
    short_df = pd.DataFrame(
        {"공매도잔고": [1000], "비중": [0.5]}, index=pd.Index(["005930"], name="티커")
    )

    with patch("pykrx.stock.get_shorting_balance", return_value=short_df):
        df = await client.fetch_short_balance("20260721")

    assert df.iloc[0]["short_balance"] == 1000


def test_krx_credentials_set_env_when_both_provided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)

    PykrxClient(cache_dir=tmp_path, krx_id="user", krx_pw="pass")

    assert os.environ["KRX_ID"] == "user"
    assert os.environ["KRX_PW"] == "pass"


def test_krx_credentials_untouched_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)

    PykrxClient(cache_dir=tmp_path)

    assert "KRX_ID" not in os.environ
    assert "KRX_PW" not in os.environ
