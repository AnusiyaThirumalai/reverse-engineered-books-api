"""Tiny in-memory TTL cache.

Single-process only. A multi-instance deployment would use Redis (see
docs/limitations.md).
"""

from __future__ import annotations

import time
from typing import Callable, Generic, TypeVar

V = TypeVar("V")


class TTLCache(Generic[V]):
    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int = 512,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._data: dict[str, tuple[float, V]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> V | None:
        entry = self._data.get(key)
        if entry is not None:
            expires_at, value = entry
            if expires_at > self._clock():
                self.hits += 1
                return value
            del self._data[key]
        self.misses += 1
        return None

    def set(self, key: str, value: V) -> None:
        if self._ttl <= 0:  # TTL of 0 disables caching
            return
        if key not in self._data and len(self._data) >= self._max:
            self._evict()
        self._data[key] = (self._clock() + self._ttl, value)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    def _evict(self) -> None:
        now = self._clock()
        for k in [k for k, (exp, _) in self._data.items() if exp <= now]:
            del self._data[k]
        if len(self._data) >= self._max:  # still full: drop oldest insertion
            del self._data[next(iter(self._data))]
