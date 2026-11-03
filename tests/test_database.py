import asyncio
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
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

    async def test_core_schema_initialization_is_idempotent_and_preserves_outer_transaction(self):
        await main.db.execute("BEGIN")
        await main.init_core_schema(main.db)
        self.assertTrue(main.db.in_transaction)
        await main.db.rollback()
        cursor = await main.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='players'"
        )
        self.assertIsNotNone(await cursor.fetchone())

    async def test_battle_hp_helpers_use_portable_case_updates(self):
        user_id = 987654399
        await main.get_player(user_id, "BattleSqlHero")
        await main.db.execute(
            "UPDATE players SET hp=95,max_hp=100,skill_cd=2 WHERE user_id=?",
            (user_id,),
        )
        await main._apply_battle_victory_heal(main.db, user_id)
        cursor = await main.db.execute(
            "SELECT hp,skill_cd FROM players WHERE user_id=?",
            (user_id,),
        )
        self.assertEqual(tuple(await cursor.fetchone()), (100, 1))

        await main._apply_battle_turn_state(main.db, user_id, 80)
        cursor = await main.db.execute(
            "SELECT hp,skill_cd FROM players WHERE user_id=?",
            (user_id,),
        )
        self.assertEqual(tuple(await cursor.fetchone()), (80, 0))

    async def test_dialect_specific_social_and_expiry_sql(self):
        self.assertIn("MIN(?,?)", main._friend_pair_lookup_sql(main.db))
        self.assertIn("MAX(?,?)", main._friend_pair_lookup_sql(main.db))
        self.assertIn("datetime(created_at)", main._stale_trade_expiry_sql(main.db))

    async def test_expire_stale_trades_uses_sqlite_datetime_semantics(self):
        await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,created_at)
               VALUES(0,101,102,'pending',datetime('now','-25 hours'))"""
        )
        await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,created_at)
               VALUES(0,103,104,'pending',datetime('now','-1 hour'))"""
        )
        await main.db.commit()
        expired = await main.expire_stale_trades()
        self.assertEqual(expired, 1)
        cur = await main.db.execute("SELECT status FROM trades ORDER BY trade_id")
        self.assertEqual([row["status"] for row in await cur.fetchall()], ["expired", "pending"])

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



class DatabaseBackendSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_configured_postgres_url_selects_postgres_connection(self):
        class FakePostgresConnection:
            dialect = "postgres"

            def __init__(self):
                self.closed = False

            async def close(self):
                self.closed = True

        connection = FakePostgresConnection()
        with patch.object(main, "DATABASE_URL", "postgresql://example.invalid/game"), \
             patch.object(main.PostgresConnection, "connect", new=AsyncMock(return_value=connection)) as connect, \
             patch.object(main, "init_game_schema", new=__import__("unittest").mock.AsyncMock()) as initialize:
            previous_db = main.db
            try:
                await main.init_db()
                connect.assert_awaited_once_with("postgresql://example.invalid/game")
                initialize.assert_awaited_once_with(connection)
                self.assertIs(main.db, connection)
                self.assertEqual(main.db.dialect, "postgres")
            finally:
                main.db = previous_db

    async def test_schema_failure_closes_connection_and_clears_global(self):
        class FakePostgresConnection:
            dialect = "postgres"

            def __init__(self):
                self.closed = False

            async def close(self):
                self.closed = True

        connection = FakePostgresConnection()
        with patch.object(main, "DATABASE_URL", "postgresql://example.invalid/game"), \
             patch.object(main.PostgresConnection, "connect", new=__import__("unittest").mock.AsyncMock(return_value=connection)), \
             patch.object(main, "init_game_schema", new=__import__("unittest").mock.AsyncMock(side_effect=RuntimeError("schema failed"))):
            previous_db = main.db
            try:
                with self.assertRaisesRegex(RuntimeError, "schema failed"):
                    await main.init_db()
                self.assertTrue(connection.closed)
                self.assertIsNone(main.db)
            finally:
                main.db = previous_db

    async def test_player_lock_releases_postgres_advisory_lock_after_handler_error(self):
        class FakePostgresConnection:
            dialect = "postgres"

            def __init__(self):
                self.acquired = []
                self.released = []

            async def acquire_player_lock(self, user_id):
                self.acquired.append(user_id)

            async def release_player_lock(self, user_id):
                self.released.append(user_id)

        connection = FakePostgresConnection()
        previous_db = main.db
        try:
            main.db = connection
            with self.assertRaisesRegex(RuntimeError, "handler failed"):
                async with main.player_lock(9_400_000_001):
                    self.assertEqual(connection.acquired, [9_400_000_001])
                    raise RuntimeError("handler failed")
            self.assertEqual(connection.released, [9_400_000_001])
        finally:
            main.db = previous_db

    async def test_postgres_backup_loop_never_runs_sqlite_file_backup(self):
        class FakePostgresConnection:
            dialect = "postgres"

        previous_db = main.db
        try:
            main.db = FakePostgresConnection()
            with patch.object(main, "create_backup") as create_backup, \
                 patch.object(main.runtime_monitor, "record_backup_failure") as record_failure, \
                 patch.object(main.asyncio, "sleep", side_effect=asyncio.CancelledError):
                with self.assertRaises(asyncio.CancelledError):
                    await main.database_backup_loop()
            create_backup.assert_not_called()
            record_failure.assert_called_once()
            self.assertIn("PostgreSQL", record_failure.call_args.args[0])
        finally:
            main.db = previous_db


    async def test_premium_handler_does_not_reacquire_middleware_database_lock(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(type="private"),
            text="/premium",
            from_user=SimpleNamespace(id=987654390),
            answer=AsyncMock(),
        )
        with patch.object(main, "get_premium_balance", new=AsyncMock(return_value=0)):
            async with main.db_lock:
                await asyncio.wait_for(main.premium_command(message), timeout=1)
        message.answer.assert_awaited_once()

    async def test_successful_payment_handler_does_not_reacquire_middleware_lock(self):
        package = main.get_premium_packages()["spark"]
        payment = SimpleNamespace(
            invoice_payload=main.make_invoice_payload("spark", 987654391),
            currency="XTR",
            total_amount=package["stars"],
            telegram_payment_charge_id="test-charge",
            provider_payment_charge_id="",
        )
        message = SimpleNamespace(
            successful_payment=payment,
            from_user=SimpleNamespace(id=987654391),
            answer=AsyncMock(),
        )
        with patch.object(main, "credit_premium_purchase", new=AsyncMock(return_value={
            "credited": True, "gems": package["gems"], "balance": package["gems"]
        })):
            async with main.db_lock:
                await asyncio.wait_for(main.premium_successful_payment(message), timeout=1)
        message.answer.assert_awaited_once()

    async def test_group_command_is_registered_instead_of_admin_helper(self):
        callbacks = [handler.callback for handler in main.dp.message.handlers]
        self.assertIn(main.group_command, callbacks)
        self.assertNotIn(main.verify_live_group_admin, callbacks)

    async def test_heal_debits_only_when_hp_is_not_full(self):
        user_id = 987654392
        await main.get_player(user_id, "HealRegression")
        await main.db.execute(
            "UPDATE players SET hp=40,max_hp=120,coins=50 WHERE user_id=?",
            (user_id,),
        )
        await main.db.commit()
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=user_id),
            answer=AsyncMock(),
        )
        await main.heal(message)
        cur = await main.db.execute(
            "SELECT hp,coins FROM players WHERE user_id=?", (user_id,)
        )
        self.assertEqual(tuple(await cur.fetchone()), (120, 20))
        await main.heal(message)
        cur = await main.db.execute(
            "SELECT hp,coins FROM players WHERE user_id=?", (user_id,)
        )
        self.assertEqual(tuple(await cur.fetchone()), (120, 20))
        self.assertEqual(message.answer.await_count, 2)


if __name__ == "__main__":
    unittest.main()
