import unittest

from rate_limit import SlidingWindowRateLimiter


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

    def test_stale_keys_are_pruned_when_capacity_is_exceeded(self):
        limiter = SlidingWindowRateLimiter(window_seconds=5, max_keys=1)
        limiter.allow("old", 1, now=1)
        limiter.allow("new", 1, now=10)
        self.assertNotIn("old", limiter._events)


if __name__ == "__main__":
    unittest.main()
