"""
KIS Rate Limit 스로틀러.

KIS REST API 호출 빈도 제한:
- 국내 주식 REST: 초당 20회 (KIS 공식 가이드)
- 여유분 확보를 위해 기본값 15회/초 적용

FixedIntervalThrottler: 호출 간격을 균등 분산 (고정 간격 직렬화).
  호출마다 1/calls_per_second 간격을 강제한다.
  asyncio.Lock으로 동시 호출을 직렬화해 간격이 겹치는 걸 방지한다.
  (Token Bucket처럼 버스트를 허용하지 않는다.)

with_retry: HTTP 429 / KIS EGW00201·EGW00202 에러 시 지수 백오프 재시도.
  주문처럼 멱등하지 않은 요청은 idempotent=False로 429 즉시 예외 처리.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------


@dataclass
class ThrottlerConfig:
    """스로틀러 파라미터."""

    calls_per_second: float = 15.0      # 초당 최대 호출 수 (KIS 한도 20, 여유분 확보)
    max_retries: int = 5                 # Rate limit 에러 시 최대 재시도 횟수
    base_backoff_seconds: float = 1.0   # 초기 백오프 대기 시간 (초)
    max_backoff_seconds: float = 60.0   # 최대 백오프 대기 시간 (초)


# ---------------------------------------------------------------------------
# 예외
# ---------------------------------------------------------------------------


class RateLimitExceeded(Exception):
    """최대 재시도 횟수를 초과했을 때."""


# ---------------------------------------------------------------------------
# 고정 간격 스로틀러
# ---------------------------------------------------------------------------


class FixedIntervalThrottler:
    """고정 간격 Rate Limit 스로틀러.

    호출마다 최소 간격(1 / calls_per_second)을 강제한다.
    asyncio.Lock으로 동시 호출을 직렬화해 초과 호출을 방지한다.

    Note:
        Token Bucket(버스트 허용)이 아닌 고정 간격 방식이다.
        KIS API는 버스트 허용 여부가 불분명하므로 보수적 고정 간격을 채택.
    """

    def __init__(self, config: ThrottlerConfig | None = None) -> None:
        self._config = config or ThrottlerConfig()
        self._interval = 1.0 / self._config.calls_per_second
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """슬롯을 획득한다. 필요 시 대기."""
        async with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    @property
    def config(self) -> ThrottlerConfig:
        return self._config


# 이전 이름 호환성 alias
TokenBucketThrottler = FixedIntervalThrottler


# ---------------------------------------------------------------------------
# 재시도 헬퍼
# ---------------------------------------------------------------------------


# KIS 자체 Rate Limit 에러 코드
_KIS_RATE_LIMIT_CODES = frozenset({"EGW00201", "EGW00202"})


def _is_kis_rate_limit(exc: RuntimeError) -> bool:
    msg = str(exc)
    return any(code in msg for code in _KIS_RATE_LIMIT_CODES)


async def with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    throttler: FixedIntervalThrottler,
    *,
    retries: int | None = None,
    base_backoff: float | None = None,
    max_backoff: float | None = None,
    idempotent: bool = True,
) -> T:
    """Rate limit 에러 시 지수 백오프로 재시도한다.

    Args:
        coro_factory: 매 시도마다 호출해 새 coroutine을 반환하는 팩토리.
        throttler: FixedIntervalThrottler 인스턴스.
        retries: 최대 재시도 횟수. None이면 throttler 설정 사용.
        base_backoff: 초기 백오프 시간 (초).
        max_backoff: 최대 백오프 시간 (초).
        idempotent: False이면 429/Rate Limit 시 재시도하지 않고 즉시 예외.
                    주문처럼 중복 실행 위험이 있는 요청에 사용.

    Returns:
        coro_factory() 실행 결과.

    Raises:
        RateLimitExceeded: 최대 재시도 횟수 초과 (idempotent=True 시).
                           또는 비멱등 요청에서 429/Rate Limit 발생 시.
        asyncio.CancelledError: 태스크 취소 시 즉시 전파.
        그 외 예외는 즉시 전파.
    """
    cfg = throttler.config
    max_retries = retries if retries is not None else cfg.max_retries
    base = base_backoff if base_backoff is not None else cfg.base_backoff_seconds
    max_b = max_backoff if max_backoff is not None else cfg.max_backoff_seconds

    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        await throttler.acquire()
        try:
            return await coro_factory()
        except asyncio.CancelledError:
            logger.debug("with_retry: 태스크 취소 (attempt=%d)", attempt)
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise
            if not idempotent:
                raise RateLimitExceeded(
                    f"비멱등 요청에서 429 발생 — 중복 실행 방지를 위해 재시도하지 않음: {exc}"
                ) from exc
            last_exc = exc
            backoff = min(base * (2**attempt), max_b)
            logger.warning(
                "KIS API 호출 빈도 초과(429), %.1fs 후 재시도 (%d/%d)",
                backoff,
                attempt + 1,
                max_retries,
            )
            await asyncio.sleep(backoff)
        except RuntimeError as exc:
            if not _is_kis_rate_limit(exc):
                raise
            if not idempotent:
                raise RateLimitExceeded(
                    f"비멱등 요청에서 KIS Rate Limit 발생 — 중복 실행 방지를 위해 재시도하지 않음: {exc}"
                ) from exc
            last_exc = exc
            backoff = min(base * (2**attempt), max_b)
            logger.warning(
                "KIS Rate Limit 에러, %.1fs 후 재시도 (%d/%d): %s",
                backoff,
                attempt + 1,
                max_retries,
                exc,
            )
            await asyncio.sleep(backoff)

    raise RateLimitExceeded(
        f"KIS API Rate Limit: {max_retries}회 재시도 후 실패. 마지막 에러: {last_exc}"
    )
