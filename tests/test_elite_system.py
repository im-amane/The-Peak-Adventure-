import unittest

from elite_system import ELITE_SPAWN_CHANCE, is_elite_spawn, scale_elite_monster


class EliteMonsterTests(unittest.TestCase):
    def test_spawn_chance_boundary(self):
        self.assertTrue(is_elite_spawn(False, 1))
        self.assertTrue(is_elite_spawn(False, ELITE_SPAWN_CHANCE))
        self.assertFalse(is_elite_spawn(False, ELITE_SPAWN_CHANCE + 1))

    def test_bosses_never_roll_as_elites(self):
        self.assertFalse(is_elite_spawn(True, 1))

    def test_elite_stats_are_scaled_on_a_copy(self):
        base = {"hp": 100, "attack_power": 20, "defense": 10, "speed": 95}
        elite = scale_elite_monster(base)
        self.assertEqual(elite["hp"], 170)
        self.assertEqual(elite["attack_power"], 27)
        self.assertEqual(elite["defense"], 12)
        self.assertEqual(elite["speed"], 100)
        self.assertEqual(base["hp"], 100)

    def test_invalid_roll_and_monster_are_rejected(self):
        with self.assertRaises(ValueError):
            is_elite_spawn(False, 0)
        with self.assertRaises(ValueError):
            scale_elite_monster({"hp": 1})


if __name__ == "__main__":
    unittest.main()
