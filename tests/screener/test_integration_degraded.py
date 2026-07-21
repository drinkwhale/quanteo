"""통합 테스트: DART API + Claude API 동시 장애 시에도 파이프라인이 완주하는지.

무음 실패 금지 원칙(T058/T102 폴백 조합) — 재무 데이터·LLM 요약이 모두
없어도 정량 데이터(시세·밸류에이션)만으로 리포트 발송까지 완주해야 한다.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from screener.agents.analyst_agent import AnalystAgent
from screener.data.collectors.dart_client import DartClient
from screener.data.collectors.pykrx_client import PykrxClient
from screener.notify.telegram_reporter import ScreenerNotifier
from screener.pipeline.screener import ScreenerConfig
from screener.scheduler.daily_job import DailyJob

TICKERS = ["005930", "000660"]


def _ohlcv_df(market: str) -> pd.DataFrame:
    if market != "KOSPI":
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "종가": [70000, 200000],
            "거래량": [10_000_000, 5_000_000],
            "거래대금": [700_000_000_000, 1_000_000_000_000],
            "등락률": [1.2, -0.5],
        },
        index=pd.Index(TICKERS, name="티커"),
    )


def _cap_df(market: str) -> pd.DataFrame:
    if market != "KOSPI":
        return pd.DataFrame()
    return pd.DataFrame(
        {"시가총액": [400_000_000_000_000, 150_000_000_000_000], "상장주식수": [6_000_000_000, 700_000_000]},
        index=pd.Index(TICKERS, name="티커"),
    )


def _fund_df(market: str) -> pd.DataFrame:
    if market != "KOSPI":
        return pd.DataFrame()
    return pd.DataFrame(
        {"PER": [12.0, 8.0], "PBR": [1.2, 1.5], "DIV": [2.0, 1.0]},
        index=pd.Index(TICKERS, name="티커"),
    )


def _ohlcv_side_effect(*args, **kwargs):
    """get_market_ohlcv는 두 가지 시그니처로 호출된다.

    - 전종목 스냅샷: get_market_ohlcv(date, market=market)
    - 단일 종목 기간 히스토리(BBC 매수 원칙 판정용): get_market_ohlcv(start, end, ticker)
    """
    if "market" in kwargs:
        return _ohlcv_df(kwargs["market"])
    return pd.DataFrame()


@pytest.mark.asyncio
async def test_dart_and_claude_down_still_sends_quant_report(tmp_path: Path) -> None:
    pykrx = PykrxClient(cache_dir=tmp_path / "pykrx")
    dart = DartClient(api_key="test-dart-key", cache_dir=tmp_path / "dart")
    analyst = AnalystAgent(api_key="test-anthropic-key")

    fake_tg = AsyncMock()
    fake_tg.send_raw = AsyncMock()
    notifier = ScreenerNotifier(telegram_notifier=fake_tg)

    config = ScreenerConfig(min_market_cap=0, min_avg_trading_value_20d=0, exclude_administrative=False)
    job = DailyJob(
        pykrx_client=pykrx,
        dart_client=dart,
        analyst_agent=analyst,
        notifier=notifier,
        screener_config=config,
        universe_top_n=10,
        report_top_n=10,
    )

    # DART: 생성자에서부터 예외 — fetch_financials()/fetch_recent_disclosures() 둘 다 장애
    mock_httpx_client = AsyncMock()
    mock_httpx_client.post = AsyncMock(side_effect=Exception("Claude API down"))
    mock_httpx_client.__aenter__.return_value = mock_httpx_client
    mock_httpx_client.__aexit__.return_value = None

    with (
        patch("pykrx.stock.get_market_ohlcv", side_effect=_ohlcv_side_effect),
        patch("pykrx.stock.get_market_cap", side_effect=lambda date, market: _cap_df(market)),
        patch(
            "pykrx.stock.get_market_fundamental", side_effect=lambda date, market: _fund_df(market)
        ),
        patch("pykrx.stock.get_market_ticker_name", return_value="테스트종목"),
        patch("pykrx.stock.get_market_sector_classifications", return_value=pd.DataFrame()),
        patch(
            "pykrx.stock.get_market_net_purchases_of_equities",
            return_value=pd.DataFrame({"순매수거래대금": []}),
        ),
        patch("pykrx.stock.get_shorting_balance", return_value=pd.DataFrame()),
        patch(
            "screener.data.collectors.dart_client.OpenDartReader",
            side_effect=Exception("DART API down"),
        ),
        patch("httpx.AsyncClient", return_value=mock_httpx_client),
    ):
        await job.run("20260721")

    # 파이프라인이 무음 실패하지 않고 끝까지 완주해 리포트를 발송해야 한다.
    assert fake_tg.send_raw.call_count == 3  # 헤더 1 + 종목 2
    sent_texts = [c.args[0] for c in fake_tg.send_raw.call_args_list]
    assert any("오늘의 발굴 종목" in t for t in sent_texts)

    # DART 장애 → 재무 피처 전부 결측 → 정량 스코어(PER 등)만으로 발송
    stock_texts = sent_texts[1:]
    for text in stock_texts:
        assert "PER" in text  # 시세/밸류에이션은 pykrx 경로라 DART 장애와 무관하게 살아있음

    # Claude 장애 → 폴백 문구만 포함, LLM 마커는 여전히 존재(💡)하되 내용은 정량 대체
    assert any("💡 정량 지표 기준 상위 랭크" in t for t in stock_texts)

    # 에러 알림이 아니라 정상 리포트로 처리됐는지 확인 (send_error_alert는 별도 텍스트 사용)
    assert not any("파이프라인 실패" in t for t in sent_texts)

    # DailyJob 자체는 실패로 간주하지 않았으므로 재시도 로그 없이 1회만 완주
    assert job.last_summaries
    for summary in job.last_summaries.values():
        assert "[DEGRADED MODE]" in " ".join(summary.risk_flags)
