import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class FakeRequest:
    def __init__(self, payload):
        self.headers = {"X-Telegram-Init-Data": "signed-test-data"}
        self.content_length = len(json.dumps(payload).encode("utf-8"))
        self._payload = payload

    async def json(self):
        return self._payload


class MiniAppValidationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "validation-test.db")
        main.db = None
        await main.init_db()
        self.user = {"id": 987654990, "first_name": "ValidationHero"}
        await main.get_player(self.user["id"], self.user["first_name"])

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def _call(self, handler, payload):
        with patch("main.validate_init_data", return_value=self.user):
            return await handler(FakeRequest(payload))

    async def _assert_event(self, event_type):
        cur = await main.db.execute(
            "SELECT event_type FROM security_events WHERE user_id=? ORDER BY event_id DESC LIMIT 1",
            (self.user["id"],),
        )
        row = await cur.fetchone()
        self.assertEqual(row["event_type"], event_type)

    async def test_unhashable_battle_action_returns_400_and_is_logged(self):
        response = await self._call(main.api_action, {"action": []})
        self.assertEqual(response.status, 400)
        await self._assert_event("invalid_battle_action")

    async def test_unhashable_dungeon_action_returns_400_and_is_logged(self):
        response = await self._call(main.api_dungeon, {"action": []})
        self.assertEqual(response.status, 400)
        await self._assert_event("invalid_dungeon_action")

    async def test_unhashable_story_action_returns_400_and_is_logged(self):
        response = await self._call(main.api_story, {"action": []})
        self.assertEqual(response.status, 400)
        await self._assert_event("invalid_story_action")

    async def test_unhashable_world_action_returns_400_and_is_logged(self):
        response = await self._call(main.api_world, {"action": []})
        self.assertEqual(response.status, 400)
        await self._assert_event("invalid_world_action")

    async def test_invalid_monster_level_is_logged(self):
        response = await self._call(main.api_explore, {"monster_level": []})
        self.assertEqual(response.status, 400)
        await self._assert_event("invalid_monster_request")


if __name__ == "__main__":
    unittest.main()
