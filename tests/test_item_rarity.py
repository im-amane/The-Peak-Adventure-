import unittest

from crafting_system import MATERIAL_MIN_LEVEL, MATERIAL_RARITY, RECIPES
from item_rarity import RARITY_TIERS, rarity_label, rarity_price_multiplier, rarity_rank
from main import SHOP_ITEMS


class ItemRarityTests(unittest.TestCase):
    def test_rarity_tiers_have_monotonic_rank_and_economy_multipliers(self):
        rarities = list(RARITY_TIERS)
        ranks = [rarity_rank(rarity) for rarity in rarities]
        multipliers = [rarity_price_multiplier(rarity) for rarity in rarities]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(len(set(ranks)), len(ranks))
        self.assertEqual(multipliers, sorted(multipliers))
        self.assertEqual(rarity_label("legendary"), "Legendary")
        with self.assertRaises(ValueError):
            rarity_rank("unknown")

    def test_shop_gear_progression_increases_level_cost_stats_and_rarity(self):
        for slot in ("weapon", "armor"):
            items = sorted(
                (item for item in SHOP_ITEMS.values() if item["type"] == slot),
                key=lambda item: item["level"],
            )
            self.assertGreaterEqual(len(items), 3)
            for previous, current in zip(items, items[1:]):
                self.assertGreater(current["level"], previous["level"])
                self.assertGreater(current["cost"], previous["cost"])
                self.assertGreater(current["bonus"], previous["bonus"])
                self.assertGreaterEqual(
                    rarity_rank(current["rarity"]), rarity_rank(previous["rarity"])
                )

    def test_material_and_recipe_rarity_tracks_progression(self):
        materials = sorted(MATERIAL_MIN_LEVEL, key=MATERIAL_MIN_LEVEL.get)
        material_ranks = [rarity_rank(MATERIAL_RARITY[item]) for item in materials]
        self.assertEqual(material_ranks, sorted(material_ranks))

        recipes = sorted(RECIPES.values(), key=lambda recipe: recipe["level"])
        recipe_ranks = [rarity_rank(recipe["rarity"]) for recipe in recipes]
        self.assertEqual(recipe_ranks, sorted(recipe_ranks))
        self.assertEqual(recipe_ranks[-1], rarity_rank("legendary"))


if __name__ == "__main__":
    unittest.main()
