"""Inbound sliding-window rate limiter (in-memory, per client key).

Purpose: stop one consumer from turning this service into a request amplifier
against the target website. Single-process only; production would use a shared
store (Redis) or an API gateway.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> tuple[bool, float]:
        """Record a request. Returns ``(allowed, retry_after_seconds)``."""
        now = self._clock()
        if len(self._hits) > self._max_keys:
            self._prune(now)
        window = self._hits.setdefault(key, deque())
        while window and window[0] <= now - self._window:
            window.popleft()
        if len(window) >= self._max:
            return False, max(0.0, window[0] + self._window - now)
        window.append(now)
        return True, 0.0

    def _prune(self, now: float) -> None:
        for k in [k for k, w in self._hits.items() if not w or w[-1] <= now - self._window]:
            del self._hits[k]
