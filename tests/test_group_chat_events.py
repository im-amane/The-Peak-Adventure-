import random
import unittest

import aiosqlite

from group_chat_event_system import (
    GroupChatEventError,
    attack_group_chat_event,
    get_active_group_chat_event,
    init_group_chat_event_tables,
    record_group_chat_message,
)


class FixedRandom:
    @staticmethod
    def randint(low, high):
        return low

    @staticmethod
    def choice(values):
        return values[0]


class GroupChatEventTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute(
            "CREATE TABLE group_profiles(chat_id INTEGER PRIMARY KEY, group_level INTEGER NOT NULL)"
        )
        await self.db.execute(
            "CREATE TABLE players(user_id INTEGER PRIMARY KEY, username TEXT)"
        )
        await self.db.execute("INSERT INTO group_profiles(chat_id,group_level) VALUES(-1001,1)")
        await self.db.executemany(
            "INSERT INTO players(user_id,username) VALUES(?,?)",
            [(101, "Ash"), (202, "Mira")],
        )
        await init_group_chat_event_tables(self.db)
        self.monsters = [{"level": 1, "name": "BABY SLIME", "hp": 40}]
        self.rng = FixedRandom()

    async def asyncTearDown(self):
        await self.db.close()

    async def test_only_registered_groups_are_counted(self):
        result = await record_group_chat_message(
            self.db, -2002, 101, self.monsters, now=1000, rng=self.rng
        )
        self.assertIsNone(result)
        cursor = await self.db.execute("SELECT COUNT(*) FROM group_chat_event_state")
        self.assertEqual((await cursor.fetchone())[0], 0)

    async def test_spawn_requires_message_target_and_random_cooldown(self):
        for _ in range(149):
            result = await record_group_chat_message(
                self.db, -1001, 101, self.monsters, now=1000, rng=self.rng
            )
            self.assertIsNone(result)

        # The message threshold is reached, but the initial 10-minute cooldown is not.
        result = await record_group_chat_message(
            self.db, -1001, 101, self.monsters, now=1500, rng=self.rng
        )
        self.assertIsNone(result)

        # The next ordinary message after the cooldown completes triggers the event.
        result = await record_group_chat_message(
            self.db, -1001, 101, self.monsters, now=1600, rng=self.rng
        )
        self.assertEqual(result["monster_name"], "BABY SLIME")
        self.assertEqual(result["hp"], 120)
        active = await get_active_group_chat_event(self.db, -1001, now=1600)
        self.assertEqual(active["status"], "active")
        self.assertEqual(active["participants"], [])

    async def test_shared_hp_cooldown_leaderboard_and_victory(self):
        for _ in range(149):
            await record_group_chat_message(
                self.db, -1001, 101, self.monsters, now=1000, rng=self.rng
            )
        await record_group_chat_message(
            self.db, -1001, 101, self.monsters, now=1600, rng=self.rng
        )
        first = await attack_group_chat_event(self.db, -1001, 101, 40, now=1601, rng=self.rng)
        self.assertEqual(first["hp"], 80)
        with self.assertRaisesRegex(GroupChatEventError, "cooldown"):
            await attack_group_chat_event(self.db, -1001, 101, 10, now=1602, rng=self.rng)

        victory = await attack_group_chat_event(self.db, -1001, 202, 80, now=1603, rng=self.rng)
        self.assertEqual(victory["status"], "won")
        self.assertEqual([row["user_id"] for row in victory["participants"]], [101, 202])
        self.assertEqual([row["damage"] for row in victory["participants"]], [40, 80])
        self.assertIsNone(await get_active_group_chat_event(self.db, -1001, now=1604))

    async def test_event_expires_and_cannot_be_attacked(self):
        for _ in range(149):
            await record_group_chat_message(
                self.db, -1001, 101, self.monsters, now=1000, rng=self.rng
            )
        await record_group_chat_message(
            self.db, -1001, 101, self.monsters, now=1600, rng=self.rng
        )
        with self.assertRaisesRegex(GroupChatEventError, "escaped"):
            await attack_group_chat_event(self.db, -1001, 101, 10, now=1600 + 20 * 60, rng=self.rng)
        self.assertIsNone(await get_active_group_chat_event(self.db, -1001, now=1600 + 20 * 60))


if __name__ == "__main__":
    unittest.main()
