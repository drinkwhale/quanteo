"""
Rate Limit 스로틀러.

FixedIntervalThrottler: 호출 간격을 균등 분산 (고정 간격 직렬화).
  호출마다 1/calls_per_second 간격을 강제한다.
  asyncio.Lock으로 동시 호출을 직렬화해 간격이 겹치는 걸 방지한다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ThrottlerConfig:
    """스로틀러 파라미터."""

    calls_per_second: float = 15.0
    max_retries: int = 5
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0


class RateLimitExceeded(Exception):
    """최대 재시도 횟수를 초과했을 때."""


class FixedIntervalThrottler:
    """고정 간격 Rate Limit 스로틀러.

    호출마다 최소 간격(1 / calls_per_second)을 강제한다.
    asyncio.Lock으로 동시 호출을 직렬화해 초과 호출을 방지한다.
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
