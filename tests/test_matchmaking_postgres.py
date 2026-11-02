"""PostgreSQL concurrency coverage for matchmaking account-level locking."""
import asyncio
import os
import unittest
import uuid

from postgres_adapter import PostgresConnection
import main
from matchmaking_system import MatchmakingError, join_matchmaking


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresMatchmakingConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_one = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        self.db_two = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        self.schema = "peak_matchmaking_" + uuid.uuid4().hex[:12]
        await self.db_one.execute(f'CREATE SCHEMA "{self.schema}"')
        await self.db_one.commit()
        for db in (self.db_one, self.db_two):
            await db.execute(f'SET search_path TO "{self.schema}"')
            await db.commit()
        await main.init_game_schema(self.db_one)
        await self.db_one.executemany(
            "INSERT INTO players(user_id,username) VALUES(?,?)",
            ((9_100_000_001, "QueueOne"), (9_100_000_002, "QueueTwo")),
        )
        await self.db_one.commit()

    async def asyncTearDown(self):
        for db in (self.db_one, self.db_two):
            if db.in_transaction:
                await db.rollback()
        await self.db_one.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await self.db_one.commit()
        await self.db_one.close()
        await self.db_two.close()

    async def test_same_account_cannot_join_two_modes_concurrently(self):
        outcomes = await asyncio.gather(
            join_matchmaking(self.db_one, 9_100_000_001, "casual", now=2_000_000_000),
            join_matchmaking(self.db_two, 9_100_000_001, "ranked", now=2_000_000_000),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, MatchmakingError) for item in outcomes), 1)
        cursor = await self.db_one.execute(
            "SELECT mode,status FROM matchmaking_queue WHERE user_id=?",
            (9_100_000_001,),
        )
        row = await cursor.fetchone()
        self.assertIn(row["mode"], {"casual", "ranked"})
        self.assertEqual(row["status"], "queued")

    async def test_two_accounts_match_once_under_concurrent_joins(self):
        results = await asyncio.gather(
            join_matchmaking(self.db_one, 9_100_000_001, "casual", now=2_000_000_100),
            join_matchmaking(self.db_two, 9_100_000_002, "casual", now=2_000_000_100),
        )
        statuses = {item["status"] for item in results}
        self.assertEqual(statuses, {"queued", "matched"})
        cursor = await self.db_one.execute("SELECT COUNT(*) AS count FROM matchmaking_matches")
        self.assertEqual((await cursor.fetchone())["count"], 1)


if __name__ == "__main__":
    unittest.main()
