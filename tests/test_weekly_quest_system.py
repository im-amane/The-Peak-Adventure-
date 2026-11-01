import unittest
import aiosqlite

from weekly_quest_system import (
    WeeklyQuestError, claim_weekly_reward, get_weekly_quests,
    init_weekly_tables, record_weekly_progress,
)


class WeeklyQuestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db=await aiosqlite.connect(":memory:")
        self.db.row_factory=aiosqlite.Row
        await self.db.execute("CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER,potions INTEGER)")
        await self.db.execute("INSERT INTO players VALUES(1,0,0)")
        await init_weekly_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_weekly_progress_caps_at_target(self):
        await record_weekly_progress(self.db,1,"wins",100,now=1790000000)
        rows=await get_weekly_quests(self.db,1,now=1790000000)
        hunter=next(row for row in rows if row["id"]=="weekly_hunter")
        self.assertEqual(hunter["progress"],15)
        self.assertTrue(hunter["completed"])

    async def test_reward_claim_is_one_time(self):
        now=1790000000
        await record_weekly_progress(self.db,1,"wins",15,now=now)
        reward=await claim_weekly_reward(self.db,1,"weekly_hunter",now=now)
        self.assertEqual(reward["coins"],300)
        with self.assertRaises(WeeklyQuestError):
            await claim_weekly_reward(self.db,1,"weekly_hunter",now=now)

    async def test_incomplete_quest_cannot_be_claimed(self):
        with self.assertRaises(WeeklyQuestError):
            await claim_weekly_reward(self.db,1,"weekly_hunter",now=1790000000)

    async def test_progress_isolated_by_week(self):
        await record_weekly_progress(self.db,1,"wins",5,now=1790000000)
        next_week=1790000000+7*86400
        rows=await get_weekly_quests(self.db,1,now=next_week)
        hunter=next(row for row in rows if row["id"]=="weekly_hunter")
        self.assertEqual(hunter["progress"],0)

    async def test_unknown_event_rejected(self):
        with self.assertRaises(WeeklyQuestError):
            await record_weekly_progress(self.db,1,"coins",1,now=1790000000)

if __name__=="__main__":
    unittest.main()
