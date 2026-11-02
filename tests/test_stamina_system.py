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

    async def test_get_stamina_preserves_outer_transaction(self):
        await self.db.execute("BEGIN")
        await get_stamina(self.db,201,now=1000)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur=await self.db.execute("SELECT 1 FROM player_stamina WHERE user_id=201")
        self.assertIsNone(await cur.fetchone())

    async def test_consume_stamina_can_defer_commit_to_exploration(self):
        state=await consume_stamina(self.db,202,10,now=1000,commit=False)
        self.assertEqual(state["stamina"],90)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur=await self.db.execute("SELECT 1 FROM player_stamina WHERE user_id=202")
        self.assertIsNone(await cur.fetchone())

    async def test_restore_stamina_preserves_outer_transaction(self):
        await consume_stamina(self.db,203,20,now=1000)
        await self.db.execute("UPDATE player_stamina SET stamina=stamina WHERE user_id=203")
        state=await restore_stamina(self.db,203,10,now=1000)
        self.assertEqual(state["stamina"],90)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur=await self.db.execute("SELECT stamina FROM player_stamina WHERE user_id=203")
        self.assertEqual((await cur.fetchone())["stamina"],80)

    async def test_ignored_stamina_debit_does_not_allow_free_exploration(self):
        await get_stamina(self.db,204,now=1000)
        await self.db.execute(
            """CREATE TRIGGER ignore_stamina_debit
               BEFORE UPDATE OF stamina ON player_stamina
               WHEN NEW.stamina<OLD.stamina
               BEGIN SELECT RAISE(IGNORE); END"""
        )
        await self.db.commit()
        with self.assertRaisesRegex(StaminaError,"Stamina changed"):
            await consume_stamina(self.db,204,10,now=1000)
        self.assertEqual((await get_stamina(self.db,204,now=1000))["stamina"],100)

    async def test_table_initialization_preserves_outer_transaction(self):
        db=await aiosqlite.connect(":memory:")
        try:
            await db.execute("BEGIN")
            await init_stamina_tables(db)
            self.assertTrue(db.in_transaction)
            await db.rollback()
            cur=await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='player_stamina'")
            self.assertIsNone(await cur.fetchone())
        finally:
            await db.close()

    async def test_invalid_inputs_rejected(self):
        with self.assertRaises(StaminaError):
            await get_stamina(self.db, 0, now=1000)
        with self.assertRaises(StaminaError):
            await consume_stamina(self.db, 101, -1, now=1000)


if __name__ == "__main__":
    unittest.main()
