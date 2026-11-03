import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class Request:
    def __init__(self, payload):
        self.headers = {}
        self.content_length = len(json.dumps(payload).encode("utf-8"))
        self.payload = payload

    async def json(self):
        return self.payload


class MiniAppDungeonWorldTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "dungeon-world-test.db")
        main.db = None
        await main.init_db()
        self.user = {"id": 987654991, "first_name": "DungeonWorldHero"}
        await main.get_player(self.user["id"], self.user["first_name"])
        await main.db.execute(
            "UPDATE players SET level=11,class_selected=1 WHERE user_id=?",
            (self.user["id"],),
        )
        await main.db.commit()

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def test_entering_higher_world_dungeon_also_travels_miniapp_player(self):
        request = Request({"action": "enter", "dungeon_id": 2})
        with patch("main.validate_init_data", return_value=self.user):
            response = await main.api_dungeon(request)

        self.assertEqual(response.status, 200)
        payload = json.loads(response.text)
        self.assertEqual(payload["state"]["world_id"], 2)
        self.assertEqual(payload["state"]["region"], "Ashen Desert")
        self.assertTrue(payload["state"]["worlds"][1]["current"])


if __name__ == "__main__":
    unittest.main()
