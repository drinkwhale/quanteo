"""core/marketdata/index_quotes.py 테스트 — 전체 실패 시 502 승격, 캐시 폴백, 락."""

from __future__ import annotations

import pytest

from core.marketdata import index_quotes


@pytest.fixture(autouse=True)
def _reset_cache():
    """모듈 전역 캐시는 테스트 간 격리를 위해 매번 초기화한다."""
    index_quotes._cache = None
    yield
    index_quotes._cache = None


async def test_all_tickers_fail_with_no_cache_raises(monkeypatch):
    monkeypatch.setattr(index_quotes, "_fetch_sync", lambda tickers: [])

    with pytest.raises(RuntimeError):
        await index_quotes.get_index_quotes(use_cache=False)


async def test_all_tickers_fail_falls_back_to_stale_cache(monkeypatch):
    stale_quote = index_quotes.IndexQuote(
        key="kospi",
        label="코스피",
        price=8051.33,
        change=-37.01,
        change_rate=-0.0045,
        currency="KRW",
    )
    index_quotes._cache = (0.0, [stale_quote])

    monkeypatch.setattr(index_quotes, "_fetch_sync", lambda tickers: [])

    result = await index_quotes.get_index_quotes(use_cache=False)
    assert result == [stale_quote]


async def test_successful_fetch_populates_cache(monkeypatch):
    fresh_quote = index_quotes.IndexQuote(
        key="kospi",
        label="코스피",
        price=8100.0,
        change=48.67,
        change_rate=0.006,
        currency="KRW",
    )
    monkeypatch.setattr(index_quotes, "_fetch_sync", lambda tickers: [fresh_quote])

    result = await index_quotes.get_index_quotes()
    assert result == [fresh_quote]
    assert index_quotes._cache is not None
    assert index_quotes._cache[1] == [fresh_quote]


async def test_cache_hit_within_ttl_skips_fetch(monkeypatch):
    cached_quote = index_quotes.IndexQuote(
        key="kospi",
        label="코스피",
        price=8051.33,
        change=-37.01,
        change_rate=-0.0045,
        currency="KRW",
    )
    index_quotes._cache = (index_quotes.time.monotonic(), [cached_quote])

    calls = []
    monkeypatch.setattr(index_quotes, "_fetch_sync", lambda tickers: calls.append(1) or [])

    result = await index_quotes.get_index_quotes(use_cache=True)
    assert result == [cached_quote]
    assert calls == []  # 캐시가 신선하니 _fetch_sync가 호출되지 않아야 한다
