"""In-process runtime telemetry and alert-condition tracking.

Metrics are deliberately aggregate-only: no Telegram IDs, tokens, payloads, or
player content are retained in this module.
"""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict, deque
from typing import Callable

RECENT_WINDOW_SECONDS = 300
MIN_RECENT_REQUESTS = 20
SERVER_ERROR_RATE_THRESHOLD = 0.20
P95_LATENCY_THRESHOLD_MS = 2_000


class RuntimeMonitor:
    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self.started_at = clock()
        self.requests_total = 0
        self.failed_requests_total = 0
        self.status_counts: Counter[str] = Counter()
        self.routes: dict[str, dict] = defaultdict(
            lambda: {"requests": 0, "failed": 0, "total_latency_ms": 0.0, "last_request_at": None}
        )
        # Store only timestamp, HTTP status and duration. Never retain request
        # paths, user IDs, headers, tokens or payloads in the rolling window.
        self._recent_requests = deque()
        self.database_last_success_at = None
        self.database_last_error = None
        self.backup_last_attempt_at = None
        self.backup_last_success_at = None
        self.backup_last_error = None
        self.backup_last_path = None

    def record_request(self, path: str, status: int, duration_seconds: float) -> None:
        now = self._clock()
        route = path if isinstance(path, str) and path.startswith("/") else "/unknown"
        if route not in self.routes and len(self.routes) >= 99:
            route = "/_other"
        status_key = str(status)
        failed = status >= 400
        latency_ms = max(0.0, float(duration_seconds)) * 1000
        stats = self.routes[route]
        self.requests_total += 1
        self.failed_requests_total += int(failed)
        self.status_counts[status_key] += 1
        stats["requests"] += 1
        stats["failed"] += int(failed)
        stats["total_latency_ms"] += latency_ms
        stats["last_request_at"] = now
        self._recent_requests.append((now, int(status), latency_ms))
        self._prune_recent_requests(now)

    def _prune_recent_requests(self, now: float) -> None:
        cutoff = now - RECENT_WINDOW_SECONDS
        while self._recent_requests and self._recent_requests[0][0] < cutoff:
            self._recent_requests.popleft()

    def _recent_request_summary(self, now: float) -> dict:
        self._prune_recent_requests(now)
        entries = list(self._recent_requests)
        total = len(entries)
        server_errors = sum(1 for _, status, _ in entries if status >= 500)
        latencies = sorted(duration for _, _, duration in entries)
        p95 = (
            round(latencies[max(0, math.ceil(total * 0.95) - 1)], 2)
            if total else 0.0
        )
        return {
            "window_seconds": RECENT_WINDOW_SECONDS,
            "requests": total,
            "server_errors": server_errors,
            "server_error_rate": round(server_errors / total, 4) if total else 0.0,
            "p95_latency_ms": p95,
        }

    def record_database_probe(self, healthy: bool, error: str | None = None) -> None:
        if healthy:
            self.database_last_success_at = self._clock()
            self.database_last_error = None
        else:
            self.database_last_error = (str(error or "Database probe failed"))[:240]

    def record_backup_success(self, path: str) -> None:
        now = self._clock()
        self.backup_last_attempt_at = now
        self.backup_last_success_at = now
        self.backup_last_error = None
        self.backup_last_path = str(path)[:500]

    def record_backup_failure(self, error: str) -> None:
        self.backup_last_attempt_at = self._clock()
        self.backup_last_error = str(error or "Backup failed")[:240]

    def alert_conditions(self, backup_interval_seconds: int, now: float | None = None) -> dict[str, bool]:
        current = self._clock() if now is None else now
        backup_reference = self.backup_last_success_at or self.started_at
        backup_stale = current - backup_reference > max(60, backup_interval_seconds * 2)
        backup_failed = self.backup_last_error is not None
        recent = self._recent_request_summary(current)
        enough_traffic = recent["requests"] >= MIN_RECENT_REQUESTS
        return {
            "database_unavailable": self.database_last_error is not None,
            "backup_unhealthy": backup_failed or backup_stale,
            "http_error_rate": (
                enough_traffic
                and recent["server_error_rate"] >= SERVER_ERROR_RATE_THRESHOLD
            ),
            "slow_responses": (
                enough_traffic
                and recent["p95_latency_ms"] >= P95_LATENCY_THRESHOLD_MS
            ),
        }

    def snapshot(self, backup_interval_seconds: int, now: float | None = None) -> dict:
        current = self._clock() if now is None else now
        backup_age = (
            None if self.backup_last_success_at is None
            else max(0, int(current - self.backup_last_success_at))
        )
        routes = {
            path: {
                **stats,
                "average_latency_ms": round(
                    stats["total_latency_ms"] / stats["requests"], 2
                ) if stats["requests"] else 0.0,
            }
            for path, stats in sorted(self.routes.items())
        }
        return {
            "uptime_seconds": max(0, int(current - self.started_at)),
            "requests_total": self.requests_total,
            "failed_requests_total": self.failed_requests_total,
            "status_counts": dict(self.status_counts),
            "recent_http": self._recent_request_summary(current),
            "routes": routes,
            "database": {
                "last_success_at": self.database_last_success_at,
                "last_error": self.database_last_error,
            },
            "backup": {
                "last_attempt_at": self.backup_last_attempt_at,
                "last_success_at": self.backup_last_success_at,
                "age_seconds": backup_age,
                "last_error": self.backup_last_error,
                "last_path": self.backup_last_path,
                "stale_after_seconds": max(60, backup_interval_seconds * 2),
            },
            "alerts": self.alert_conditions(backup_interval_seconds, current),
        }
