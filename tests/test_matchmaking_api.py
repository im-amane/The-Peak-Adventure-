import json
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
        self.other_user_id = 9_200_000_002
        await main.get_player(self.other_user_id, "QueueApiOpponent")
        await self.db.execute(
            "UPDATE players SET class_selected=1 WHERE user_id=?",
            (self.other_user_id,),
        )
        await self.db.commit()
        self.other_user = {"id": self.other_user_id, "username": "QueueApiOpponent"}

    async def asyncTearDown(self):
        main.db = self.previous_db
        await self.db.close()

    async def call_api(self, payload):
        with patch("main.validate_init_data", return_value=self.user):
            return await main.api_matchmaking(FakeRequest(payload))

    async def test_join_and_cancel_are_authenticated_server_actions(self):
        joined = await self.call_api({"action": "join", "mode": "casual"})
        self.assertEqual(joined.status, 200)
        body = json.loads(joined.body.decode())
        self.assertEqual(body["result"]["status"], "queued")
        self.assertEqual(body["state"]["matchmaking"]["status"], "queued")

        cancelled = await self.call_api({"action": "cancel"})
        self.assertEqual(cancelled.status, 200)
        body = json.loads(cancelled.body.decode())
        self.assertTrue(body["result"]["cancelled"])
        self.assertEqual(body["state"]["matchmaking"]["status"], "cancelled")

    async def test_matched_players_can_take_authenticated_pvp_turns(self):
        first = await self.call_api({"action": "join", "mode": "casual"})
        self.assertEqual(first.status, 200)
        with patch("main.validate_init_data", return_value=self.other_user):
            second = await main.api_matchmaking(FakeRequest({"action": "join", "mode": "casual"}))
        self.assertEqual(second.status, 200)
        match_id = json.loads(second.body.decode())["result"]["match_id"]

        attack = await self.call_api({"action": "attack", "match_id": match_id})
        self.assertEqual(attack.status, 200)
        body = json.loads(attack.body.decode())
        self.assertEqual(body["result"]["status"], "active")
        self.assertEqual(body["state"]["matchmaking"]["battle"]["turn_user_id"], self.other_user_id)
        self.assertFalse(body["state"]["matchmaking"]["battle"]["is_my_turn"])

    async def test_pvp_action_rejects_unexpected_fields_and_non_participants(self):
        invalid = await self.call_api({"action": "attack", "match_id": 1, "damage": 99999})
        self.assertEqual(invalid.status, 400)
        await self.call_api({"action": "join", "mode": "casual"})
        with patch("main.validate_init_data", return_value=self.other_user):
            await main.api_matchmaking(FakeRequest({"action": "join", "mode": "casual"}))
        match_id = (await main.api_matchmaking(FakeRequest({"action": "status"}))).status
        self.assertEqual(match_id, 400)

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
