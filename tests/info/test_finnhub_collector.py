"""FinnhubCollector 단위 테스트."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from info.ai_filter.claude_filter import FilterResult
from info.news.finnhub_collector import FinnhubCollector


def _ok_response(data: list) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


def _status_response(status: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = []
    resp.raise_for_status = MagicMock()
    return resp


_SAMPLE_ENTRY = [
    {
        "headline": "NVDA blows earnings out of the water",
        "url": "https://news.com/nvda1",
        "summary": "NVDA Q2 results beat estimates",
        "datetime": 1719619200,
    }
]


# ---------------------------------------------------------------------------
# 정상 수집
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_returns_items():
    collector = FinnhubCollector(api_key="test-key", symbols=["NVDA"])

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=_ok_response(_SAMPLE_ENTRY)):
        items = await collector.fetch(["NVDA"])

    assert len(items) == 1
    assert "NVDA" in items[0].source


# ---------------------------------------------------------------------------
# Rate limit — 429 지수 백오프 3회 재시도 후 스킵
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_429_backoff_and_skip():
    collector = FinnhubCollector(api_key="test-key", symbols=["MU"])

    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=_status_response(429),
    ):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            items = await collector.fetch(["MU"])

    assert items == []


@pytest.mark.asyncio
async def test_429_then_success():
    collector = FinnhubCollector(api_key="test-key", symbols=["TSM"])
    responses = [_status_response(429), _ok_response(_SAMPLE_ENTRY)]
    call_idx = {"n": 0}

    async def _side_effect(*args, **kwargs):
        r = responses[min(call_idx["n"], len(responses) - 1)]
        call_idx["n"] += 1
        return r

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=_side_effect):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            items = await collector.fetch(["TSM"])

    assert len(items) == 1


# ---------------------------------------------------------------------------
# 500 오류 — 해당 심볼 스킵
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_500_error_skips_symbol():
    collector = FinnhubCollector(api_key="test-key", symbols=["AMD"])

    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=_status_response(500),
    ):
        items = await collector.fetch(["AMD"])

    assert items == []


# ---------------------------------------------------------------------------
# 빈 배열 응답 — Telegram 미발송
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_array_no_telegram():
    mock_notifier = AsyncMock()
    mock_notifier.send_news_alert = AsyncMock()
    mock_filter = AsyncMock()
    mock_filter.classify = AsyncMock(
        return_value=FilterResult(score="HIGH", reason="test", action="관망")
    )

    collector = FinnhubCollector(
        api_key="test-key",
        symbols=["ASML"],
        claude_filter=mock_filter,
        info_notifier=mock_notifier,
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=_ok_response([])):
        await collector.fetch(["ASML"])

    mock_notifier.send_news_alert.assert_not_called()


# ---------------------------------------------------------------------------
# Semaphore — 동시 요청 제한 동작
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    """Semaphore가 동시 요청을 제한하는지 확인."""
    collector = FinnhubCollector(api_key="test-key", symbols=["NVDA", "MU", "AMD"])
    active = {"n": 0, "max": 0}

    async def _track_concurrency(*args, **kwargs):
        active["n"] += 1
        active["max"] = max(active["max"], active["n"])
        await asyncio.sleep(0.01)
        active["n"] -= 1
        return _ok_response(_SAMPLE_ENTRY)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=_track_concurrency):
        await collector.fetch()

    assert active["max"] <= 10  # Semaphore 한도 이하
