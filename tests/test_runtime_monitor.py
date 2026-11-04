import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import main
from runtime_monitor import RuntimeMonitor


class RuntimeMonitorTests(unittest.TestCase):
    def test_aggregate_request_metrics_do_not_retain_request_identity(self):
        now = [1000.0]
        monitor = RuntimeMonitor(clock=lambda: now[0])
        monitor.record_request("/api/action", 200, 0.025)
        now[0] += 1
        monitor.record_request("/api/action", 409, 0.075)
        snapshot = monitor.snapshot(3600)

        self.assertEqual(snapshot["requests_total"], 2)
        self.assertEqual(snapshot["failed_requests_total"], 1)
        self.assertEqual(snapshot["status_counts"], {"200": 1, "409": 1})
        self.assertEqual(snapshot["routes"]["/api/action"]["average_latency_ms"], 50.0)
        self.assertNotIn("user_id", str(snapshot))
        self.assertNotIn("token", str(snapshot))

    def test_database_and_backup_alerts_clear_after_recovery(self):
        now = [1000.0]
        monitor = RuntimeMonitor(clock=lambda: now[0])
        monitor.record_database_probe(False, "connection refused")
        monitor.record_backup_failure("disk full")
        self.assertEqual(
            monitor.alert_conditions(3600),
            {"database_unavailable": True, "backup_unhealthy": True, "http_error_rate": False, "slow_responses": False},
        )

        now[0] += 10
        monitor.record_database_probe(True)
        monitor.record_backup_success("/safe/backups/snapshot.db")
        self.assertEqual(
            monitor.alert_conditions(3600),
            {"database_unavailable": False, "backup_unhealthy": False, "http_error_rate": False, "slow_responses": False},
        )
        snapshot = monitor.snapshot(3600)
        self.assertIsNone(snapshot["database"]["last_error"])
        self.assertIsNone(snapshot["backup"]["last_error"])
        self.assertEqual(snapshot["backup"]["last_path"], "/safe/backups/snapshot.db")

    def test_route_metrics_normalize_dynamic_ids_before_aggregation(self):
        monitor = RuntimeMonitor(clock=lambda: 1000.0)
        for user_id in range(250):
            monitor.record_request(f"/api/player/{user_id}/profile", 200, 0.001)
        snapshot = monitor.snapshot(3600)
        self.assertEqual(len(snapshot["routes"]), 1)
        self.assertEqual(snapshot["routes"]["/api/player/{id}/profile"]["requests"], 250)
        self.assertNotIn("249", str(snapshot["routes"]))

    def test_route_metrics_hide_telegram_ids_and_opaque_identifiers(self):
        monitor = RuntimeMonitor(clock=lambda: 1000.0)
        monitor.record_request("/api/player/987654321012345678/profile", 200, 0.01)
        monitor.record_request("/api/session/0123456789abcdef0123456789abcdef", 200, 0.01)
        routes = monitor.snapshot(3600)["routes"]
        self.assertIn("/api/player/{id}/profile", routes)
        self.assertIn("/api/session/{id}", routes)
        self.assertNotIn("987654321012345678", str(routes))
        self.assertNotIn("0123456789abcdef", str(routes))

    def test_database_and_backup_errors_redact_credentials_before_snapshot(self):
        monitor = RuntimeMonitor(clock=lambda: 1000.0)
        monitor.record_database_probe(
            False,
            "connect failed postgresql://admin:super-secret@db.internal/game?token=abc123",
        )
        monitor.record_backup_failure("upload failed password=hunter2 Bearer eyJhbGciOiJIUzI1NiJ9")
        snapshot = str(monitor.snapshot(3600))
        self.assertIn("admin:[redacted]@db.internal", snapshot)
        self.assertIn("token=[redacted]", snapshot)
        self.assertIn("password=[redacted]", snapshot)
        self.assertIn("Bearer [redacted]", snapshot)
        for secret in ("super-secret", "abc123", "hunter2", "eyJhbGciOiJIUzI1NiJ9"):
            self.assertNotIn(secret, snapshot)

    def test_missing_or_stale_backup_is_reported(self):
        now = [1000.0]
        monitor = RuntimeMonitor(clock=lambda: now[0])
        self.assertFalse(monitor.alert_conditions(60)["backup_unhealthy"])
        now[0] += 121
        self.assertTrue(monitor.alert_conditions(60)["backup_unhealthy"])
        monitor.record_backup_success("/safe/backups/snapshot.db")
        now[0] += 121
        self.assertTrue(monitor.alert_conditions(60)["backup_unhealthy"])

    def test_http_error_rate_alert_requires_minimum_traffic_and_recovers(self):
        now = [1000.0]
        monitor = RuntimeMonitor(clock=lambda: now[0])
        for index in range(20):
            monitor.record_request("/api/action", 500 if index < 5 else 200, 0.02)
        snapshot = monitor.snapshot(3600)
        self.assertTrue(snapshot["alerts"]["http_error_rate"])
        self.assertEqual(snapshot["recent_http"]["server_errors"], 5)
        self.assertEqual(snapshot["recent_http"]["server_error_rate"], 0.25)
        now[0] += 301
        for _ in range(20):
            monitor.record_request("/api/action", 200, 0.02)
        self.assertFalse(monitor.alert_conditions(3600)["http_error_rate"])

    def test_slow_response_alert_uses_recent_p95_latency(self):
        now = [2000.0]
        monitor = RuntimeMonitor(clock=lambda: now[0])
        for _ in range(20):
            monitor.record_request("/api/state", 200, 2.5)
        snapshot = monitor.snapshot(3600)
        self.assertTrue(snapshot["alerts"]["slow_responses"])
        self.assertEqual(snapshot["recent_http"]["p95_latency_ms"], 2500.0)
        now[0] += 301
        monitor.record_request("/api/state", 200, 0.01)
        self.assertFalse(monitor.alert_conditions(3600)["slow_responses"])

    def test_rolling_http_window_expires_old_samples(self):
        now = [3000.0]
        monitor = RuntimeMonitor(clock=lambda: now[0])
        for _ in range(20):
            monitor.record_request("/api/action", 503, 0.01)
        now[0] += 301
        snapshot = monitor.snapshot(3600)
        self.assertEqual(snapshot["recent_http"]["requests"], 0)
        self.assertEqual(snapshot["recent_http"]["server_error_rate"], 0.0)


