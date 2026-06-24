"""FixedIntervalThrottler + with_retry 테스트."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import httpx
import pytest

from core.adapters.kis.throttler import (
    FixedIntervalThrottler,
    RateLimitExceeded,
    ThrottlerConfig,
    TokenBucketThrottler,  # backward-compat alias
    with_retry,
)

# ---------------------------------------------------------------------------
# FixedIntervalThrottler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throttler_acquires_without_error():
    throttler = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=100.0))
    await throttler.acquire()  # 예외 없이 통과해야 함


@pytest.mark.asyncio
async def test_throttler_enforces_min_interval():
    """두 번째 호출이 최소 간격 후에 실행됨을 확인한다."""
    cfg = ThrottlerConfig(calls_per_second=10.0)  # 100ms 간격
    throttler = FixedIntervalThrottler(cfg)

    start = time.monotonic()
    await throttler.acquire()
    await throttler.acquire()
    elapsed = time.monotonic() - start

    # 두 번째 호출까지 최소 100ms 대기 발생
    assert elapsed >= 0.09  # 여유 있게 90ms 이상


@pytest.mark.asyncio
async def test_throttler_config_defaults():
    throttler = FixedIntervalThrottler()
    assert throttler.config.calls_per_second == 15.0
    assert throttler.config.max_retries == 5


@pytest.mark.asyncio
async def test_throttler_backward_compat_alias():
    """TokenBucketThrottler는 FixedIntervalThrottler의 alias다."""
    assert TokenBucketThrottler is FixedIntervalThrottler
    throttler = TokenBucketThrottler(ThrottlerConfig(calls_per_second=100.0))
    await throttler.acquire()  # 예외 없이 통과


@pytest.mark.asyncio
async def test_throttler_serializes_concurrent_acquire():
    """동시에 여러 acquire() 호출이 직렬화돼야 한다 (Lock 검증)."""
    cfg = ThrottlerConfig(calls_per_second=20.0)  # 50ms 간격
    throttler = FixedIntervalThrottler(cfg)

    call_times: list[float] = []

    async def track() -> None:
        await throttler.acquire()
        call_times.append(time.monotonic())

    # 3개 동시 실행
    await asyncio.gather(track(), track(), track())

    assert len(call_times) == 3
    call_times.sort()

    # 직렬화로 인해 연속 호출 간격이 최소 40ms 이상이어야 함
    for i in range(1, len(call_times)):
        gap = call_times[i] - call_times[i - 1]
        assert gap >= 0.04, f"호출 간격이 너무 짧습니다: {gap:.3f}s (기대 >= 0.04s)"


# ---------------------------------------------------------------------------
# with_retry — 성공
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_success_on_first_attempt():
    throttler = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0))
    mock = AsyncMock(return_value="ok")

    result = await with_retry(mock, throttler)

    assert result == "ok"
    mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# with_retry — HTTP 429 재시도
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_retries_on_429(monkeypatch):
    """429 응답 후 성공하면 정상 반환 (idempotent=True 기본값)."""
    throttler = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0))

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
    throttler = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0, max_retries=2))
    monkeypatch.setattr("core.adapters.kis.throttler.asyncio.sleep", AsyncMock())

    _req = httpx.Request("GET", "https://example.com")
    _resp_429 = httpx.Response(429, request=_req)
    exc_429 = httpx.HTTPStatusError("rate limit", request=_req, response=_resp_429)

    async def _always_fail():
        raise exc_429

    with pytest.raises(RateLimitExceeded):
        await with_retry(_always_fail, throttler)


@pytest.mark.asyncio
async def test_with_retry_non_idempotent_raises_immediately_on_429(monkeypatch):
    """idempotent=False 이면 429 첫 발생 시 재시도 없이 즉시 RateLimitExceeded."""
    throttler = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0))
    monkeypatch.setattr("core.adapters.kis.throttler.asyncio.sleep", AsyncMock())

    _req = httpx.Request("POST", "https://example.com")
    _resp_429 = httpx.Response(429, request=_req)
    exc_429 = httpx.HTTPStatusError("rate limit", request=_req, response=_resp_429)

    call_count = 0

    async def _order():
        nonlocal call_count
        call_count += 1
        raise exc_429

    with pytest.raises(RateLimitExceeded, match="비멱등"):
        await with_retry(_order, throttler, idempotent=False)

    # 재시도 없이 단 1번만 호출돼야 한다
    assert call_count == 1


# ---------------------------------------------------------------------------
# with_retry — KIS Rate Limit 에러 코드
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_retry_retries_on_kis_rate_limit_egw00201(monkeypatch):
    """EGW00201 에러 후 성공하면 정상 반환."""
    throttler = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0))
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
async def test_with_retry_retries_on_kis_rate_limit_egw00202(monkeypatch):
    """EGW00202 에러도 동일하게 재시도한다."""
    throttler = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0))
    monkeypatch.setattr("core.adapters.kis.throttler.asyncio.sleep", AsyncMock())

    call_count = 0

    async def _flaky():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("KIS API 오류 (rt_cd=EGW00202): 초당 거래건수를 초과하였습니다.")
        return "ok"

    result = await with_retry(_flaky, throttler)

    assert result == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_with_retry_propagates_non_rate_limit_runtime_error():
    """Rate Limit이 아닌 RuntimeError는 즉시 전파된다."""
    throttler = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0))

    async def _fail():
        raise RuntimeError("KIS API 오류 (rt_cd=1): 일반 오류")

    with pytest.raises(RuntimeError, match="일반 오류"):
        await with_retry(_fail, throttler)


@pytest.mark.asyncio
async def test_with_retry_propagates_non_429_http_error():
    """429가 아닌 HTTP 에러는 즉시 전파된다."""
    throttler = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0))

    _req = httpx.Request("GET", "https://example.com")
    _resp_500 = httpx.Response(500, request=_req)

    async def _fail():
        raise httpx.HTTPStatusError("server error", request=_req, response=_resp_500)

    with pytest.raises(httpx.HTTPStatusError):
        await with_retry(_fail, throttler)


@pytest.mark.asyncio
async def test_with_retry_propagates_cancelled_error():
    """asyncio.CancelledError는 즉시 전파된다 (재시도 없음)."""
    throttler = FixedIntervalThrottler(ThrottlerConfig(calls_per_second=1000.0))

    call_count = 0

    async def _cancelled():
        nonlocal call_count
        call_count += 1
        raise asyncio.CancelledError("태스크 취소")

    with pytest.raises(asyncio.CancelledError):
        await with_retry(_cancelled, throttler)

    # 재시도 없이 단 1번만 호출돼야 한다
    assert call_count == 1
