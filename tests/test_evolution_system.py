import unittest
import aiosqlite

from evolution_system import (
    EVOLUTION_DEFEATS_REQUIRED,
    EvolutionError,
    get_evolution_state,
    init_evolution_tables,
    is_evolved_spawn,
    record_monster_defeat,
    scale_evolved_monster,
)


class MonsterEvolutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await init_evolution_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_mastery_evolves_after_required_defeats(self):
        for count in range(1, EVOLUTION_DEFEATS_REQUIRED):
            state = await record_monster_defeat(self.db, 101, 7)
            self.assertEqual(state["defeats"], count)
            self.assertFalse(state["evolved"])
        state = await record_monster_defeat(self.db, 101, 7)
        self.assertEqual(state["defeats"], EVOLUTION_DEFEATS_REQUIRED)
        self.assertTrue(state["evolved"])

    async def test_mastery_is_individual_per_player_and_monster(self):
        await record_monster_defeat(self.db, 101, 7)
        await record_monster_defeat(self.db, 101, 8)
        own = await get_evolution_state(self.db, 101, 7)
        other_monster = await get_evolution_state(self.db, 101, 8)
        other_player = await get_evolution_state(self.db, 202, 7)
        self.assertEqual(own["defeats"], 1)
        self.assertEqual(other_monster["defeats"], 1)
        self.assertEqual(other_player["defeats"], 0)

    async def test_evolved_form_scales_without_mutating_original(self):
        original = {"name": "Mire Stalker", "hp": 100, "attack_power": 20, "defense": 10, "speed": 5}
        evolved = scale_evolved_monster(original)
        self.assertEqual(original["name"], "Mire Stalker")
        self.assertEqual(evolved["name"], "Ascended Mire Stalker")
        self.assertEqual(evolved["hp"], 150)
        self.assertEqual(evolved["attack_power"], 26)
        self.assertEqual(evolved["defense"], 12)
        self.assertEqual(evolved["speed"], 8)

    async def test_evolved_form_rejects_malformed_base_monster_stats(self):
        base = {"name": "Mire Stalker", "hp": 100, "attack_power": 20, "defense": 10, "speed": 5}
        invalid_variants = (
            {**base, "name": []},
            {**base, "hp": True},
            {**base, "attack_power": 2.5},
            {**base, "defense": -1},
            {**base, "speed": 101},
            {**base, "unique_power": {"effect": "freeze"}},
        )
        for monster in invalid_variants:
            with self.subTest(monster=monster), self.assertRaises(EvolutionError):
                scale_evolved_monster(monster)

    async def test_evolved_spawn_probability_requires_mastery(self):
        self.assertTrue(is_evolved_spawn(True, 1))
        self.assertTrue(is_evolved_spawn(True, 25))
        self.assertFalse(is_evolved_spawn(True, 26))
        self.assertFalse(is_evolved_spawn(False, 1))
        with self.assertRaises(ValueError):
            is_evolved_spawn(True, 101)

    async def test_invalid_mastery_input_is_rejected(self):
        with self.assertRaises(EvolutionError):
            await record_monster_defeat(self.db, 0, 7)
        with self.assertRaises(EvolutionError):
            await get_evolution_state(self.db, 101, 101)


    async def test_record_defeat_preserves_outer_transaction(self):
        await self.db.execute("INSERT INTO player_monster_mastery(user_id,monster_level,defeats) VALUES(303,9,2)")
        await self.db.commit()
        await self.db.execute("UPDATE player_monster_mastery SET defeats=defeats WHERE user_id=303")
        state = await record_monster_defeat(self.db, 303, 9)
        self.assertEqual(state["defeats"], 3)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        state = await get_evolution_state(self.db, 303, 9)
        self.assertEqual(state["defeats"], 2)

    async def test_failed_defeat_record_rolls_back_only_its_savepoint(self):
        await self.db.execute("CREATE TRIGGER reject_mastery_update BEFORE UPDATE ON player_monster_mastery BEGIN SELECT RAISE(ABORT, 'blocked'); END")
        await self.db.execute("INSERT INTO player_monster_mastery(user_id,monster_level,defeats) VALUES(404,9,2)")
        await self.db.commit()
        await self.db.execute("BEGIN")
        with self.assertRaises(Exception):
            await record_monster_defeat(self.db, 404, 9)
        self.assertTrue(self.db.in_transaction)
        await self.db.execute("INSERT INTO player_monster_mastery(user_id,monster_level,defeats) VALUES(405,10,1)")
        await self.db.commit()
        state = await get_evolution_state(self.db, 404, 9)
        self.assertEqual(state["defeats"], 2)


if __name__ == "__main__":
    unittest.main()
