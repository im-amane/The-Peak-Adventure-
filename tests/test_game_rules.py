import json
import unittest
from pathlib import Path

from game_rules import BOSS_LEVELS, expected_monster_power, validate_monster_catalogue


class GameRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monsters = json.loads(Path(__file__).resolve().parents[1].joinpath("monsters.json").read_text(encoding="utf-8"))

    def test_catalogue_has_one_hundred_monsters(self):
        self.assertEqual(len(self.monsters), 100)
        validate_monster_catalogue(self.monsters)

    def test_boss_milestones(self):
        self.assertEqual(BOSS_LEVELS, frozenset({10, 20, 30, 40, 50, 60, 70, 80, 90, 100}))
        for level in BOSS_LEVELS:
            self.assertTrue(self.monsters[level - 1]["boss"])

    def test_original_power_milestones(self):
        expected = {
            1: 100, 10: 322, 20: 1137, 30: 4022, 40: 14227,
            50: 50319, 60: 177975, 70: 629485, 80: 2226439,
            90: 7874739, 100: 27852332,
        }
        for level, power in expected.items():
            self.assertEqual(expected_monster_power(level), power)
            self.assertEqual(self.monsters[level - 1]["power"], power)

    def test_alpha_god_is_level_100_boss(self):
        alpha = self.monsters[-1]
        self.assertEqual(alpha["name"], "THE ALPHA GOD")
        self.assertTrue(alpha["boss"])
        self.assertEqual(alpha["power"], 27852332)


if __name__ == "__main__":
    unittest.main()
