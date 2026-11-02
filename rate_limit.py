"""Small in-memory sliding-window limiter for authenticated game API traffic."""
from __future__ import annotations

import time
import math
from collections import deque


class SlidingWindowRateLimiter:
    """Track request timestamps per key without trusting client-supplied IP headers."""

    def __init__(self, window_seconds: int = 60, max_keys: int = 10000):
        if (
            not isinstance(window_seconds, int) or isinstance(window_seconds, bool) or window_seconds < 1
            or not isinstance(max_keys, int) or isinstance(max_keys, bool) or max_keys < 1
        ):
            raise ValueError("window_seconds and max_keys must be positive integers")
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int, now: float | None = None) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds); limit is per key and window."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        current = time.monotonic() if now is None else now
        if isinstance(current, bool) or not isinstance(current, (int, float)) or not math.isfinite(current):
            raise ValueError("now must be a finite monotonic timestamp")
        events = self._events.setdefault(key, deque())
        cutoff = current - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            return False, max(1, int(self.window_seconds - (current - events[0])) + 1)
        events.append(current)
        if len(self._events) > self.max_keys:
            stale = [entry for entry, timestamps in self._events.items()
                     if not timestamps or timestamps[-1] <= cutoff]
            for entry in stale:
                self._events.pop(entry, None)
            while len(self._events) > self.max_keys:
                oldest = min(
                    self._events,
                    key=lambda entry: self._events[entry][-1] if self._events[entry] else float("-inf"),
                )
                self._events.pop(oldest, None)
        return True, 0
