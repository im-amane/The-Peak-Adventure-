import unittest
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

    async def test_unban_requires_active_ban(self):
        with self.assertRaises(ModerationError):
            await unban_player(self.db,900,2,now=1000)

if __name__=="__main__":
    unittest.main()
