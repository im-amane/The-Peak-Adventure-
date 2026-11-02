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
            {"database_unavailable": True, "backup_unhealthy": True},
        )

        now[0] += 10
        monitor.record_database_probe(True)
        monitor.record_backup_success("/safe/backups/snapshot.db")
        self.assertEqual(
            monitor.alert_conditions(3600),
            {"database_unavailable": False, "backup_unhealthy": False},
        )
        snapshot = monitor.snapshot(3600)
        self.assertIsNone(snapshot["database"]["last_error"])
        self.assertIsNone(snapshot["backup"]["last_error"])
        self.assertEqual(snapshot["backup"]["last_path"], "/safe/backups/snapshot.db")

    def test_missing_or_stale_backup_is_reported(self):
        now = [1000.0]
        monitor = RuntimeMonitor(clock=lambda: now[0])
        self.assertFalse(monitor.alert_conditions(60)["backup_unhealthy"])
        now[0] += 121
        self.assertTrue(monitor.alert_conditions(60)["backup_unhealthy"])
        monitor.record_backup_success("/safe/backups/snapshot.db")
        now[0] += 121
        self.assertTrue(monitor.alert_conditions(60)["backup_unhealthy"])


if __name__ == "__main__":
    unittest.main()
