"""엔드투엔드 통합 테스트: Collector→Screener→Scorer→Ranker→AnalystAgent→Reporter.

pykrx/DART/Claude/Telegram 전부 mock — 실제 네트워크 호출 없이 파이프라인
전체 배선이 올바른지 검증한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


def _finstate_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"account_nm": "매출액", "thstrm_amount": "1,000,000"},
            {"account_nm": "영업이익", "thstrm_amount": "200,000"},
            {"account_nm": "당기순이익", "thstrm_amount": "150,000"},
            {"account_nm": "자본총계", "thstrm_amount": "800,000"},
            {"account_nm": "부채총계", "thstrm_amount": "500,000"},
            {"account_nm": "유동자산", "thstrm_amount": "300,000"},
            {"account_nm": "유동부채", "thstrm_amount": "100,000"},
            {"account_nm": "영업활동현금흐름", "thstrm_amount": "180,000"},
        ]
    )


def _claude_response(obj: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"content": [{"text": json.dumps(obj, ensure_ascii=False)}]}
    return resp


@pytest.mark.asyncio
async def test_full_pipeline_sends_report_with_llm_summary(tmp_path: Path) -> None:
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

    mock_dart_reader = MagicMock()
    mock_dart_reader.finstate_all.return_value = _finstate_df()
    mock_dart_reader.list.return_value = pd.DataFrame()  # 공시 없음

    mock_claude_resp = _claude_response(
        {
            "one_line_thesis": "메모리 업턴 초입",
            "protips": ["영업이익률 개선"],
            "risk_flags": [],
        }
    )
    mock_httpx_client = AsyncMock()
    mock_httpx_client.post = AsyncMock(return_value=mock_claude_resp)
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
        patch("screener.data.collectors.dart_client.OpenDartReader", return_value=mock_dart_reader),
        patch("httpx.AsyncClient", return_value=mock_httpx_client),
    ):
        await job.run("20260721")

    # 헤더 1건 + 종목 2건 = 3건 발송
    assert fake_tg.send_raw.call_count == 3
    sent_texts = [c.args[0] for c in fake_tg.send_raw.call_args_list]
    assert any("오늘의 발굴 종목" in t for t in sent_texts)
    assert any("💡 메모리 업턴 초입" in t for t in sent_texts)
    assert job.last_summaries  # CallbackHandler(T108)가 참조할 요약이 채워졌는지
