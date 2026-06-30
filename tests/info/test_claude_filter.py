"""ClaudeFilter 단위 테스트."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from info.ai_filter.claude_filter import (
    CRITICAL_KEYWORDS,
    ClaudeFilter,
    FilterResult,
)


def _make_filter(api_key: str = "test-key", notifier=None) -> ClaudeFilter:
    return ClaudeFilter(api_key=api_key, notifier=notifier)


def _claude_response(score: str, reason: str, action: str) -> dict:
    body = json.dumps({"score": score, "reason": reason, "action": action})
    return {
        "content": [{"type": "text", "text": body}],
        "model": ClaudeFilter.MODEL,
    }


# ---------------------------------------------------------------------------
# 키워드 사전 필터
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefilter_no_keyword_returns_low():
    f = _make_filter()
    result = await f.classify(title="오늘 날씨가 맑습니다", body="비 소식 없음")
    assert result.score == "LOW"
    assert result.reason == "키워드 미해당"


@pytest.mark.asyncio
async def test_prefilter_keyword_hit_calls_claude():
    f = _make_filter()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _claude_response("HIGH", "FOMC 결정", "관망")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await f.classify(title="FOMC 금리 인상 결정", body="연준이 25bp 인상")

    assert result.score == "HIGH"


# ---------------------------------------------------------------------------
# Claude API 정상 응답 파싱
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_high_score():
    f = _make_filter()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _claude_response("HIGH", "NVDA 실적 서프라이즈", "매수검토")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await f.classify("NVDA 어닝서프라이즈", "NVDA Q2 실적 기대치 대폭 상회")

    assert result == FilterResult(score="HIGH", reason="NVDA 실적 서프라이즈", action="매수검토")


# ---------------------------------------------------------------------------
# 1단 폴백: Claude API DOWN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_on_connect_error_two_or_more_keywords():
    f = _make_filter()
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("connection refused"),
    ):
        # FOMC + 금리 = 2개 → MEDIUM 반환
        result = await f.classify("FOMC 금리 인상 논의", "금리 관련 회의")

    assert result.score == "MEDIUM"
    assert "[DEGRADED MODE]" in result.reason


@pytest.mark.asyncio
async def test_fallback_on_connect_error_one_keyword():
    f = _make_filter()
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("connection refused"),
    ):
        # FOMC 1개만 → LOW
        result = await f.classify("FOMC 관련 뉴스", "기타 내용")

    assert result.score == "LOW"
    assert "[DEGRADED MODE]" in result.reason


# ---------------------------------------------------------------------------
# Haiku 응답 JSON 누락 필드
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_score_field_falls_back():
    f = _make_filter()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "content": [{"type": "text", "text": '{"reason": "테스트", "action": "관망"}'}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        # score 필드 없음 → ValueError → 1단 폴백
        result = await f.classify("SK하이닉스 주가", "반도체 관련 소식")

    assert "[DEGRADED MODE]" in result.reason


@pytest.mark.asyncio
async def test_empty_reason_field_falls_back():
    f = _make_filter()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "content": [{"type": "text", "text": '{"score": "HIGH", "reason": "", "action": "관망"}'}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await f.classify("SK하이닉스 공시", "DRAM 관련")

    assert "[DEGRADED MODE]" in result.reason


# ---------------------------------------------------------------------------
# 2단 폴백: CRITICAL_KEYWORDS 빈 리스트
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_keywords_triggers_operator_alert():
    mock_notifier = AsyncMock()
    f = _make_filter(notifier=mock_notifier)

    original = CRITICAL_KEYWORDS.copy()
    CRITICAL_KEYWORDS.clear()
    try:
        result = await f.classify("FOMC 금리", "중요 뉴스")
    finally:
        CRITICAL_KEYWORDS.extend(original)

    assert result.score == "LOW"
    assert "[DEGRADED MODE]" in result.reason
    mock_notifier.send.assert_called_once()