class _SequenceMonitor:
    def __init__(self, conditions):
        self._conditions = iter(conditions)

    def alert_conditions(self, _backup_interval):
        return next(self._conditions)


class _FlakyBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, admin_id, message):
        self.messages.append((admin_id, message))
        if len(self.messages) == 1:
            raise RuntimeError("temporary Telegram delivery failure")


class OperationsAlertLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_alerts_retry_failed_delivery_and_report_recovery(self):
        alert_names = (
            "database_unavailable",
            "backup_unhealthy",
            "http_error_rate",
            "slow_responses",
        )
        unhealthy = {name: True for name in alert_names}
        healthy = {name: False for name in alert_names}
        monitor = _SequenceMonitor((unhealthy, unhealthy, healthy))
        bot = _FlakyBot()
        sleep_calls = 0

        async def stop_after_three_cycles(_seconds):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls == 3:
                raise asyncio.CancelledError()

        with (
            patch.object(main, "runtime_monitor", monitor),
            patch.object(main, "ADMIN_IDS", [123456]),
            patch.object(main, "database_healthcheck", new_callable=AsyncMock),
            patch.object(main.asyncio, "sleep", side_effect=stop_after_three_cycles),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await main.operations_alert_loop(bot)

        # First alert delivery fails, is retried on cycle two, and then gets a
        # recovery notification on cycle three. The other three alerts follow
        # the same transition path without duplicate active notifications.
        self.assertEqual(len(bot.messages), 9)
        self.assertEqual(bot.messages[0][1], bot.messages[4][1])
        self.assertIn("unavailable", bot.messages[0][1])
        recovery_messages = [message for _, message in bot.messages[5:]]
        self.assertEqual(len(recovery_messages), 4)
        self.assertTrue(all(message.startswith("✅") for message in recovery_messages))
        self.assertTrue(any("database connection recovered" in message for message in recovery_messages))
        self.assertTrue(any("backup recovered" in message for message in recovery_messages))
        self.assertTrue(any("server-error rate recovered" in message for message in recovery_messages))
        self.assertTrue(any("response latency" in message for message in recovery_messages))

if __name__ == "__main__":
    unittest.main()
