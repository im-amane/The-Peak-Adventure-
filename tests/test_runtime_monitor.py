import unittest

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

    def test_route_metrics_are_bounded_against_high_cardinality_paths(self):
        monitor = RuntimeMonitor(clock=lambda: 1000.0)
        for index in range(250):
            monitor.record_request(f"/random/{index}", 200, 0.001)
        snapshot = monitor.snapshot(3600)
        self.assertLessEqual(len(snapshot["routes"]), 100)
        self.assertEqual(snapshot["routes"]["/_other"]["requests"], 151)

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


if __name__ == "__main__":
    unittest.main()
