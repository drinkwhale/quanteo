"""TokenBucketThrottler + with_retry 테스트."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from core.adapters.kis.throttler import (
    RateLimitExceeded,
    ThrottlerConfig,
    TokenBucketThrottler,
    with_retry,
)


# ---------------------------------------------------------------------------
# TokenBucketThrottler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throttler_acquires_without_error():
    throttler = TokenBucketThrottler(ThrottlerConfig(calls_per_second=100.0))
    await throttler.acquire()  # 예외 없이 통과해야 함


@pytest.mark.asyncio
async def test_throttler_enforces_min_interval(monkeypatch):
    """두 번째 호출이 최소 간격 후에 실행됨을 확인한다."""
    cfg = ThrottlerConfig(calls_per_second=10.0)  # 100ms 간격
    throttler = TokenBucketThrottler(cfg)

    start = time.monotonic()
    await throttler.acquire()
    await throttler.acquire()
    elapsed = time.monotonic() - start

    # 두 번째 호출까지 최소 100ms 대기 발생
    assert elapsed >= 0.09  # 여유 있게 90ms 이상


@pytest.mark.asyncio
async def test_throttler_config_defaults():
    throttler = TokenBucketThrottler()
    assert throttler.config.calls_per_second == 15.0
    assert throttler.config.max_retries == 5


# ---------------------------------------------------------------------------
# with_retry — 성공
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_success_on_first_attempt():
    throttler = TokenBucketThrottler(ThrottlerConfig(calls_per_second=1000.0))
    mock = AsyncMock(return_value="ok")

    result = await with_retry(mock, throttler)

    assert result == "ok"
    mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# with_retry — HTTP 429 재시도
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_retries_on_429(monkeypatch):
    """429 응답 후 성공하면 정상 반환."""
    throttler = TokenBucketThrottler(ThrottlerConfig(calls_per_second=1000.0))

    # asyncio.sleep을 패치해 실제 대기 없이 테스트
    monkeypatch.setattr("core.adapters.kis.throttler.asyncio.sleep", AsyncMock())

    _req = httpx.Request("GET", "https://example.com")
    _resp_429 = httpx.Response(429, request=_req)
    exc_429 = httpx.HTTPStatusError("rate limit", request=_req, response=_resp_429)

    call_count = 0

    async def _flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise exc_429
        return "success"

    result = await with_retry(_flaky, throttler)

    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_with_retry_raises_after_max_retries(monkeypatch):
    """최대 재시도 초과 시 RateLimitExceeded 발생."""
    throttler = TokenBucketThrottler(ThrottlerConfig(calls_per_second=1000.0, max_retries=2))
    monkeypatch.setattr("core.adapters.kis.throttler.asyncio.sleep", AsyncMock())

    _req = httpx.Request("GET", "https://example.com")
    _resp_429 = httpx.Response(429, request=_req)
    exc_429 = httpx.HTTPStatusError("rate limit", request=_req, response=_resp_429)

    async def _always_fail():
        raise exc_429

    with pytest.raises(RateLimitExceeded):
        await with_retry(_always_fail, throttler)


# ---------------------------------------------------------------------------
# with_retry — KIS Rate Limit 에러 코드
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_retries_on_kis_rate_limit_code(monkeypatch):
    """EGW00201 에러 후 성공하면 정상 반환."""
    throttler = TokenBucketThrottler(ThrottlerConfig(calls_per_second=1000.0))
    monkeypatch.setattr("core.adapters.kis.throttler.asyncio.sleep", AsyncMock())

    call_count = 0

    async def _flaky():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("KIS API 오류 (rt_cd=EGW00201): 초당 거래건수를 초과하였습니다.")
        return "ok"

    result = await with_retry(_flaky, throttler)

    assert result == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_with_retry_propagates_non_rate_limit_runtime_error():
    """Rate Limit이 아닌 RuntimeError는 즉시 전파된다."""
    throttler = TokenBucketThrottler(ThrottlerConfig(calls_per_second=1000.0))

    async def _fail():
        raise RuntimeError("KIS API 오류 (rt_cd=1): 일반 오류")

    with pytest.raises(RuntimeError, match="일반 오류"):
        await with_retry(_fail, throttler)


@pytest.mark.asyncio
async def test_with_retry_propagates_non_429_http_error():
    """429가 아닌 HTTP 에러는 즉시 전파된다."""
    throttler = TokenBucketThrottler(ThrottlerConfig(calls_per_second=1000.0))

    _req = httpx.Request("GET", "https://example.com")
    _resp_500 = httpx.Response(500, request=_req)

    async def _fail():
        raise httpx.HTTPStatusError("server error", request=_req, response=_resp_500)

    with pytest.raises(httpx.HTTPStatusError):
        await with_retry(_fail, throttler)
