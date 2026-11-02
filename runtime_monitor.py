"""In-process runtime telemetry and alert-condition tracking.

Metrics are deliberately aggregate-only: no Telegram IDs, tokens, payloads, or
player content are retained in this module.
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Callable


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
        self.database_last_success_at = None
        self.database_last_error = None
        self.backup_last_attempt_at = None
        self.backup_last_success_at = None
        self.backup_last_error = None
        self.backup_last_path = None

    def record_request(self, path: str, status: int, duration_seconds: float) -> None:
        now = self._clock()
        route = path if isinstance(path, str) and path.startswith("/") else "/unknown"
        if route not in self.routes and len(self.routes) >= 100:
            route = "/_other"
        status_key = str(status)
        failed = status >= 400
        stats = self.routes[route]
        self.requests_total += 1
        self.failed_requests_total += int(failed)
        self.status_counts[status_key] += 1
        stats["requests"] += 1
        stats["failed"] += int(failed)
        stats["total_latency_ms"] += max(0.0, float(duration_seconds)) * 1000
        stats["last_request_at"] = now

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
        return {
            "database_unavailable": self.database_last_error is not None,
            "backup_unhealthy": backup_failed or backup_stale,
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
