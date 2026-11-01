import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from party_system import create_party


class FakeRequest:
    def __init__(self, payload):
        self.headers = {"X-Telegram-Init-Data": "signed-test-data"}
        self.content_length = len(json.dumps(payload).encode("utf-8"))
        self._payload = payload

    async def json(self):
        return self._payload


class MiniAppSocialApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "social-api-test.db")
        main.db = None
        await main.init_db()

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def test_party_invite_does_not_create_unknown_player(self):
        leader_id = 987654901
        unknown_target_id = 987654902
        await main.get_player(leader_id, "PartyLeader")
        await main.db.execute(
            "UPDATE players SET class_selected=1, hero_class='Knight' WHERE user_id=?",
            (leader_id,),
        )
        await main.db.commit()
        await create_party(main.db, leader_id)

        request = FakeRequest({
            "action": "party_invite",
            "target_id": unknown_target_id,
        })
        with patch("main.validate_init_data", return_value={
            "id": leader_id,
            "first_name": "PartyLeader",
        }):
            response = await main.api_social(request)

        self.assertEqual(response.status, 409)
        self.assertIn("has not joined", json.loads(response.text)["error"])
        cur = await main.db.execute(
            "SELECT 1 FROM players WHERE user_id=?",
            (unknown_target_id,),
        )
        self.assertIsNone(await cur.fetchone())


if __name__ == "__main__":
    unittest.main()
