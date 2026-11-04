import unittest
import aiosqlite

from weekly_quest_system import (
    WeeklyQuestError, claim_weekly_reward, get_weekly_quests,
    current_week_key, init_weekly_tables, record_weekly_progress,
)


class WeeklyQuestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db=await aiosqlite.connect(":memory:")
        self.db.row_factory=aiosqlite.Row
        await self.db.execute("CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER,potions INTEGER)")
        await self.db.execute("INSERT INTO players VALUES(1,0,0)")
        await init_weekly_tables(self.db)
        await self.db.commit()

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

    async def test_failed_reward_rolls_back_claim_flag(self):
        now=1790000000
        await record_weekly_progress(self.db,1,"wins",15,now=now)
        await self.db.execute("DELETE FROM players WHERE user_id=1")
        await self.db.commit()
        with self.assertRaisesRegex(WeeklyQuestError,"Player account not found"):
            await claim_weekly_reward(self.db,1,"weekly_hunter",now=now)
        cur=await self.db.execute(
            "SELECT claimed FROM player_weekly_quests WHERE user_id=1 AND week_key=(SELECT week_key FROM player_weekly_quests WHERE user_id=1 LIMIT 1) AND quest_id='weekly_hunter'"
        )
        row=await cur.fetchone()
        self.assertEqual(row["claimed"],0)

    async def test_weekly_operations_preserve_outer_transaction(self):
        now = 1790000000
        await self.db.execute("CREATE TABLE audit_log(value TEXT)")
        await self.db.execute("INSERT INTO audit_log VALUES('keep')")
        await record_weekly_progress(self.db,1,"wins",15,now=now)
        self.assertTrue(self.db.in_transaction)
        await get_weekly_quests(self.db,1,now=now)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()

        rows=await get_weekly_quests(self.db,1,now=now)
        hunter=next(row for row in rows if row["id"]=="weekly_hunter")
        self.assertEqual(hunter["progress"],0)
        cur=await self.db.execute("SELECT COUNT(*) FROM audit_log")
        self.assertEqual((await cur.fetchone())[0],0)

    async def test_weekly_reward_claim_preserves_outer_transaction(self):
        now=1790000000
        await record_weekly_progress(self.db,1,"wins",15,now=now)
        await self.db.execute("CREATE TABLE audit_log(value TEXT)")
        await self.db.execute("INSERT INTO audit_log VALUES('keep')")
        await claim_weekly_reward(self.db,1,"weekly_hunter",now=now)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()

        cur=await self.db.execute("SELECT coins,potions FROM players WHERE user_id=1")
        self.assertEqual(tuple(await cur.fetchone()),(0,0))
        rows=await get_weekly_quests(self.db,1,now=now)
        hunter=next(row for row in rows if row["id"]=="weekly_hunter")
        self.assertFalse(hunter["claimed"])

    async def test_non_string_quest_id_is_rejected(self):
        with self.assertRaises(WeeklyQuestError):
            await claim_weekly_reward(self.db,1,[],now=1790000000)

    async def test_incomplete_quest_cannot_be_claimed(self):
        with self.assertRaises(WeeklyQuestError):
            await claim_weekly_reward(self.db,1,"weekly_hunter",now=1790000000)

    async def test_progress_isolated_by_week(self):
        await record_weekly_progress(self.db,1,"wins",5,now=1790000000)
        next_week=1790000000+7*86400
        rows=await get_weekly_quests(self.db,1,now=next_week)
        hunter=next(row for row in rows if row["id"]=="weekly_hunter")
        self.assertEqual(hunter["progress"],0)

    async def test_unhashable_progress_type_is_rejected_cleanly(self):
        with self.assertRaises(WeeklyQuestError):
            await record_weekly_progress(self.db, 1, [], now=1790000000)

    async def test_invalid_weekly_timestamps_are_rejected_cleanly(self):
        for value in (True, float("nan"), float("inf"), "next week", 10**100):
            with self.subTest(value=value), self.assertRaises(WeeklyQuestError):
                current_week_key(value)
            with self.subTest(read_value=value), self.assertRaises(WeeklyQuestError):
                await get_weekly_quests(self.db, 1, now=value)

    async def test_unknown_event_rejected(self):
        with self.assertRaises(WeeklyQuestError):
            await record_weekly_progress(self.db,1,"coins",1,now=1790000000)

if __name__=="__main__":
    unittest.main()
