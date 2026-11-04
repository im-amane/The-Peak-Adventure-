import unittest

from economy_balance import (
    BOSS_LEVELS,
    audit_shop_affordability,
    calculate_battle_coin_reward,
    wins_to_afford,
    validate_shop_affordability,
)
from main import SHOP_ITEMS


class EconomyBalanceTests(unittest.TestCase):
    def test_coin_rewards_match_the_existing_pve_formula(self):
        self.assertEqual(calculate_battle_coin_reward(1), 22)
        self.assertEqual(calculate_battle_coin_reward(10, is_boss=True), 335)
        self.assertEqual(calculate_battle_coin_reward(40, is_boss=True), 1295)
        self.assertEqual(calculate_battle_coin_reward(10, is_boss=True, is_elite=True), 502)
        self.assertEqual(calculate_battle_coin_reward(10, is_boss=True, is_elite=True, is_evolved=True), 753)

    def test_boss_levels_cover_every_ten_level_milestone(self):
        self.assertEqual(BOSS_LEVELS, frozenset(range(10, 101, 10)))

    def test_wins_to_afford_rounds_up(self):
        self.assertEqual(wins_to_afford(40, 22), 2)
        self.assertEqual(wins_to_afford(44, 22), 2)
        self.assertEqual(wins_to_afford(45, 22), 3)
        self.assertEqual(wins_to_afford(0, 22), 0)

    def test_shop_affordability_report_covers_every_catalog_item(self):
        report = audit_shop_affordability(SHOP_ITEMS)
        self.assertEqual({row["item_id"] for row in report}, set(SHOP_ITEMS))
        self.assertTrue(all(row["wins_to_afford"] >= 1 for row in report))
        self.assertTrue(all(row["coins_per_win"] > 0 for row in report))
        self.assertLessEqual(max(row["wins_to_afford"] for row in report), 5)

    def test_live_shop_catalog_stays_within_five_clean_wins(self):
        report = validate_shop_affordability(SHOP_ITEMS, max_wins=5)
        self.assertEqual(len(report), len(SHOP_ITEMS))

    def test_shop_affordability_guard_rejects_unreachable_price_spike(self):
        broken = {key: dict(item) for key, item in SHOP_ITEMS.items()}
        broken["flame_sword"]["cost"] = 50_000
        with self.assertRaisesRegex(ValueError, "progression budget"):
            validate_shop_affordability(broken, max_wins=5)

    def test_shop_affordability_guard_rejects_invalid_budget(self):
        for value in (True, 0, -1, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_shop_affordability(SHOP_ITEMS, max_wins=value)

    def test_report_exposes_progression_costs_in_unlock_order(self):
        report = audit_shop_affordability(SHOP_ITEMS)
        by_id = {row["item_id"]: row for row in report}
        self.assertEqual(by_id["iron_sword"]["wins_to_afford"], 2)
        self.assertEqual(by_id["flame_sword"]["wins_to_afford"], 4)
        self.assertEqual(by_id["dragon_slayer"]["wins_to_afford"], 2)
        self.assertEqual(by_id["celestial_armor"]["wins_to_afford"], 1)

    def test_invalid_reward_inputs_are_rejected(self):
        for level in (True, False, 0, 101, 1.5, "10"):
            with self.subTest(level=level), self.assertRaises(ValueError):
                calculate_battle_coin_reward(level)
        with self.assertRaises(ValueError):
            calculate_battle_coin_reward(10, is_boss=1)

    def test_invalid_affordability_inputs_are_rejected(self):
        for cost, reward in ((-1, 10), (True, 10), (10, 0), (10, False)):
            with self.subTest(cost=cost, reward=reward), self.assertRaises(ValueError):
                wins_to_afford(cost, reward)
        for catalog in (None, [], {"bad": {"level": True, "cost": 10}}):
            with self.subTest(catalog=catalog), self.assertRaises(ValueError):
                audit_shop_affordability(catalog)


if __name__ == "__main__":
    unittest.main()
