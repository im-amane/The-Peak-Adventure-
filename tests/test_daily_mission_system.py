import unittest
import aiosqlite

from daily_mission_system import (
    DAILY_MISSIONS, DailyMissionError, claim_daily_mission,
    current_day_key, get_daily_missions, init_daily_mission_tables,
    record_daily_progress,
)


class DailyMissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute(
            "CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER NOT NULL DEFAULT 0,potions INTEGER NOT NULL DEFAULT 0)"
        )
        await self.db.execute("INSERT INTO players(user_id) VALUES(101)")
        await init_daily_mission_tables(self.db)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()

    async def test_daily_missions_start_empty_and_reset_by_utc_day(self):
        rows = await get_daily_missions(self.db, 101, now=1_800_000_000)
        self.assertEqual(len(rows), len(DAILY_MISSIONS))
        self.assertTrue(all(row["progress"] == 0 for row in rows))
        self.assertNotEqual(current_day_key(1_800_000_000), current_day_key(1_800_086_400))

    async def test_progress_caps_at_target(self):
        await record_daily_progress(self.db, 101, "wins", 10, now=1_800_000_000)
        rows = await get_daily_missions(self.db, 101, now=1_800_000_000)
        hunter = next(row for row in rows if row["id"] == "daily_hunter")
        self.assertEqual(hunter["progress"], hunter["target"])

    async def test_claim_requires_completion_and_pays_once(self):
        now = 1_800_000_000
        with self.assertRaises(DailyMissionError):
            await claim_daily_mission(self.db, 101, "daily_hunter", now)
        await record_daily_progress(self.db, 101, "wins", 3, now)
        reward = await claim_daily_mission(self.db, 101, "daily_hunter", now)
        self.assertEqual(reward["coins"], 75)
        with self.assertRaises(DailyMissionError):
            await claim_daily_mission(self.db, 101, "daily_hunter", now)
        cur = await self.db.execute("SELECT coins,potions FROM players WHERE user_id=101")
        self.assertEqual(tuple(await cur.fetchone()), (75, 1))

    async def test_daily_operations_preserve_outer_transaction(self):
        now = 1_800_000_000
        await self.db.execute("CREATE TABLE audit_log(value TEXT)")
        await self.db.execute("INSERT INTO audit_log VALUES('keep')")
        await record_daily_progress(self.db, 101, "wins", 3, now)
        self.assertTrue(self.db.in_transaction)
        await get_daily_missions(self.db, 101, now)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()

        rows = await get_daily_missions(self.db, 101, now)
        hunter = next(row for row in rows if row["id"] == "daily_hunter")
        self.assertEqual(hunter["progress"], 0)
        cur = await self.db.execute("SELECT COUNT(*) FROM audit_log")
        self.assertEqual((await cur.fetchone())[0], 0)

    async def test_daily_reward_claim_preserves_outer_transaction(self):
        now = 1_800_000_000
        await record_daily_progress(self.db, 101, "wins", 3, now)
        await self.db.execute("CREATE TABLE audit_log(value TEXT)")
        await self.db.execute("INSERT INTO audit_log VALUES('keep')")
        await claim_daily_mission(self.db, 101, "daily_hunter", now)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()

        cur = await self.db.execute("SELECT coins,potions FROM players WHERE user_id=101")
        self.assertEqual(tuple(await cur.fetchone()), (0, 0))
        rows = await get_daily_missions(self.db, 101, now)
        hunter = next(row for row in rows if row["id"] == "daily_hunter")
        self.assertFalse(hunter["claimed"])

    async def test_unknown_progress_type_rejected(self):
        with self.assertRaises(DailyMissionError):
            await record_daily_progress(self.db, 101, "pvp", now=1_800_000_000)


if __name__ == "__main__":
    unittest.main()
