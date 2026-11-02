import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONSTERS = json.loads((ROOT / "monsters.json").read_text(encoding="utf-8"))

from scripts.generate_monster_power_chart import render_csv
EXPECTED_TRAITS = {
    "regenerate",
    "fury",
    "swift",
    "armored",
    "drain",
    "poison",
    "shield",
    "reflect",
    "lifesteal",
    "berserk",
}


class MonsterCatalogTests(unittest.TestCase):
    def test_generated_power_chart_matches_canonical_catalog(self):
        chart = (ROOT / "docs" / "monster_power_chart.csv").read_text(encoding="utf-8")
        self.assertEqual(chart, render_csv(MONSTERS))
        self.assertEqual(len(chart.splitlines()), 101)

    def test_catalog_has_exactly_one_record_for_each_level(self):
        self.assertEqual(len(MONSTERS), 100)
        self.assertEqual([monster["level"] for monster in MONSTERS], list(range(1, 101)))

    def test_bosses_cover_all_ten_level_milestones(self):
        self.assertEqual(
            [monster["level"] for monster in MONSTERS if monster["boss"]],
            list(range(10, 101, 10)),
        )
        self.assertTrue(all(monster["rank"] == "BOSS" for monster in MONSTERS if monster["boss"]))

    def test_monster_names_and_abilities_are_unique(self):
        for field in ("name", "special_move", "unique_power", "advantage", "disadvantage", "story"):
            values = [monster[field] for monster in MONSTERS]
            self.assertEqual(len(values), len(set(values)), f"{field} must be unique")

    def test_power_rating_increases_with_each_level(self):
        powers = [monster["power"] for monster in MONSTERS]
        self.assertTrue(
            all(current > previous for previous, current in zip(powers, powers[1:])),
            "monster power must rise strictly with level",
        )

    def test_combat_stats_and_traits_are_valid(self):
        for monster in MONSTERS:
            with self.subTest(level=monster["level"]):
                for field in ("power", "attack_power", "defense", "speed", "hp"):
                    self.assertIsInstance(monster[field], int)
                    self.assertGreater(monster[field], 0)
                self.assertIn(monster["trait_effect"], EXPECTED_TRAITS)
                self.assertTrue(monster["element"])
                self.assertTrue(monster["weakness"])
                self.assertNotEqual(monster["element"], monster["weakness"])

    def test_each_story_has_a_region_marker_and_real_narrative(self):
        for monster in MONSTERS:
            with self.subTest(level=monster["level"]):
                story = monster["story"]
                self.assertRegex(story, re.compile(r"^\[\d+/10\s+·\s+.+\]"))
                self.assertGreaterEqual(len(story), 150)

    def test_each_monster_has_distinct_advantage_and_disadvantage(self):
        for monster in MONSTERS:
            with self.subTest(level=monster["level"]):
                self.assertTrue(monster["advantage"].strip())
                self.assertTrue(monster["disadvantage"].strip())
                self.assertNotEqual(monster["advantage"], monster["disadvantage"])


if __name__ == "__main__":
    unittest.main()
