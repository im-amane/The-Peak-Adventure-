import unittest
import aiosqlite

from mana_system import (
    MAX_MANA, REGEN_SECONDS, SKILL_MANA_COST, ManaError,
    consume_mana, get_mana, init_mana_tables, restore_mana,
)


class ManaSystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db=await aiosqlite.connect(":memory:")
        self.db.row_factory=aiosqlite.Row
        await init_mana_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_new_player_starts_with_full_mana(self):
        self.assertEqual((await get_mana(self.db,1,now=1000))["mana"],MAX_MANA)

    async def test_skill_cost_is_persisted(self):
        state=await consume_mana(self.db,1,SKILL_MANA_COST,now=1000)
        self.assertEqual(state["mana"],70)
        self.assertEqual((await get_mana(self.db,1,now=1000))["mana"],70)

    async def test_passive_regeneration(self):
        await consume_mana(self.db,1,40,now=1000)
        self.assertEqual((await get_mana(self.db,1,now=1000+2*REGEN_SECONDS))["mana"],62)

    async def test_cannot_cast_without_mana(self):
        await consume_mana(self.db,1,MAX_MANA,now=1000)
        with self.assertRaises(ManaError):
            await consume_mana(self.db,1,1,now=1000)

    async def test_turn_restore_is_capped(self):
        await consume_mana(self.db,1,10,now=1000)
        self.assertEqual((await restore_mana(self.db,1,20,now=1000))["mana"],MAX_MANA)

    async def test_get_mana_preserves_outer_transaction(self):
        await self.db.execute("BEGIN")
        await get_mana(self.db,101,now=1000)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur=await self.db.execute("SELECT 1 FROM player_mana WHERE user_id=101")
        self.assertIsNone(await cur.fetchone())

    async def test_consume_mana_preserves_outer_transaction(self):
        await self.db.execute("BEGIN")
        state=await consume_mana(self.db,102,30,now=1000)
        self.assertEqual(state["mana"],70)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur=await self.db.execute("SELECT 1 FROM player_mana WHERE user_id=102")
        self.assertIsNone(await cur.fetchone())

    async def test_restore_mana_preserves_outer_transaction(self):
        await consume_mana(self.db,103,30,now=1000)
        await self.db.execute("UPDATE player_mana SET mana=mana WHERE user_id=103")
        state=await restore_mana(self.db,103,10,now=1000)
        self.assertEqual(state["mana"],80)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur=await self.db.execute("SELECT mana FROM player_mana WHERE user_id=103")
        self.assertEqual((await cur.fetchone())["mana"],70)

    async def test_table_initialization_preserves_outer_transaction(self):
        db=await aiosqlite.connect(":memory:")
        try:
            await db.execute("BEGIN")
            await init_mana_tables(db)
            self.assertTrue(db.in_transaction)
            await db.rollback()
            cur=await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='player_mana'")
            self.assertIsNone(await cur.fetchone())
        finally:
            await db.close()

    async def test_ignored_mana_debit_does_not_allow_free_skill(self):
        await get_mana(self.db,104,now=1000)
        await self.db.execute(
            """CREATE TRIGGER ignore_mana_debit
               BEFORE UPDATE OF mana ON player_mana
               WHEN NEW.mana < OLD.mana
               BEGIN SELECT RAISE(IGNORE); END"""
        )
        await self.db.commit()
        with self.assertRaisesRegex(ManaError,"Mana changed"):
            await consume_mana(self.db,104,30,now=1000)
        self.assertEqual((await get_mana(self.db,104,now=1000))["mana"],100)


if __name__=="__main__":
    unittest.main()
