"""AnalystAgent 단위 테스트."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from core.strategy.plugins.bbc_buy import BbcBuySignal, EntryTime
from screener.agents.analyst_agent import AnalystAgent, RankedStock, StockSummary


def _stock(**overrides) -> RankedStock:
    defaults = dict(
        ticker="005930",
        name="삼성전자",
        rank=1,
        weighted_score=4.2,
        score_breakdown={"growth": 4, "profitability": 5, "cashflow": 4, "stability": 5, "valuation": 3},
        per=12.3,
        pbr=1.2,
        foreign_institution_streak=5,
        volume_surge_ratio=2.1,
    )
    defaults.update(overrides)
    return RankedStock(**defaults)


def _claude_response(obj: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"content": [{"text": json.dumps(obj, ensure_ascii=False)}]}
    return resp


class TestRankedStockFromRow:
    def test_builds_from_series(self) -> None:
        row = pd.Series(
            {
                "ticker": "005930",
                "name": "삼성전자",
                "rank": 1,
                "weighted_score": 4.2,
                "growth": 4,
                "profitability": 5,
                "cashflow": 4,
                "stability": 5,
                "valuation": 3,
                "per": 12.3,
                "pbr": 1.2,
                "foreign_institution_streak": 5,
                "volume_surge_ratio": 2.1,
            }
        )

        stock = RankedStock.from_row(row)

        assert stock.ticker == "005930"
        assert stock.score_breakdown["growth"] == 4
        assert stock.per == 12.3

    def test_missing_optional_fields_become_none(self) -> None:
        row = pd.Series({"ticker": "005930", "name": "삼성전자", "rank": 1, "weighted_score": 4.0})

        stock = RankedStock.from_row(row)

        assert stock.per is None
        assert stock.volume_surge_ratio is None


class TestSummarize:
    @pytest.mark.asyncio
    async def test_parses_valid_json_response(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        resp = _claude_response(
            {
                "one_line_thesis": "메모리 업턴 초입 + 재무 건전성 최상위",
                "protips": ["3분기 연속 영업이익률 개선"],
                "risk_flags": [],
            }
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summary = await agent.summarize(_stock(), disclosures=[])

        assert isinstance(summary, StockSummary)
        assert summary.one_line_thesis == "메모리 업턴 초입 + 재무 건전성 최상위"
        assert summary.protips == ["3분기 연속 영업이익률 개선"]
        assert summary.score_breakdown["growth"] == 4

    @pytest.mark.asyncio
    async def test_api_failure_falls_back_to_quant_summary(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection error"))
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summary = await agent.summarize(_stock(), disclosures=[])

        assert summary.one_line_thesis == "정량 지표 기준 상위 랭크"
        assert any("DEGRADED MODE" in flag for flag in summary.risk_flags)

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"content": [{"text": "이건 JSON이 아닙니다"}]}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summary = await agent.summarize(_stock(), disclosures=[])

        assert summary.one_line_thesis == "정량 지표 기준 상위 랭크"

    @pytest.mark.asyncio
    async def test_forbidden_phrase_in_thesis_replaced(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        resp = _claude_response(
            {"one_line_thesis": "지금 매수 추천합니다", "protips": [], "risk_flags": []}
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summary = await agent.summarize(_stock(), disclosures=[])

        assert summary.one_line_thesis == "정량 지표 기준 상위 랭크"
        assert any("REVIEW REQUIRED" in flag for flag in summary.risk_flags)

    @pytest.mark.asyncio
    async def test_forbidden_phrase_in_protip_removed(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        resp = _claude_response(
            {
                "one_line_thesis": "재무 건전성 양호",
                "protips": ["부채비율 낮음", "적극 매수 타이밍"],
                "risk_flags": [],
            }
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summary = await agent.summarize(_stock(), disclosures=[])

        assert summary.protips == ["부채비율 낮음"]
        assert any("REVIEW REQUIRED" in flag for flag in summary.risk_flags)

    @pytest.mark.asyncio
    async def test_truncated_response_falls_back_with_clear_reason(self) -> None:
        agent = AnalystAgent(api_key="test-key", max_tokens=400)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "content": [{"text": '{"one_line_thesis": "잘린 응답', "type": "text"}],
            "stop_reason": "max_tokens",
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summary = await agent.summarize(_stock(), disclosures=[])

        assert summary.one_line_thesis == "정량 지표 기준 상위 랭크"
        assert any("DEGRADED MODE" in flag for flag in summary.risk_flags)

    @pytest.mark.asyncio
    async def test_bbc_signal_included_in_prompt_and_summary(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        resp = _claude_response(
            {"one_line_thesis": "재무 건전성 양호", "protips": [], "risk_flags": []}
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        bbc_signal = BbcBuySignal(
            principle=2, entry_time=EntryTime.AFTERNOON, reason="제2원칙 눌림목: 테스트"
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            summary = await agent.summarize(_stock(), disclosures=[], bbc_signal=bbc_signal)

        assert summary.bbc_principle == 2
        assert summary.bbc_reason == "제2원칙 눌림목: 테스트"
        sent_prompt = mock_client.post.call_args.kwargs["json"]["messages"][0]["content"]
        assert "제2원칙 눌림목: 테스트" in sent_prompt

    @pytest.mark.asyncio
    async def test_no_bbc_signal_leaves_fields_none(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        resp = _claude_response(
            {"one_line_thesis": "재무 건전성 양호", "protips": [], "risk_flags": []}
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summary = await agent.summarize(_stock(), disclosures=[])

        assert summary.bbc_principle is None
        assert summary.bbc_reason is None

    @pytest.mark.asyncio
    async def test_bbc_signal_preserved_in_fallback(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection error"))
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        bbc_signal = BbcBuySignal(
            principle=3, entry_time=EntryTime.MORNING, reason="제3원칙 급락저점: 테스트"
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            summary = await agent.summarize(_stock(), disclosures=[], bbc_signal=bbc_signal)

        # Claude 장애 폴백이어도 결정론적 BBC 판정은 그대로 유지된다.
        assert summary.bbc_principle == 3
        assert summary.bbc_reason == "제3원칙 급락저점: 테스트"
        assert summary.one_line_thesis == "정량 지표 기준 상위 랭크"

    @pytest.mark.asyncio
    async def test_clean_response_has_no_review_flag(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        resp = _claude_response(
            {"one_line_thesis": "재무 건전성 양호", "protips": ["부채비율 낮음"], "risk_flags": []}
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summary = await agent.summarize(_stock(), disclosures=[])

        assert summary.risk_flags == []


class TestSummarizeBatch:
    @pytest.mark.asyncio
    async def test_empty_items_returns_empty_dict(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        assert await agent.summarize_batch([]) == {}

    @pytest.mark.asyncio
    async def test_batch_success_parses_all_results(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        stock = _stock()

        create_resp = MagicMock()
        create_resp.raise_for_status = MagicMock()
        create_resp.json.return_value = {"id": "msgbatch_1", "processing_status": "in_progress"}

        status_resp = MagicMock()
        status_resp.raise_for_status = MagicMock()
        status_resp.json.return_value = {"id": "msgbatch_1", "processing_status": "ended"}

        result_obj = {
            "one_line_thesis": "메모리 업턴 초입",
            "protips": ["영업이익률 개선"],
            "risk_flags": [],
        }
        results_resp = MagicMock()
        results_resp.raise_for_status = MagicMock()
        results_resp.text = json.dumps(
            {
                "custom_id": stock.ticker,
                "result": {
                    "type": "succeeded",
                    "message": {
                        "content": [
                            {"type": "text", "text": json.dumps(result_obj, ensure_ascii=False)}
                        ]
                    },
                },
            },
            ensure_ascii=False,
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=create_resp)
        mock_client.get = AsyncMock(side_effect=[status_resp, results_resp])
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summaries = await agent.summarize_batch([(stock, [], None)])

        assert summaries[stock.ticker].one_line_thesis == "메모리 업턴 초입"
        mock_client.post.assert_called_once()
        assert (
            mock_client.post.call_args.args[0]
            == "https://api.anthropic.com/v1/messages/batches"
        )

    @pytest.mark.asyncio
    async def test_batch_creation_failure_falls_back_all(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        stock = _stock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network down"))
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summaries = await agent.summarize_batch([(stock, [], None)])

        assert summaries[stock.ticker].one_line_thesis == "정량 지표 기준 상위 랭크"
        assert any("DEGRADED MODE" in flag for flag in summaries[stock.ticker].risk_flags)

    @pytest.mark.asyncio
    async def test_batch_item_error_falls_back_single_ticker(self) -> None:
        agent = AnalystAgent(api_key="test-key")
        stock = _stock()

        create_resp = MagicMock()
        create_resp.raise_for_status = MagicMock()
        create_resp.json.return_value = {"id": "msgbatch_1", "processing_status": "in_progress"}

        status_resp = MagicMock()
        status_resp.raise_for_status = MagicMock()
        status_resp.json.return_value = {"id": "msgbatch_1", "processing_status": "ended"}

        results_resp = MagicMock()
        results_resp.raise_for_status = MagicMock()
        results_resp.text = json.dumps(
            {
                "custom_id": stock.ticker,
                "result": {"type": "errored", "error": {"type": "invalid_request"}},
            }
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=create_resp)
        mock_client.get = AsyncMock(side_effect=[status_resp, results_resp])
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            summaries = await agent.summarize_batch([(stock, [], None)])

        assert summaries[stock.ticker].one_line_thesis == "정량 지표 기준 상위 랭크"
