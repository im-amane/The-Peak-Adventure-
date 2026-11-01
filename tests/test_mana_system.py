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

if __name__=="__main__":
    unittest.main()
