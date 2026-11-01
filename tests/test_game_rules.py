import copy
import json
import unittest
from pathlib import Path

from game_rules import BOSS_LEVELS, calculate_enemy_damage, class_evades, expected_monster_power, get_boss_phase, nearby_monster_levels, skill_cooldown_for_class, validate_monster_catalogue


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

    def test_second_world_stories_name_their_monster_and_continue_the_seal_mystery(self):
        second_world = self.monsters[10:20]
        for monster in second_world:
            self.assertIn(monster["name"].casefold(), monster["story"].casefold())
            self.assertIn("Ashen Desert", monster["story"])
        self.assertIn("buried river", second_world[0]["story"])
        self.assertIn("second seal", second_world[-1]["story"])
        self.assertIn("first blue spark", second_world[-1]["story"])

    def test_third_world_stories_name_their_monster_and_advance_the_seal_mystery(self):
        third_world = self.monsters[20:30]
        for monster in third_world:
            self.assertIn(monster["name"].casefold(), monster["story"].casefold())
            self.assertIn("Stormglass Highlands", monster["story"])
        self.assertIn("second seal", third_world[0]["story"])
        self.assertIn("third seal", third_world[6]["story"])
        self.assertIn("third seal", third_world[-1]["story"])
        self.assertIn("first blue spark", third_world[-1]["story"])
        self.assertTrue(third_world[-1]["boss"])

    def test_fourth_world_stories_name_their_monster_and_reveal_the_guardian(self):
        fourth_world = self.monsters[30:40]
        for monster in fourth_world:
            self.assertIn(monster["name"].casefold(), monster["story"].casefold())
            self.assertIn("Hollow Kingdom", monster["story"])
        self.assertIn("first seal", fourth_world[0]["story"])
        self.assertIn("fourth seal", fourth_world[5]["story"])
        self.assertIn("fourth seal", fourth_world[-1]["story"])
        self.assertIn("first blue spark", fourth_world[-1]["story"])
        self.assertTrue(fourth_world[-1]["boss"])

    def test_all_ten_combat_traits_are_used(self):
        expected = {"regenerate", "fury", "swift", "armored", "drain", "poison", "shield", "reflect", "lifesteal", "berserk"}
        self.assertEqual({monster["trait_effect"] for monster in self.monsters}, expected)

    def test_alpha_god_is_level_100_boss(self):
        alpha = self.monsters[-1]
        self.assertEqual(alpha["name"], "THE ALPHA GOD")
        self.assertTrue(alpha["boss"])
        self.assertEqual(alpha["power"], 27852332)

    def test_first_world_stories_name_their_monster_and_form_one_arc(self):
        first_world = self.monsters[:10]
        for monster in first_world:
            self.assertIn(monster["name"].casefold(), monster["story"].casefold())
            self.assertIn("Whispering Meadow", monster["story"])
        self.assertIn("blue spark", first_world[0]["story"])
        self.assertIn("first seal", first_world[-1]["story"])

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

    def test_player_defence_reduces_incoming_damage(self):
        without_defence = calculate_enemy_damage(40, 1, 0, 0, 0, 0)
        with_class_defence = calculate_enemy_damage(40, 1, 0, 12, 0, 0)
        with_armor = calculate_enemy_damage(40, 1, 8, 0, 0, 0)
        self.assertEqual(without_defence, 38)
        self.assertEqual(with_class_defence, 26)
        self.assertEqual(with_armor, 30)

    def test_enemy_damage_keeps_minimum_and_trait_modifiers(self):
        self.assertEqual(calculate_enemy_damage(1, 100, 100, 100, 0, 0), 3)
        self.assertEqual(calculate_enemy_damage(40, 1, 0, 0, 0, 0, fury=True), 47)
        self.assertEqual(calculate_enemy_damage(40, 1, 0, 0, 0, 0, special=True), 57)

    def test_class_speed_controls_dodge_chance(self):
        self.assertFalse(class_evades(0, 1))
        self.assertTrue(class_evades(10, 10))
        self.assertFalse(class_evades(10, 11))

    def test_mage_has_faster_skill_cooldown(self):
        self.assertEqual(skill_cooldown_for_class("Mage"), 3)
        self.assertEqual(skill_cooldown_for_class("Knight"), 4)
        self.assertEqual(skill_cooldown_for_class("Archer"), 4)
        self.assertEqual(skill_cooldown_for_class("Berserker"), 4)

    def test_nearby_monsters_offer_multiple_level_appropriate_encounters(self):
        self.assertEqual(nearby_monster_levels(1), (1, 2))
        self.assertEqual(nearby_monster_levels(11), (11, 12))
        self.assertEqual(nearby_monster_levels(10), (10,))
        self.assertEqual(nearby_monster_levels(10, boss_defeated=True), (9, 11))
        self.assertEqual(nearby_monster_levels(100, boss_defeated=True), (99,))

    def test_nearby_monster_levels_reject_invalid_player_level(self):
        for level in (0, 101, True, 1.5):
            with self.subTest(level=level), self.assertRaises(ValueError):
                nearby_monster_levels(level)

    def test_boss_phase_thresholds_and_normal_monsters(self):
        self.assertEqual(get_boss_phase(False, 1, 100), 1)
        self.assertEqual(get_boss_phase(True, 61, 100), 1)
        self.assertEqual(get_boss_phase(True, 60, 100), 2)
        self.assertEqual(get_boss_phase(True, 26, 100), 2)
        self.assertEqual(get_boss_phase(True, 25, 100), 3)

    def test_boss_phases_increase_incoming_damage(self):
        base = calculate_enemy_damage(40, 1, 0, 0, 0, 0)
        self.assertEqual(calculate_enemy_damage(40, 1, 0, 0, 0, 0, boss_phase=2), int(base * 1.2))
        self.assertEqual(calculate_enemy_damage(40, 1, 0, 0, 0, 0, boss_phase=3), int(base * 1.5))


if __name__ == "__main__":
    unittest.main()
