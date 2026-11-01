import ast
import unittest
from pathlib import Path

from game_rules import calculate_enemy_damage


class CombatRuleTests(unittest.TestCase):
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
