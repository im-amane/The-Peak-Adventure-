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
            "CREATE TABLE players(user_id INTEGER PRIMARY KEY,level INTEGER NOT NULL,xp INTEGER NOT NULL,coins INTEGER NOT NULL DEFAULT 0)"
        )
        await self.db.executemany("INSERT INTO players(user_id,level,xp) VALUES(?,?,?)", [(1,1,0),(2,1,0)])
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
        await attack_roaming_event(self.db, event["event_id"], 1, 20, now=1000)
        await attack_roaming_event(self.db, event["event_id"], 2, 100, now=1000)
        reward = await claim_roaming_event_reward(self.db, event["event_id"], 1)
        self.assertGreater(reward["coins"], 0)
        with self.assertRaisesRegex(RoamingEventError, "already been claimed"):
            await claim_roaming_event_reward(self.db, event["event_id"], 1)
        with self.assertRaisesRegex(RoamingEventError, "contributed"):
            await claim_roaming_event_reward(self.db, event["event_id"], 3)

    async def test_expired_event_cannot_be_attacked(self):
        event = await get_or_create_roaming_event(self.db, 1, 3, "Mire Colossus", 1, now=1000, duration_seconds=60)
        with self.assertRaisesRegex(RoamingEventError, "no longer active"):
            await attack_roaming_event(self.db, event["event_id"], 1, 10, now=1060)


if __name__ == "__main__":
    unittest.main()
