"""Small in-memory sliding-window limiter for authenticated game API traffic."""
from __future__ import annotations

import time
from collections import deque


class SlidingWindowRateLimiter:
    """Track request timestamps per key without trusting client-supplied IP headers."""

    def __init__(self, window_seconds: int = 60, max_keys: int = 10000):
        if window_seconds < 1 or max_keys < 1:
            raise ValueError("window_seconds and max_keys must be positive")
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int, now: float | None = None) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds); limit is per key and window."""
        if not key or limit < 1:
            raise ValueError("key and limit must be valid")
        current = time.monotonic() if now is None else now
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
