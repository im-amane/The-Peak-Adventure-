import copy
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

    def test_every_monster_has_unique_move_trait_and_story(self):
        self.assertEqual(len({m["name"] for m in self.monsters}), 100)
        self.assertEqual(len({m["special_move"] for m in self.monsters}), 100)
        self.assertEqual(len({m["unique_power"] for m in self.monsters}), 100)
        self.assertEqual(len({m["story"] for m in self.monsters}), 100)

    def test_alpha_god_is_level_100_boss(self):
        alpha = self.monsters[-1]
        self.assertEqual(alpha["name"], "THE ALPHA GOD")
        self.assertTrue(alpha["boss"])
        self.assertEqual(alpha["power"], 27852332)

    def test_rejects_blank_unique_power(self):
        broken = copy.deepcopy(self.monsters)
        broken[0]["unique_power"] = "   "
        with self.assertRaisesRegex(ValueError, "unique_power"):
            validate_monster_catalogue(broken)

    def test_rejects_duplicate_story_even_with_different_case(self):
        broken = copy.deepcopy(self.monsters)
        broken[1]["story"] = broken[0]["story"].upper()
        with self.assertRaisesRegex(ValueError, "unique story"):
            validate_monster_catalogue(broken)

    def test_rejects_negative_combat_stats(self):
        broken = copy.deepcopy(self.monsters)
        broken[0]["attack_power"] = -1
        with self.assertRaisesRegex(ValueError, "attack_power"):
            validate_monster_catalogue(broken)

    def test_rejects_non_boolean_boss_flag(self):
        broken = copy.deepcopy(self.monsters)
        broken[9]["boss"] = 1
        with self.assertRaisesRegex(ValueError, "boss flag"):
            validate_monster_catalogue(broken)

    def test_rejects_non_boss_with_boss_rank(self):
        broken = copy.deepcopy(self.monsters)
        broken[0]["rank"] = "BOSS"
        with self.assertRaisesRegex(ValueError, "Non-boss"):
            validate_monster_catalogue(broken)


if __name__ == "__main__":
    unittest.main()
