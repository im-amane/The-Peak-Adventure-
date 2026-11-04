"""Regression tests for operations alert transitions and delivery retries."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import main


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
