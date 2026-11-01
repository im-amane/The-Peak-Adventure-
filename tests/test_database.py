import tempfile
import unittest
from pathlib import Path

import main


class DatabaseSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        main.DB_PATH = str(Path(self.temp_dir.name) / "test-adventure.db")
        main.db = None
        await main.init_db()

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
            main.db = None
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def test_player_defaults_and_profile(self):
        player = await main.get_player(987654321, "TestHero")
        self.assertEqual(player["level"], 1)
        self.assertEqual(player["hp"], player["max_hp"])
        self.assertEqual(player["class_selected"], 0)
        self.assertEqual(player["weapon"], "Rusty Sword")
        profile = await main.player_text(player)
        self.assertIn("TestHero", profile)
        self.assertIn("Guild: None", profile)

    async def test_daily_reward_has_rolling_cooldown(self):
        await main.get_player(987654322, "DailyHero")
        self.assertTrue(await main.claim_daily_reward(987654322))
        self.assertFalse(await main.claim_daily_reward(987654322))

    async def test_new_gameplay_tables_and_elite_battle_flag_exist(self):
        for table in ("player_stamina", "player_mana", "player_weekly_quests", "player_reports", "player_bans", "player_daily_missions", "roaming_events", "roaming_event_participants"):
            cur = await main.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            self.assertIsNotNone(await cur.fetchone(), table)
        cur = await main.db.execute("PRAGMA table_info(battles)")
        columns = {row["name"] for row in await cur.fetchall()}
        self.assertIn("is_elite", columns)

    async def test_miniapp_state_exposes_unlocked_dungeon_choices(self):
        user = {"id": 987654323, "first_name": "DungeonHero"}
        state = await main.miniapp_state(user)
        self.assertEqual(len(state["dungeons"]), 10)
        self.assertTrue(state["dungeons"][0]["unlocked"])
        self.assertFalse(state["dungeons"][1]["unlocked"])
        self.assertFalse(state["dungeons"][0]["claimed"])
        self.assertIsNone(state["dungeon"])
        self.assertEqual(len(state["daily_missions"]), 3)
        self.assertTrue(all(item["progress"] == 0 for item in state["daily_missions"]))

    async def test_multiplayer_tables_exist(self):
        for table in ("duels", "guilds", "guild_members", "trades", "quest_progress", "achievement_progress"):
            cur = await main.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            self.assertIsNotNone(await cur.fetchone(), table)


if __name__ == "__main__":
    unittest.main()
