import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main


class FakeRequest:
    def __init__(self, payload=None, path="/api/quest/claim", method="POST"):
        self.headers = {"X-Telegram-Init-Data": "signed-test-data"}
        self.content_length = len(json.dumps(payload or {}).encode("utf-8"))
        self.path = path
        self.method = method
        self._payload = payload or {}

    async def json(self):
        return self._payload


class MiniAppSecurityTelemetryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "security-api-test.db")
        main.db = None
        await main.init_db()

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def test_invalid_reward_claim_is_recorded(self):
        request = FakeRequest({"quest_id": 123})
        with patch("main.validate_init_data", return_value={"id": 99101, "first_name": "Tester"}):
            response = await main.api_quest_claim(request)

        self.assertEqual(response.status, 400)
        cur = await main.db.execute(
            "SELECT event_type,severity FROM security_events WHERE user_id=?",
            (99101,),
        )
        event = await cur.fetchone()
        self.assertEqual(event["event_type"], "invalid_reward_claim")
        self.assertEqual(event["severity"], 2)

    async def test_repeated_rate_limit_is_recorded_without_running_handler(self):
        request = FakeRequest(path="/api/action")
        async def handler(_request):
            raise AssertionError("Rate-limited requests must not reach the handler.")

        with patch("main.validate_init_data", return_value={"id": 99102, "first_name": "Tester"}), \
             patch.object(main.api_rate_limiter, "allow", return_value=(False, 12)):
            response = await main.miniapp_rate_limit(request, handler)

        self.assertEqual(response.status, 429)
        cur = await main.db.execute(
            "SELECT event_type,details FROM security_events WHERE user_id=?",
            (99102,),
        )
        event = await cur.fetchone()
        self.assertEqual(event["event_type"], "repeated_rate_limit")
        self.assertEqual(event["details"], "/api/action")


if __name__ == "__main__":
    unittest.main()
