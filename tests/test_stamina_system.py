import unittest

import aiosqlite

from stamina_system import (
    EXPLORE_COST, MAX_STAMINA, REGEN_SECONDS, StaminaError,
    consume_stamina, get_stamina, init_stamina_tables, restore_stamina,
)


class StaminaSystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await init_stamina_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_new_player_starts_full(self):
        self.assertEqual((await get_stamina(self.db, 101, now=1000))["stamina"], MAX_STAMINA)

    async def test_consumption_is_persistent(self):
        state = await consume_stamina(self.db, 101, EXPLORE_COST, now=1000)
        self.assertEqual(state["stamina"], 90)
        self.assertEqual((await get_stamina(self.db, 101, now=1000))["stamina"], 90)

    async def test_regeneration_uses_elapsed_intervals(self):
        await consume_stamina(self.db, 101, 30, now=1000)
        self.assertEqual((await get_stamina(self.db, 101, now=1000 + 2 * REGEN_SECONDS))["stamina"], 72)

    async def test_cannot_go_below_zero(self):
        await consume_stamina(self.db, 101, MAX_STAMINA, now=1000)
        with self.assertRaises(StaminaError):
            await consume_stamina(self.db, 101, 1, now=1000)

    async def test_restore_is_capped(self):
        await consume_stamina(self.db, 101, 20, now=1000)
        self.assertEqual((await restore_stamina(self.db, 101, 50, now=1000))["stamina"], MAX_STAMINA)

    async def test_full_stamina_does_not_bank_regeneration_time(self):
        await get_stamina(self.db, 101, now=1000)
        await consume_stamina(self.db, 101, 10, now=10000)
        self.assertEqual((await get_stamina(self.db, 101, now=10000))["stamina"], 90)

    async def test_invalid_inputs_rejected(self):
        with self.assertRaises(StaminaError):
            await get_stamina(self.db, 0, now=1000)
        with self.assertRaises(StaminaError):
            await consume_stamina(self.db, 101, -1, now=1000)


if __name__ == "__main__":
    unittest.main()
