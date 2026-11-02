import unittest
import aiosqlite

from roaming_event_system import (
    RoamingEventError, attack_roaming_event, claim_roaming_event_reward,
    get_or_create_roaming_event, init_roaming_event_tables,
)


class RoamingEventTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute(
            "CREATE TABLE players(user_id INTEGER PRIMARY KEY,level INTEGER NOT NULL,xp INTEGER NOT NULL,coins INTEGER NOT NULL DEFAULT 0,hp INTEGER NOT NULL DEFAULT 120,max_hp INTEGER NOT NULL DEFAULT 120,hero_class TEXT NOT NULL DEFAULT 'Knight')"
        )
        await self.db.executemany("INSERT INTO players(user_id,level,xp) VALUES(?,?,?)", [(1,1,0),(2,1,0)])
        await self.db.commit()
        await init_roaming_event_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_world_shares_one_active_event(self):
        first = await get_or_create_roaming_event(self.db, 1, 3, "Mire Colossus", 100, now=1000)
        second = await get_or_create_roaming_event(self.db, 1, 4, "Different Monster", 120, now=1001)
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(second["monster_name"], "Mire Colossus")

    async def test_attack_cooldown_and_shared_damage(self):
        event = await get_or_create_roaming_event(self.db, 1, 3, "Mire Colossus", 5, now=1000)
        result = await attack_roaming_event(self.db, event["event_id"], 1, 20, now=1000)
        self.assertEqual(result["hp"], 80)
        with self.assertRaisesRegex(RoamingEventError, "cooldown"):
            await attack_roaming_event(self.db, event["event_id"], 1, 10, now=1010)
        result = await attack_roaming_event(self.db, event["event_id"], 2, 100, now=1010)
        self.assertEqual(result["status"], "completed")

    async def test_only_contributors_claim_one_time_rewards(self):
        event = await get_or_create_roaming_event(self.db, 1, 3, "Mire Colossus", 1, now=1000)
        await attack_roaming_event(self.db, event["event_id"], 1, 5, now=1000)
        await attack_roaming_event(self.db, event["event_id"], 2, 100, now=1000)
        reward = await claim_roaming_event_reward(self.db, event["event_id"], 1)
        self.assertGreater(reward["coins"], 0)
        cur = await self.db.execute("SELECT coins,level,xp,max_hp,hp FROM players WHERE user_id=1")
        self.assertEqual(tuple(await cur.fetchone()), (136, 2, 25, 180, 120))
        with self.assertRaisesRegex(RoamingEventError, "already been claimed"):
            await claim_roaming_event_reward(self.db, event["event_id"], 1)
        with self.assertRaisesRegex(RoamingEventError, "contributed"):
            await claim_roaming_event_reward(self.db, event["event_id"], 3)

    async def test_event_creation_preserves_outer_transaction(self):
        await self.db.execute("BEGIN")
        event = await get_or_create_roaming_event(self.db, 2, 4, "Stone Warden", 50, now=2000)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur = await self.db.execute("SELECT 1 FROM roaming_events WHERE event_id=?", (event["event_id"],))
        self.assertIsNone(await cur.fetchone())

    async def test_attack_preserves_outer_transaction(self):
        event = await get_or_create_roaming_event(self.db, 2, 4, "Stone Warden", 50, now=2000)
        await self.db.commit()
        await self.db.execute("BEGIN")
        await attack_roaming_event(self.db, event["event_id"], 1, 10, now=2000)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur = await self.db.execute("SELECT hp FROM roaming_events WHERE event_id=?", (event["event_id"],))
        self.assertEqual((await cur.fetchone())[0], 1000)

    async def test_reward_preserves_outer_transaction(self):
        event = await get_or_create_roaming_event(self.db, 2, 4, "Stone Warden", 1, now=2000)
        await attack_roaming_event(self.db, event["event_id"], 1, 20, now=2000)
        await attack_roaming_event(self.db, event["event_id"], 2, 100, now=2000)
        await self.db.commit()
        await self.db.execute("BEGIN")
        await claim_roaming_event_reward(self.db, event["event_id"], 1)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur = await self.db.execute("SELECT reward_claimed FROM roaming_event_participants WHERE event_id=? AND user_id=1", (event["event_id"],))
        self.assertEqual((await cur.fetchone())[0], 0)
        cur = await self.db.execute("SELECT coins FROM players WHERE user_id=1")
        self.assertEqual((await cur.fetchone())[0], 0)

    async def test_ignored_reward_claim_update_does_not_credit_coins(self):
        event = await get_or_create_roaming_event(self.db, 2, 4, "Stone Warden", 1, now=2000)
        await attack_roaming_event(self.db, event["event_id"], 1, 20, now=2000)
        await attack_roaming_event(self.db, event["event_id"], 2, 100, now=2000)
        await self.db.execute("CREATE TRIGGER ignore_roaming_reward_claim BEFORE UPDATE OF reward_claimed ON roaming_event_participants BEGIN SELECT RAISE(IGNORE); END")
        await self.db.commit()
        with self.assertRaisesRegex(RoamingEventError, "already been claimed"):
            await claim_roaming_event_reward(self.db, event["event_id"], 1)
        cur = await self.db.execute("SELECT coins FROM players WHERE user_id=1")
        self.assertEqual((await cur.fetchone())[0], 0)
        cur = await self.db.execute("SELECT reward_claimed FROM roaming_event_participants WHERE event_id=? AND user_id=1", (event["event_id"],))
        self.assertEqual((await cur.fetchone())[0], 0)

    async def test_failed_player_credit_rolls_back_reward_claim(self):
        event = await get_or_create_roaming_event(self.db, 2, 4, "Stone Warden", 1, now=2000)
        await attack_roaming_event(self.db, event["event_id"], 1, 20, now=2000)
        await attack_roaming_event(self.db, event["event_id"], 2, 100, now=2000)
        await self.db.execute("CREATE TRIGGER reject_roaming_reward BEFORE UPDATE OF coins ON players WHEN OLD.user_id=1 BEGIN SELECT RAISE(ABORT,'wallet unavailable'); END")
        await self.db.commit()
        with self.assertRaisesRegex(Exception, "wallet unavailable"):
            await claim_roaming_event_reward(self.db, event["event_id"], 1)
        cur = await self.db.execute("SELECT reward_claimed FROM roaming_event_participants WHERE event_id=? AND user_id=1", (event["event_id"],))
        self.assertEqual((await cur.fetchone())[0], 0)
        cur = await self.db.execute("SELECT coins FROM players WHERE user_id=1")
        self.assertEqual((await cur.fetchone())[0], 0)

    async def test_roaming_table_initialization_preserves_outer_transaction(self):
        db = await aiosqlite.connect(":memory:")
        try:
            await db.execute("CREATE TABLE marker(value INTEGER)")
            await db.execute("BEGIN")
            await db.execute("INSERT INTO marker VALUES(1)")
            await init_roaming_event_tables(db)
            self.assertTrue(db.in_transaction)
            await db.rollback()
            cur = await db.execute("SELECT COUNT(*) FROM marker")
            self.assertEqual((await cur.fetchone())[0], 0)
            cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='roaming_events'")
            self.assertIsNone(await cur.fetchone())
        finally:
            await db.close()
    async def test_expired_event_cannot_be_attacked(self):
        event = await get_or_create_roaming_event(self.db, 1, 3, "Mire Colossus", 1, now=1000, duration_seconds=60)
        with self.assertRaisesRegex(RoamingEventError, "no longer active"):
            await attack_roaming_event(self.db, event["event_id"], 1, 10, now=1060)


if __name__ == "__main__":
    unittest.main()
