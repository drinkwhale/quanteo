"""AnalystAgent 단위 테스트."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

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
