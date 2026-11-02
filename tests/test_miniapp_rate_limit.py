import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web

import main
from rate_limit import SlidingWindowRateLimiter


class FakeRequest:
    def __init__(self, path, method="POST"):
        self.path = path
        self.method = method
        self.headers = {"X-Telegram-Init-Data": "signed-test-data"}


class MiniAppRateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous_api_limiter = main.api_rate_limiter
        self.previous_event_limiter = main.rate_limit_event_limiter
        self.previous_route_limiter = main.api_route_rate_limiter
        self.previous_db = main.db
        main.api_rate_limiter = SlidingWindowRateLimiter(window_seconds=60)
        main.rate_limit_event_limiter = SlidingWindowRateLimiter(window_seconds=60)
        main.api_route_rate_limiter = SlidingWindowRateLimiter(window_seconds=60)
        main.db = None

    async def asyncTearDown(self):
        main.api_rate_limiter = self.previous_api_limiter
        main.rate_limit_event_limiter = self.previous_event_limiter
        main.api_route_rate_limiter = self.previous_route_limiter
        main.db = self.previous_db

    async def call_middleware(self, path, method="POST"):
        async def handler(_request):
            return web.Response(status=200)

        with patch("main.validate_init_data", return_value={"id": 987654321}):
            return await main.miniapp_rate_limit(FakeRequest(path, method), handler)

    async def test_premium_shop_has_a_stricter_route_limit(self):
        responses = [
            await self.call_middleware("/api/premium-shop")
            for _ in range(7)
        ]
        self.assertEqual([response.status for response in responses[:6]], [200] * 6)
        self.assertEqual(responses[6].status, 429)
        self.assertIn("Retry-After", responses[6].headers)

    async def test_sensitive_route_limits_are_isolated_by_endpoint(self):
        for _ in range(6):
            response = await self.call_middleware("/api/premium-shop")
            self.assertEqual(response.status, 200)
        social_response = await self.call_middleware("/api/social")
        self.assertEqual(social_response.status, 200)

    async def test_global_write_limit_still_applies_across_different_routes(self):
        for path, count in (("/api/action", 15), ("/api/explore", 15), ("/api/social", 10)):
            for _ in range(count):
                response = await self.call_middleware(path)
                self.assertEqual(response.status, 200)
        blocked = await self.call_middleware("/api/world")
        self.assertEqual(blocked.status, 429)

    async def test_character_story_and_reward_mutations_have_route_limits(self):
        route_limits = {
            "/api/appearance": 10,
            "/api/story": 15,
            "/api/quest/claim": 10,
            "/api/daily-mission/claim": 10,
            "/api/weekly-quest/claim": 10,
            "/api/matchmaking": 8,
            "/api/settings": 10,
        }
        for path, limit in route_limits.items():
            with self.subTest(path=path):
                main.api_rate_limiter = SlidingWindowRateLimiter(window_seconds=60)
                main.api_route_rate_limiter = SlidingWindowRateLimiter(window_seconds=60)
                for _ in range(limit):
                    response = await self.call_middleware(path)
                    self.assertEqual(response.status, 200)
                blocked = await self.call_middleware(path)
                self.assertEqual(blocked.status, 429)
                self.assertIn("Retry-After", blocked.headers)

    async def test_every_state_mutation_route_is_covered_by_route_limits(self):
        expected = {
            "/api/action", "/api/explore", "/api/social", "/api/premium-shop",
            "/api/world", "/api/dungeon", "/api/appearance", "/api/story",
            "/api/quest/claim", "/api/daily-mission/claim", "/api/weekly-quest/claim", "/api/settings",
        }
        self.assertTrue(expected.issubset(main.API_ROUTE_LIMITS))

    async def test_repeated_blocked_requests_only_write_one_security_event_per_window(self):
        main.db = object()
        with patch("main.validate_init_data", return_value={"id": 987654321}):
            with patch("main.get_active_ban", new=AsyncMock(return_value=None)):
                with patch("main.record_security_event", new=AsyncMock()) as record_event:
                    async def handler(_request):
                        return web.Response(status=200)

                    for _ in range(9):
                        await main.miniapp_rate_limit(FakeRequest("/api/premium-shop"), handler)

        self.assertEqual(record_event.await_count, 1)


if __name__ == "__main__":
    unittest.main()
