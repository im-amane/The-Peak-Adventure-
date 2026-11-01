import tempfile
import unittest
from pathlib import Path

import main
from world_system import travel_to_world


class MiniAppWorldIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "world-test.db")
        main.db = None
        await main.init_db()

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def test_miniapp_state_tracks_selected_world_and_landmark(self):
        user = {"id": 987654326, "first_name": "WorldHero"}
        player = await main.get_player(user["id"], user["first_name"])
        state = await main.miniapp_state(user)
        self.assertEqual(state["world_id"], 1)
        self.assertEqual(state["region"], "Whispering Meadow")
        self.assertEqual(len(state["worlds"]), 10)
        self.assertTrue(state["worlds"][0]["current"])
        self.assertFalse(state["worlds"][1]["unlocked"])
        self.assertEqual(state["landmark"]["landmark"], "Whispering Tree")

        await main.db.execute("UPDATE players SET level=11 WHERE user_id=?", (user["id"],))
        await main.db.commit()
        await travel_to_world(main.db, user["id"], 11, 2)
        state = await main.miniapp_state(user)
        self.assertEqual(state["world_id"], 2)
        self.assertEqual(state["region"], "Ashen Desert")
        self.assertTrue(state["worlds"][1]["current"])
        self.assertTrue(state["worlds"][1]["unlocked"])
        self.assertEqual(state["landmark"]["landmark"], "Buried Sun Dial")


if __name__ == "__main__":
    unittest.main()
