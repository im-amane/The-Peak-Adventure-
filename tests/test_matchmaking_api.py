import unittest
from unittest.mock import patch

import aiosqlite

import main


class FakeRequest:
    def __init__(self, payload, content_length=32):
        self.headers = {"X-Telegram-Init-Data": "signed-test-data"}
        self.content_length = content_length
        self._payload = payload

    async def json(self):
        return self._payload


class MatchmakingApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous_db = main.db
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        main.db = self.db
        await main.init_game_schema(self.db)
        self.user_id = 9_200_000_001
        await main.get_player(self.user_id, "QueueApiHero")
        await self.db.execute(
            "UPDATE players SET class_selected=1 WHERE user_id=?",
            (self.user_id,),
        )
        await self.db.commit()
        self.user = {"id": self.user_id, "username": "QueueApiHero"}

    async def asyncTearDown(self):
        main.db = self.previous_db
        await self.db.close()

    async def call_api(self, payload):
        with patch("main.validate_init_data", return_value=self.user):
            return await main.api_matchmaking(FakeRequest(payload))

    async def test_join_and_cancel_are_authenticated_server_actions(self):
        joined = await self.call_api({"action": "join", "mode": "casual"})
        self.assertEqual(joined.status, 200)
        body = await joined.json()
        self.assertEqual(body["result"]["status"], "queued")
        self.assertEqual(body["state"]["matchmaking"]["status"], "queued")

        cancelled = await self.call_api({"action": "cancel"})
        self.assertEqual(cancelled.status, 200)
        body = await cancelled.json()
        self.assertTrue(body["result"]["cancelled"])
        self.assertEqual(body["state"]["matchmaking"]["status"], "cancelled")

    async def test_unselected_class_cannot_join(self):
        await self.db.execute(
            "UPDATE players SET class_selected=0 WHERE user_id=?",
            (self.user_id,),
        )
        await self.db.commit()
        response = await self.call_api({"action": "join", "mode": "ranked"})
        self.assertEqual(response.status, 409)

    async def test_unknown_fields_and_unhashable_actions_are_rejected(self):
        for payload in (
            {"action": "join", "mode": "casual", "user_id": 123},
            {"action": []},
            {"action": "join", "mode": []},
        ):
            with self.subTest(payload=payload):
                response = await self.call_api(payload)
                self.assertEqual(response.status, 400)


if __name__ == "__main__":
    unittest.main()
