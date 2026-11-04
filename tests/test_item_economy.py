import unittest

from item_economy import (
    RARITY_COIN_BANDS,
    RARITY_LABELS,
    SHOP_ITEM_RARITY,
    get_item_rarity,
    validate_shop_catalog,
)
from crafting_system import MATERIAL_RARITY, MATERIALS, RECIPES


class ItemEconomyTests(unittest.TestCase):
    def setUp(self):
        self.shop = {
            "iron_sword": {"cost": 40, "level": 2, "bonus": 8},
            "steel_sword": {"cost": 150, "level": 5, "bonus": 20},
            "flame_sword": {"cost": 450, "level": 15, "bonus": 45},
            "dragon_slayer": {"cost": 1500, "level": 40, "bonus": 90},
            "leather_armor": {"cost": 30, "level": 2, "bonus": 5},
            "iron_armor": {"cost": 150, "level": 10, "bonus": 18},
            "frostguard_armor": {"cost": 500, "level": 25, "bonus": 35},
            "celestial_armor": {"cost": 1400, "level": 60, "bonus": 60},
            "health_potion": {"cost": 25, "level": 1, "bonus": 1},
        }

    def test_shop_catalog_matches_all_rarity_ids_and_price_bands(self):
        self.assertIsNone(validate_shop_catalog(self.shop))
        self.assertEqual(set(self.shop), set(SHOP_ITEM_RARITY))

    def test_unknown_shop_ids_are_rejected(self):
        self.shop["mystery_blade"] = {"cost": 10, "level": 1, "bonus": 1}
        with self.assertRaisesRegex(ValueError, "IDs and rarity"):
            validate_shop_catalog(self.shop)

    def test_prices_cannot_escape_rarity_bands(self):
        self.shop["iron_sword"]["cost"] = 999
        with self.assertRaisesRegex(ValueError, "does not fit"):
            validate_shop_catalog(self.shop)

    def test_boolean_and_negative_values_are_rejected(self):
        self.shop["iron_sword"]["cost"] = True
        with self.assertRaisesRegex(ValueError, "non-integer"):
            validate_shop_catalog(self.shop)
        self.shop["iron_sword"]["cost"] = -1
        with self.assertRaisesRegex(ValueError, "invalid economy"):
            validate_shop_catalog(self.shop)

    def test_shop_rarity_display_is_stable_and_rejects_unknown_ids(self):
        self.assertEqual(get_item_rarity("dragon_slayer"), "🟣 Epic")
        with self.assertRaises(ValueError):
            get_item_rarity("unknown")

    def test_crafting_recipes_have_ordered_rarity_tiers(self):
        self.assertEqual(
            [RECIPES[key]["rarity"] for key in ("iron_sword", "frost_armor", "rift_blade", "celestial_mail")],
            ["common", "uncommon", "rare", "epic"],
        )
        self.assertEqual(set(MATERIAL_RARITY), set(MATERIALS))
        self.assertTrue(all(value in RARITY_LABELS for value in MATERIAL_RARITY.values()))

    def test_rarity_bands_are_contiguous_and_positive(self):
        ordered = [RARITY_COIN_BANDS[key] for key in ("common", "uncommon", "rare", "epic", "legendary")]
        self.assertTrue(all(low > 0 and high >= low for low, high in ordered))
        self.assertTrue(all(ordered[index][1] + 1 == ordered[index + 1][0] for index in range(len(ordered) - 1)))


if __name__ == "__main__":
    unittest.main()
