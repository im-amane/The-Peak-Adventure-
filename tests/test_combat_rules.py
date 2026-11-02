import ast
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
                with unittest.mock.patch(
                    "main.finish_battle",
                    side_effect=RuntimeError("simulated Telegram reward failure"),
                ):
                    with self.assertRaisesRegex(RuntimeError,"simulated Telegram reward failure"):
                        await main._battle_action_unlocked(call)
                self.assertTrue(main.db.in_transaction)
                await main.db.rollback()
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


if __name__ == "__main__":
    unittest.main()
