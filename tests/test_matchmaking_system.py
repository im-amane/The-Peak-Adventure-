import unittest

import aiosqlite

from matchmaking_system import (
    MatchmakingError,
    cancel_matchmaking,
    complete_matchmaking_match,
    expire_matchmaking_queue,
    get_matchmaking_status,
    init_matchmaking_tables,
    join_matchmaking,
)


class MatchmakingSystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute(
            """CREATE TABLE players(
                 user_id INTEGER PRIMARY KEY,
                 level INTEGER NOT NULL DEFAULT 1,
                 pvp_wins INTEGER NOT NULL DEFAULT 0,
                 pvp_losses INTEGER NOT NULL DEFAULT 0
               )"""
        )
        await self.db.executemany(
            "INSERT INTO players(user_id,level,pvp_wins,pvp_losses) VALUES(?,?,?,?)",
            (
                (1, 10, 0, 0),
                (2, 10, 0, 0),
                (3, 10, 0, 0),
                (4, 10, 10, 0),
            ),
        )
        await init_matchmaking_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_two_similar_players_match_and_can_complete_match(self):
        first = await join_matchmaking(self.db, 1, "casual", now=1000)
        self.assertEqual(first["status"], "queued")

        second = await join_matchmaking(self.db, 2, "casual", now=1001)
        self.assertEqual(second["status"], "matched")
        self.assertEqual(second["opponent_id"], 1)
        self.assertIsNotNone(second["match_id"])

        first_status = await get_matchmaking_status(self.db, 1, now=1001)
        self.assertEqual(first_status["status"], "matched")
        self.assertEqual(first_status["match_id"], second["match_id"])
        self.assertEqual(first_status["opponent_id"], 2)

        completed = await complete_matchmaking_match(
            self.db,
            second["match_id"],
            winner_id=2,
            now=1010,
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["winner_id"], 2)
        self.assertEqual((await get_matchmaking_status(self.db, 1, now=1010))["status"], "completed")

    async def test_join_is_idempotent_and_cancelled_users_are_rate_limited(self):
        first = await join_matchmaking(self.db, 1, now=1000)
        again = await join_matchmaking(self.db, 1, now=1001)
        self.assertEqual(again["status"], "queued")
        self.assertEqual(first["queued_at"], again["queued_at"])

        self.assertTrue(await cancel_matchmaking(self.db, 1, now=1002))
        self.assertFalse(await cancel_matchmaking(self.db, 1, now=1003))
        self.assertEqual((await get_matchmaking_status(self.db, 1, now=1003))["status"], "cancelled")

        with self.assertRaisesRegex(MatchmakingError, "Wait 6 seconds"):
            await join_matchmaking(self.db, 1, now=1004)
        rejoined = await join_matchmaking(self.db, 1, now=1010)
        self.assertEqual(rejoined["status"], "queued")

    async def test_rating_window_expands_for_waiting_players(self):
        waiting = await join_matchmaking(self.db, 4, "ranked", now=1000)
        self.assertEqual(waiting["status"], "queued")
        matched = await join_matchmaking(self.db, 1, "ranked", now=1015)
        self.assertEqual(matched["status"], "matched")
        self.assertEqual(matched["opponent_id"], 4)
        self.assertEqual(matched["rating_gap"], 200)

    async def test_expired_queue_entry_cannot_be_matched(self):
        await join_matchmaking(self.db, 1, now=1000)
        self.assertEqual(
            (await get_matchmaking_status(self.db, 1, now=1180))["status"],
            "expired",
        )

        other = await join_matchmaking(self.db, 2, now=1181)
        self.assertEqual(other["status"], "queued")

    async def test_invalid_mode_and_unknown_player_are_rejected(self):
        with self.assertRaises(MatchmakingError):
            await join_matchmaking(self.db, 1, "tournament", now=1000)
        with self.assertRaises(MatchmakingError):
            await join_matchmaking(self.db, 999, "casual", now=1000)

    async def test_queue_join_preserves_outer_transaction(self):
        await self.db.execute("BEGIN")
        result = await join_matchmaking(self.db, 1, now=1000)
        self.assertEqual(result["status"], "queued")
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertIsNone(await get_matchmaking_status(self.db, 1, now=1001))


if __name__ == "__main__":
    unittest.main()
