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

    def test_fifth_world_stories_name_their_monster_and_explain_the_fifth_seal(self):
        fifth_world = self.monsters[40:50]
        for monster in fifth_world:
            self.assertIn(monster["name"].casefold(), monster["story"].casefold())
            self.assertIn("Ember Abyss", monster["story"])
        self.assertIn("fourth seal", fifth_world[1]["story"])
        self.assertIn("fifth seal", fifth_world[4]["story"])
        self.assertIn("fifth seal", fifth_world[-1]["story"])
        self.assertIn("first blue spark", fifth_world[-1]["story"])
        self.assertTrue(fifth_world[-1]["boss"])

    def test_sixth_world_stories_name_their_monster_and_reveal_the_sixth_seal(self):
        sixth_world = self.monsters[50:60]
        for monster in sixth_world:
            self.assertIn(monster["name"].casefold(), monster["story"].casefold())
            self.assertIn("Frostfang Peaks", monster["story"])
        self.assertIn("fifth seal", sixth_world[0]["story"])
        self.assertIn("sixth seal", sixth_world[1]["story"])
        self.assertIn("sixth seal", sixth_world[-1]["story"])
        self.assertIn("seventh seal", sixth_world[-1]["story"])
        self.assertTrue(sixth_world[-1]["boss"])

    def test_seventh_world_stories_name_their_monster_and_locate_the_seventh_seal(self):
        seventh_world = self.monsters[60:70]
        for monster in seventh_world:
            self.assertIn(monster["name"].casefold(), monster["story"].casefold())
            self.assertIn("Starfall Expanse", monster["story"])
        self.assertIn("sixth seal", seventh_world[2]["story"])
        self.assertIn("seventh seal", seventh_world[4]["story"])
        self.assertIn("seventh seal", seventh_world[-1]["story"])
        self.assertIn("eighth seal", seventh_world[-1]["story"])
        self.assertTrue(seventh_world[-1]["boss"])

    def test_eighth_world_stories_name_their_monster_and_reveal_the_creator(self):
        eighth_world = self.monsters[70:80]
        for monster in eighth_world:
            self.assertIn(monster["name"].casefold(), monster["story"].casefold())
            self.assertIn("Celestial Ruins", monster["story"])
        self.assertIn("eighth seal", eighth_world[3]["story"])
        self.assertIn("ninth seal", eighth_world[4]["story"])
        self.assertIn("eighth seal", eighth_world[-1]["story"])
        self.assertIn("ninth seal", eighth_world[-1]["story"])
        self.assertTrue(eighth_world[-1]["boss"])

    def test_ninth_world_stories_name_their_monster_and_open_the_origin_path(self):
        ninth_world = self.monsters[80:90]
        for monster in ninth_world:
            self.assertIn(monster["name"].casefold(), monster["story"].casefold())
            self.assertIn("Eternal Hour", monster["story"])
        self.assertIn("ninth seal", ninth_world[5]["story"])
        self.assertIn("ninth seal", ninth_world[-1]["story"])
        self.assertIn("Origin Realm", ninth_world[-1]["story"])
        self.assertTrue(ninth_world[-1]["boss"])

    def test_tenth_world_stories_name_their_monster_and_complete_the_origin_arc(self):
        tenth_world = self.monsters[90:100]
        for monster in tenth_world:
            self.assertIn(monster["name"].casefold(), monster["story"].casefold())
            self.assertIn("Origin Realm", monster["story"])
        self.assertIn("creator", tenth_world[0]["story"])
        self.assertIn("ten worlds", tenth_world[7]["story"])
        self.assertIn("THE ALPHA GOD", tenth_world[-1]["story"])
        self.assertIn("final battle", tenth_world[-1]["story"])
        self.assertTrue(tenth_world[-1]["boss"])

    def test_monster_tactics_follow_traits_and_health_thresholds(self):
        from game_rules import choose_monster_tactic

        self.assertEqual(choose_monster_tactic("swift", 2, 100, 100), "special")
        self.assertEqual(choose_monster_tactic("swift", 3, 100, 100), "strike")
        self.assertEqual(choose_monster_tactic("armored", 2, 100, 100), "strike")
        self.assertEqual(choose_monster_tactic("armored", 3, 100, 100), "special")
        self.assertEqual(choose_monster_tactic("berserk", 1, 50, 100), "special")
        self.assertEqual(choose_monster_tactic("fury", 1, 30, 100), "special")
        self.assertEqual(choose_monster_tactic("fury", 1, 31, 100), "strike")
        self.assertEqual(choose_monster_tactic("armored", 1, 10, 100, is_boss=True, boss_phase=3), "special")
        self.assertEqual(choose_monster_tactic("armored", 2, 100, 100, is_boss=True, boss_phase=2), "special")

    def test_monster_tactics_reject_invalid_state(self):
        from game_rules import choose_monster_tactic

        for args in [("unknown", 1, 10, 10), ("swift", 0, 10, 10), ("swift", 1, 11, 10), ("swift", 1, 1, 0)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                choose_monster_tactic(*args)

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

    def test_core_rules_reject_boolean_and_fractional_numeric_inputs(self):
        from game_rules import xp_required

        for value in (True, 1.5, 0, 101):
            with self.subTest(rule="xp_required", value=value), self.assertRaises(ValueError):
                xp_required(value)
            with self.subTest(rule="expected_monster_power", value=value), self.assertRaises(ValueError):
                expected_monster_power(value)
        for speed, roll in ((True, 1), (10, False), (10.5, 1), (10, 1.5)):
            with self.subTest(speed=speed, roll=roll), self.assertRaises(ValueError):
                class_evades(speed, roll)
        for boss, hp, max_hp in ((1, 10, 100), (True, 10.5, 100), (False, 10, 100.5)):
            with self.subTest(boss=boss, hp=hp, max_hp=max_hp), self.assertRaises(ValueError):
                get_boss_phase(boss, hp, max_hp)

    def test_shared_enemy_turn_resolution_applies_traits_and_returns_consistent_state(self):
        from game_rules import resolve_enemy_turn

        common = dict(
            trait_effect="lifesteal", turn_count=3, monster_hp_before=80,
            monster_hp_after_action=60, monster_max_hp=100,
            monster_attack_power=40, monster_speed=10, player_hp=100,
            player_max_hp=100, player_level=1, armor_defense=0,
            class_defense=0, class_speed=0, player_damage=20,
            action="attack", random_bonus=0, dodge_roll=100,
            is_boss=False, boss_name="Test Beast", hero_class="Knight",
        )
        result = resolve_enemy_turn(**common)
        self.assertEqual(result["boss_phase"], 1)
        self.assertEqual(result["enemy_damage"], 57)
        self.assertFalse(result["evaded"])
        self.assertEqual(result["player_hp"], 43)
        self.assertEqual(result["monster_hp"], 74)
        self.assertIn("The monster steals 14 HP.", result["effect_notes"])

    def test_shared_enemy_turn_resolution_handles_dodge_reflect_and_poison(self):
        from game_rules import resolve_enemy_turn

        result = resolve_enemy_turn(
            trait_effect="poison", turn_count=1, monster_hp_before=100,
            monster_hp_after_action=80, monster_max_hp=100,
            monster_attack_power=40, monster_speed=0, player_hp=100,
            player_max_hp=100, player_level=1, armor_defense=0,
            class_defense=0, class_speed=100, player_damage=20,
            action="attack", random_bonus=0, dodge_roll=1,
            is_boss=False, boss_name="Venom", hero_class="Archer",
        )
        self.assertTrue(result["evaded"])
        self.assertEqual(result["enemy_damage"], 0)
        self.assertEqual(result["player_hp"], 98)
        self.assertIn("Poison deals 2 damage.", result["effect_notes"])

    def test_shared_enemy_turn_preserves_legacy_over_max_player_health(self):
        from game_rules import resolve_enemy_turn

        result = resolve_enemy_turn(
            trait_effect="armored", turn_count=1, monster_hp_before=100,
            monster_hp_after_action=80, monster_max_hp=100,
            monster_attack_power=40, monster_speed=0, player_hp=150,
            player_max_hp=100, player_level=1, armor_defense=0,
            class_defense=0, class_speed=0, player_damage=20,
            action="attack", random_bonus=0, dodge_roll=100,
            is_boss=False, boss_name="Test", hero_class="Knight",
        )
        self.assertEqual(result["player_hp"], 112)

    def test_shared_enemy_turn_resolution_rejects_boolean_and_invalid_health(self):
        from game_rules import resolve_enemy_turn

        args = dict(
            trait_effect="armored", turn_count=1, monster_hp_before=100,
            monster_hp_after_action=80, monster_max_hp=100,
            monster_attack_power=40, monster_speed=0, player_hp=100,
            player_max_hp=100, player_level=1, armor_defense=0,
            class_defense=0, class_speed=0, player_damage=20,
            action="attack", random_bonus=0, dodge_roll=1,
            is_boss=False, boss_name="Test", hero_class="Knight",
        )
        with self.assertRaises(ValueError):
            resolve_enemy_turn(**{**args, "turn_count": True})
        with self.assertRaises(ValueError):
            resolve_enemy_turn(**{**args, "monster_hp_after_action": 101})

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

    def test_combat_phase_rejects_boolean_and_fractional_values(self):
        from game_rules import choose_monster_tactic

        for phase in (True, False, 1.0, 2.5):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                calculate_enemy_damage(40, 1, 0, 0, 0, 0, boss_phase=phase)
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                choose_monster_tactic("armored", 1, 100, 100, is_boss=True, boss_phase=phase)

    def test_boss_phases_increase_incoming_damage(self):
        base = calculate_enemy_damage(40, 1, 0, 0, 0, 0)
        self.assertEqual(calculate_enemy_damage(40, 1, 0, 0, 0, 0, boss_phase=2), int(base * 1.2))
        self.assertEqual(calculate_enemy_damage(40, 1, 0, 0, 0, 0, boss_phase=3), int(base * 1.5))


if __name__ == "__main__":
    unittest.main()
