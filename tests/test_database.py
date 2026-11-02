import tempfile
import unittest
from unittest.mock import patch
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

    async def test_generated_id_helper_uses_sqlite_lastrowid(self):
        await main.db.execute("CREATE TABLE generated_id_probe(id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT)")
        generated_id = await main._insert_generated_id(
            main.db,
            "INSERT INTO generated_id_probe(value) VALUES (?)",
            ("sqlite",),
            "trade_id",
        )
        self.assertEqual(generated_id, 1)

    async def test_generated_id_helper_uses_postgres_returning(self):
        class Cursor:
            async def fetchone(self):
                return {"duel_id": 73}

        class PostgresStub:
            dialect = "postgres"

            async def execute(self, sql, parameters):
                self.sql = sql
                self.parameters = parameters
                return Cursor()

        connection = PostgresStub()
        generated_id = await main._insert_generated_id(
            connection,
            "INSERT INTO duels(chat_id) VALUES (?)",
            (123,),
            "duel_id",
        )
        self.assertEqual(generated_id, 73)
        self.assertEqual(
            connection.sql,
            "INSERT INTO duels(chat_id) VALUES (?) RETURNING duel_id",
        )
        self.assertEqual(connection.parameters, (123,))

    async def test_generated_id_helper_rejects_unapproved_identifier(self):
        with self.assertRaisesRegex(ValueError, "Unsupported generated ID column"):
            await main._insert_generated_id(main.db, "INSERT INTO duels(chat_id) VALUES (?)", (1,), "chat_id")

    async def test_database_healthcheck_detects_unavailable_database(self):
        self.assertTrue(await main.database_healthcheck())
        active_db = main.db
        main.db = None
        try:
            self.assertFalse(await main.database_healthcheck())
        finally:
            main.db = active_db

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

    async def test_get_player_preserves_caller_transaction(self):
        await main.db.execute("BEGIN")
        await main.get_player(987654329, "TransactionHero")
        self.assertTrue(main.db.in_transaction)
        await main.db.rollback()
        cur = await main.db.execute("SELECT 1 FROM players WHERE user_id=?", (987654329,))
        self.assertIsNone(await cur.fetchone())
        cur = await main.db.execute("SELECT 1 FROM player_presence WHERE user_id=?", (987654329,))
        self.assertIsNone(await cur.fetchone())

    async def test_get_player_failure_rolls_back_only_its_savepoint(self):
        await main.db.execute("BEGIN")
        with patch("main.touch_presence", side_effect=RuntimeError("presence write failed")):
            with self.assertRaisesRegex(RuntimeError, "presence write failed"):
                await main.get_player(987654330, "RollbackHero")
        self.assertTrue(main.db.in_transaction)
        cur = await main.db.execute("SELECT 1 FROM players WHERE user_id=?", (987654330,))
        self.assertIsNone(await cur.fetchone())
        await main.db.rollback()

    async def test_new_gameplay_tables_and_elite_battle_flag_exist(self):
        for table in ("player_stamina", "player_mana", "player_weekly_quests", "player_reports", "player_bans", "player_daily_missions", "roaming_events", "roaming_event_participants", "player_monster_mastery", "dungeon_runs", "dungeon_rewards", "security_events", "premium_wallets", "premium_transactions", "premium_shop_purchases", "player_xp_boosts"):
            cur = await main.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            self.assertIsNotNone(await cur.fetchone(), table)
        cur = await main.db.execute("PRAGMA table_info(battles)")
        columns = {row["name"] for row in await cur.fetchall()}
        self.assertIn("is_elite", columns)
        self.assertIn("is_evolved", columns)

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
        self.assertEqual(state["premium_gems"], 0)
        self.assertEqual(state["social"]["friend_requests"], [])
        self.assertEqual(state["social"]["party_invites"], [])
        self.assertEqual(state["social"]["pending_guild_invites"], [])

    async def test_miniapp_state_exposes_weekly_missions(self):
        user = {"id": 987654324, "first_name": "QuestHero"}
        state = await main.miniapp_state(user)
        self.assertGreaterEqual(len(state["weekly_quests"]), 1)
        self.assertEqual(len(state["daily_missions"]), 3)
        self.assertTrue(all("claimed" in item for item in state["daily_missions"]))

    async def test_multiplayer_tables_exist(self):
        for table in ("duels", "guilds", "guild_members", "trades", "quest_progress", "achievement_progress"):
            cur = await main.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            self.assertIsNotNone(await cur.fetchone(), table)


if __name__ == "__main__":
    unittest.main()
