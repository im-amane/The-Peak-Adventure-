import ast
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import main

from game_rules import calculate_enemy_damage


class CombatRuleTests(unittest.IsolatedAsyncioTestCase):
    def test_telegram_battle_uses_synchronous_monster_builder_correctly(self):
        source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        handler = next(
            node for node in module.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_battle_action_unlocked"
        )
        assignment = next(
            node for node in ast.walk(handler)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "m" for target in node.targets)
        )
        self.assertIsInstance(assignment.value, ast.Call)
        self.assertIsInstance(assignment.value.func, ast.Name)
        self.assertEqual(assignment.value.func.id, "build_battle_monster")
        self.assertEqual(len(assignment.value.args), 1)
        self.assertIsInstance(assignment.value.args[0], ast.Name)
        self.assertEqual(assignment.value.args[0].id, "b")


    async def test_telegram_attack_executes_and_advances_the_active_battle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_path, previous_db = main.DB_PATH, main.db
            main.DB_PATH = str(Path(temp_dir) / "combat-test.db")
            main.db = None
            try:
                await main.init_db()
                user_id = 987654321
                await main.get_player(user_id, "CombatTester")
                await main.db.execute(
                    "UPDATE players SET class_selected=1,hp=500,max_hp=500,armor_defense=1000 WHERE user_id=?",
                    (user_id,),
                )
                await main.db.execute(
                    """INSERT INTO battles(user_id,monster_level,monster_hp,turn_count,is_elite,is_evolved)
                       VALUES(?,1,77,0,0,0)""",
                    (user_id,),
                )
                await main.db.commit()

                call = SimpleNamespace(
                    from_user=SimpleNamespace(id=user_id, username="CombatTester"),
                    data="battle:attack",
                    answer=AsyncMock(),
                    message=SimpleNamespace(edit_text=AsyncMock()),
                )
                await main._battle_action_unlocked(call)

                cursor = await main.db.execute(
                    "SELECT turn_count,monster_hp FROM battles WHERE user_id=?",
                    (user_id,),
                )
                battle = await cursor.fetchone()
                self.assertEqual(battle["turn_count"], 1)
                self.assertLess(battle["monster_hp"], 77)
                player = await main.get_player(user_id)
                self.assertLess(player["hp"], 500)
                call.answer.assert_awaited_once()
                call.message.edit_text.assert_awaited_once()
            finally:
                if main.db is not None:
                    await main.db.close()
                main.db = previous_db
                main.DB_PATH = previous_path

    async def test_telegram_lethal_attack_keeps_turn_and_mana_atomic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_path, previous_db = main.DB_PATH, main.db
            main.DB_PATH = str(Path(temp_dir) / "combat-rollback-test.db")
            main.db = None
            try:
                await main.init_db()
                user_id = 987654322
                await main.get_player(user_id, "CombatRollbackTester")
                await main.db.execute(
                    "UPDATE players SET class_selected=1,hp=100,max_hp=100 WHERE user_id=?",
                    (user_id,),
                )
                await main.db.execute(
                    """INSERT INTO battles(user_id,monster_level,monster_hp,turn_count,is_elite,is_evolved)
                       VALUES(?,1,1,0,0,0)""",
                    (user_id,),
                )
                await main.db.commit()
                call = SimpleNamespace(
                    from_user=SimpleNamespace(id=user_id, username="CombatRollbackTester"),
                    data="battle:attack",
                    answer=AsyncMock(),
                    message=SimpleNamespace(edit_text=AsyncMock()),
                )
                async def handler(event, data):
                    await main._battle_action_unlocked(event)

                with patch(
                    "main.finish_battle",
                    side_effect=RuntimeError("simulated Telegram reward failure"),
                ):
                    with self.assertRaisesRegex(RuntimeError,"simulated Telegram reward failure"):
                        await main.DatabaseLockMiddleware()(handler,call,{})
                self.assertFalse(main.db.in_transaction)
                cur=await main.db.execute(
                    "SELECT monster_hp,turn_count FROM battles WHERE user_id=?",(user_id,)
                )
                battle=await cur.fetchone()
                self.assertEqual((battle["monster_hp"],battle["turn_count"]),(1,0))
                player=await main.get_player(user_id)
                self.assertEqual(player["hp"],100)
                cur=await main.db.execute("SELECT 1 FROM player_mana WHERE user_id=?",(user_id,))
                self.assertIsNone(await cur.fetchone())
            finally:
                if main.db is not None:
                    await main.db.close()
                main.db = previous_db
                main.DB_PATH = previous_path

    def test_player_defence_reduces_monster_damage(self):
        base = calculate_enemy_damage(60, 5, 0, 0, 0, 0)
        guarded = calculate_enemy_damage(60, 5, 12, 8, 0, 0)
        self.assertEqual(base, 50)
        self.assertEqual(guarded, 30)

    def test_fury_and_special_attack_multiply_damage(self):
        normal = calculate_enemy_damage(50, 1, 0, 0, 0, 0)
        boosted = calculate_enemy_damage(50, 1, 0, 0, 0, 0, fury=True, special=True)
        self.assertEqual(normal, 48)
        self.assertEqual(boosted, 90)

    def test_damage_has_a_minimum_floor(self):
        damage = calculate_enemy_damage(1, 100, 100, 100, 0, -10)
        self.assertEqual(damage, 3)



    async def test_stale_battle_finalizer_does_not_award_duplicate_rewards(self):
        class FakeCursor:
            def __init__(self, row=None, rowcount=0):
                self.row = row
                self.rowcount = rowcount

            async def fetchone(self):
                return self.row

        fake_db = SimpleNamespace(
            execute=AsyncMock(side_effect=[
                FakeCursor(row={"user_id": 987654324}),
                FakeCursor(rowcount=0),
            ]),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )
        previous_db = main.db
        main.db = fake_db
        try:
            with patch("main.build_battle_monster", return_value={"name": "Stale Monster"}), \
                 patch("main.consume_xp_boost", new=AsyncMock()) as consume_boost:
                result = await main.finish_battle(987654324, True)
            self.assertIsNone(result)
            fake_db.rollback.assert_awaited_once()
            fake_db.commit.assert_not_awaited()
            consume_boost.assert_not_awaited()
            self.assertEqual(fake_db.execute.await_count, 2)
        finally:
            main.db = previous_db

    async def test_battle_victory_rewards_are_applied_only_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_path, previous_db = main.DB_PATH, main.db
            main.DB_PATH = str(Path(temp_dir) / "battle-reward-idempotency.db")
            main.db = None
            try:
                await main.init_db()
                user_id = 987654323
                await main.get_player(user_id, "RewardIdempotencyTester")
                await main.db.execute(
                    """UPDATE players SET class_selected=1,hp=100,max_hp=100,xp=0,coins=0,wins=0
                       WHERE user_id=?""",
                    (user_id,),
                )
                await main.db.execute(
                    """INSERT INTO battles(user_id,monster_level,monster_hp,turn_count,is_elite,is_evolved)
                       VALUES(?,1,0,1,0,0)""",
                    (user_id,),
                )
                await main.db.commit()

                with (
                    patch("main.consume_xp_boost", new=AsyncMock(return_value=False)),
                    patch("main.record_monster_defeat", new=AsyncMock(return_value={"evolved": False, "defeats": 1})),
                    patch("main.advance_dungeon", new=AsyncMock()),
                    patch("main.award_material_drop", new=AsyncMock()),
                    patch("main.record_weekly_progress", new=AsyncMock()),
                    patch("main.record_daily_progress", new=AsyncMock()),
                    patch("main.record_player_guild_activity", new=AsyncMock()),
                    patch("main.refresh_quest_progress", new=AsyncMock()),
                ):
                    first_result = await main.finish_battle(user_id, True)
                    second_result = await main.finish_battle(user_id, True)

                self.assertIn("Victory!", first_result)
                self.assertIsNone(second_result)
                player = await main.get_player(user_id)
                self.assertEqual(player["wins"], 1)
                self.assertGreater(player["xp"], 0)
                self.assertGreater(player["coins"], 0)
                cursor = await main.db.execute(
                    "SELECT 1 FROM battles WHERE user_id=?",
                    (user_id,),
                )
                self.assertIsNone(await cursor.fetchone())
            finally:
                if main.db is not None:
                    await main.db.close()
                main.db = previous_db
                main.DB_PATH = previous_path


if __name__ == "__main__":
    unittest.main()
