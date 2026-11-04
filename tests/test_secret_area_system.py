import unittest
import aiosqlite

from evolution_system import init_evolution_tables, record_monster_defeat
from secret_area_system import (
    SECRET_AREAS, SecretAreaError, discover_secret_area,
    get_secret_area_state, init_secret_area_tables,
)


class SecretAreaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute(
            "CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER NOT NULL DEFAULT 0,potions INTEGER NOT NULL DEFAULT 0)"
        )
        await self.db.execute("CREATE TABLE boss_defeats(user_id INTEGER,monster_level INTEGER)")
        await self.db.execute("INSERT INTO players(user_id) VALUES(101)")
        await init_evolution_tables(self.db)
        await init_secret_area_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_secret_area_requires_boss_and_five_world_wins(self):
        state = await get_secret_area_state(self.db, 101, 10, 1)
        self.assertFalse(state["unlocked"])
        for _ in range(5):
            await record_monster_defeat(self.db, 101, 3)
        state = await get_secret_area_state(self.db, 101, 10, 1)
        self.assertFalse(state["unlocked"])
        await self.db.execute("INSERT INTO boss_defeats VALUES(101,10)")
        await self.db.commit()
        state = await get_secret_area_state(self.db, 101, 10, 1)
        self.assertTrue(state["unlocked"])

    async def test_discovery_rewards_are_paid_once(self):
        await self.db.execute("INSERT INTO boss_defeats VALUES(101,10)")
        await self.db.commit()
        for _ in range(5):
            await record_monster_defeat(self.db, 101, 2)
        reward = await discover_secret_area(self.db, 101, 10, 1)
        self.assertEqual(reward["name"], SECRET_AREAS[0][1])
        self.assertEqual((reward["coins"], reward["potions"]), (350, 2))
        with self.assertRaisesRegex(SecretAreaError, "already discovered"):
            await discover_secret_area(self.db, 101, 10, 1)
        cur = await self.db.execute("SELECT coins,potions FROM players WHERE user_id=101")
        self.assertEqual(tuple(await cur.fetchone()), (350, 2))

    async def test_discovery_requires_five_wins_and_valid_world(self):
        await self.db.execute("INSERT INTO boss_defeats VALUES(101,10)")
        await self.db.commit()
        with self.assertRaisesRegex(SecretAreaError, "5 battles"):
            await discover_secret_area(self.db, 101, 10, 1)
        with self.assertRaises(SecretAreaError):
            await get_secret_area_state(self.db, 101, 10, 11)

    async def test_existing_outer_transaction_is_preserved(self):
        await self.db.execute("INSERT INTO boss_defeats VALUES(101,10)")
        for _ in range(5):
            await record_monster_defeat(self.db, 101, 1)
        # The test setup is committed before opening the outer transaction.
        await self.db.commit()
        await self.db.execute("UPDATE players SET coins=coins WHERE user_id=101")
        reward = await discover_secret_area(self.db, 101, 10, 1)
        self.assertTrue(self.db.in_transaction)
        self.assertTrue(reward["discovered"])
        await self.db.rollback()
        state = await get_secret_area_state(self.db, 101, 10, 1)
        self.assertFalse(state["discovered"])


    async def test_table_initialization_preserves_outer_transaction(self):
        await self.db.execute("CREATE TABLE transaction_probe(value INTEGER)")
        await self.db.commit()
        await self.db.execute("INSERT INTO transaction_probe VALUES(1)")
        await init_secret_area_tables(self.db)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur = await self.db.execute("SELECT COUNT(*) FROM transaction_probe")
        self.assertEqual((await cur.fetchone())[0], 0)

    async def test_missing_player_does_not_leave_discovery_or_reward(self):
        await self.db.execute("INSERT INTO boss_defeats VALUES(999,10)")
        await self.db.execute(
            "INSERT INTO player_monster_mastery(user_id,monster_level,defeats) VALUES(999,1,5)"
        )
        await self.db.commit()
        with self.assertRaisesRegex(SecretAreaError, "Player account not found"):
            await discover_secret_area(self.db, 999, 10, 1)
        cur = await self.db.execute("SELECT 1 FROM player_secret_areas WHERE user_id=999")
        self.assertIsNone(await cur.fetchone())


if __name__ == "__main__":
    unittest.main()
