import unittest
import sqlite3
import aiosqlite

from moderation_system import (
    ModerationError, ban_player, get_active_ban,
    init_moderation_tables, unban_player,
)


class ModerationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db=await aiosqlite.connect(":memory:")
        self.db.row_factory=aiosqlite.Row
        await self.db.execute("CREATE TABLE players(user_id INTEGER PRIMARY KEY)")
        await self.db.executemany("INSERT INTO players VALUES(?)",[(1,),(2,)])
        await self.db.commit()
        await init_moderation_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_admin_can_ban_and_unban(self):
        await ban_player(self.db,900,2,"Repeated harassment",now=1000)
        self.assertEqual((await get_active_ban(self.db,2))["reason"],"Repeated harassment")
        await unban_player(self.db,900,2,now=1100)
        self.assertIsNone(await get_active_ban(self.db,2))

    async def test_ban_reason_required(self):
        with self.assertRaises(ModerationError):
            await ban_player(self.db,900,2,"bad",now=1000)

    async def test_unknown_player_cannot_be_banned(self):
        with self.assertRaises(ModerationError):
            await ban_player(self.db,900,99,"Repeated harassment",now=1000)

    async def test_reban_updates_reason_and_actor(self):
        await ban_player(self.db,900,2,"Repeated harassment",now=1000)
        await ban_player(self.db,901,2,"Cheating detected",now=1100)
        row=await get_active_ban(self.db,2)
        self.assertEqual((row["actor_id"],row["reason"]),(901,"Cheating detected"))

    async def test_ban_preserves_outer_transaction(self):
        await self.db.execute("BEGIN")
        await ban_player(self.db,900,2,"Repeated harassment",now=1000)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertIsNone(await get_active_ban(self.db,2))

    async def test_unban_preserves_outer_transaction(self):
        await ban_player(self.db,900,2,"Repeated harassment",now=1000)
        await self.db.commit()
        await self.db.execute("BEGIN")
        await unban_player(self.db,900,2,now=1100)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertIsNotNone(await get_active_ban(self.db,2))

    async def test_moderation_table_initialization_preserves_outer_transaction(self):
        db=await aiosqlite.connect(":memory:")
        try:
            await db.execute("CREATE TABLE marker(value INTEGER)")
            await db.execute("BEGIN")
            await db.execute("INSERT INTO marker VALUES(1)")
            await init_moderation_tables(db)
            self.assertTrue(db.in_transaction)
            await db.rollback()
            cur=await db.execute("SELECT COUNT(*) FROM marker")
            self.assertEqual((await cur.fetchone())[0],0)
            cur=await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='player_bans'")
            self.assertIsNone(await cur.fetchone())
        finally:
            await db.close()

    async def test_ignored_ban_upsert_does_not_report_success(self):
        await self.db.execute("CREATE TRIGGER ignore_player_ban BEFORE INSERT ON player_bans BEGIN SELECT RAISE(IGNORE); END")
        await self.db.commit()
        with self.assertRaisesRegex(ModerationError,"could not be recorded"):
            await ban_player(self.db,900,2,"Repeated harassment",now=1000)
        self.assertIsNone(await get_active_ban(self.db,2))

    async def test_invalid_moderation_timestamp_is_rejected(self):
        with self.assertRaises(ModerationError):
            await ban_player(self.db,900,2,"Repeated harassment",now=True)
    async def test_unban_requires_active_ban(self):
        with self.assertRaises(ModerationError):
            await unban_player(self.db,900,2,now=1000)

if __name__=="__main__":
    unittest.main()
