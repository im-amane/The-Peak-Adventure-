import unittest
import asyncio
import os
import tempfile

import aiosqlite

from rate_limit import DatabaseSlidingWindowRateLimiter, SlidingWindowRateLimiter


class SlidingWindowRateLimiterTests(unittest.TestCase):
    def test_allows_requests_up_to_limit_then_blocks(self):
        limiter = SlidingWindowRateLimiter(window_seconds=60)
        self.assertEqual([limiter.allow("player:1", 2, now=t)[0] for t in (1, 2)], [True, True])
        allowed, retry = limiter.allow("player:1", 2, now=3)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry, 1)

    def test_window_expires_old_requests(self):
        limiter = SlidingWindowRateLimiter(window_seconds=10)
        self.assertTrue(limiter.allow("player:1", 1, now=1)[0])
        self.assertTrue(limiter.allow("player:1", 1, now=12)[0])

    def test_keys_are_isolated(self):
        limiter = SlidingWindowRateLimiter(window_seconds=60)
        self.assertTrue(limiter.allow("player:1", 1, now=1)[0])
        self.assertTrue(limiter.allow("player:2", 1, now=1)[0])

    def test_invalid_inputs_are_rejected(self):
        limiter = SlidingWindowRateLimiter()
        with self.assertRaises(ValueError):
            limiter.allow("", 1, now=0)
        with self.assertRaises(ValueError):
            limiter.allow("player:1", 0, now=0)


    def test_invalid_configuration_types_are_rejected(self):
        for kwargs in ({"window_seconds": True}, {"max_keys": False}, {"window_seconds": 1.5}, {"max_keys": 2.5}):
            with self.assertRaises(ValueError):
                SlidingWindowRateLimiter(**kwargs)

    def test_invalid_key_limit_and_timestamp_types_are_rejected(self):
        limiter = SlidingWindowRateLimiter()
        for key, limit, now in (([], 1, 0), ("player:1", True, 0), ("player:1", 1.5, 0), ("player:1", 1, True), ("player:1", 1, float("nan")), ("player:1", 1, float("inf")), ("player:1", 1, "later")):
            with self.assertRaises(ValueError):
                limiter.allow(key, limit, now=now)
    def test_active_key_count_stays_within_capacity(self):
        limiter = SlidingWindowRateLimiter(window_seconds=60, max_keys=2)
        limiter.allow("player:1", 1, now=1)
        limiter.allow("player:2", 1, now=2)
        limiter.allow("player:3", 1, now=3)
        self.assertLessEqual(len(limiter._events), 2)
        self.assertNotIn("player:1", limiter._events)

    def test_retry_after_tracks_oldest_request_expiry(self):
        limiter = SlidingWindowRateLimiter(window_seconds=10)
        limiter.allow("player:1", 1, now=5)
        allowed, retry = limiter.allow("player:1", 1, now=8)
        self.assertFalse(allowed)
        self.assertEqual(retry, 8)

    def test_stale_keys_are_pruned_when_capacity_is_exceeded(self):
        limiter = SlidingWindowRateLimiter(window_seconds=5, max_keys=1)
        limiter.allow("old", 1, now=1)
        limiter.allow("new", 1, now=10)
        self.assertNotIn("old", limiter._events)


if __name__ == "__main__":
    unittest.main()


class DatabaseSlidingWindowRateLimiterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        self.limiter = DatabaseSlidingWindowRateLimiter(window_seconds=10)
        await self.limiter.init(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        os.unlink(self.path)

    async def test_database_limiter_enforces_window_and_expiry(self):
        self.assertEqual(await self.limiter.allow(self.db, "player:1", 2, now=100), (True, 0))
        self.assertEqual(await self.limiter.allow(self.db, "player:1", 2, now=101), (True, 0))
        allowed, retry = await self.limiter.allow(self.db, "player:1", 2, now=102)
        self.assertFalse(allowed)
        self.assertEqual(retry, 8)
        self.assertEqual(await self.limiter.allow(self.db, "player:1", 2, now=111), (True, 0))

    async def test_database_limiter_serializes_independent_connections(self):
        other = await aiosqlite.connect(self.path)
        other.row_factory = aiosqlite.Row
        try:
            results = await asyncio.gather(
                self.limiter.allow(self.db, "shared-key", 1, now=200),
                self.limiter.allow(other, "shared-key", 1, now=200),
            )
            self.assertEqual(sum(allowed for allowed, _ in results), 1)
        finally:
            await other.close()

    async def test_database_limiter_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await self.limiter.allow(self.db, "nested-key", 1, now=300)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT COUNT(*) AS total FROM api_rate_limit_events WHERE rate_key='nested-key'"
        )
        self.assertEqual((await cursor.fetchone())["total"], 0)

