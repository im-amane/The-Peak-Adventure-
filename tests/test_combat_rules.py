import unittest

from game_rules import calculate_enemy_damage


class CombatRuleTests(unittest.TestCase):
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
