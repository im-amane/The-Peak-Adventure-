import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode
import tempfile
from pathlib import Path
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

import main


class MiniAppHttpIntegrationTests(unittest.IsolatedAsyncioTestCase):
    token = "987654:test-http-integration-token"
    user_id = 987654321

    def make_init_data(self):
        fields = {
            "auth_date": str(int(time.time())),
            "query_id": "AAHttpIntegration",
            "user": json.dumps(
                {"id": self.user_id, "first_name": "HttpHero", "username": "http_hero"},
                separators=(",", ":"),
            ),
        }
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", self.token.encode(), hashlib.sha256).digest()
        fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        return urlencode(fields)

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        self.previous_token = main.TOKEN
        main.DB_PATH = str(Path(self.temp_dir.name) / "miniapp-http.db")
        main.TOKEN = self.token
        main.db = None
        await main.init_db()
        await main.get_player(self.user_id, "HttpHero")
        await main.db.execute(
            """UPDATE players
               SET class_selected=1,hero_class='Knight',hp=100,max_hp=100
               WHERE user_id=?""",
            (self.user_id,),
        )
        await main.db.commit()

        self.client = TestClient(TestServer(main.create_web_app()))
        await self.client.start_server()
        self.headers = {"X-Telegram-Init-Data": self.make_init_data()}

    async def asyncTearDown(self):
        await self.client.close()
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        main.TOKEN = self.previous_token
        self.temp_dir.cleanup()

    async def test_http_routes_enforce_telegram_auth_and_healthcheck_database(self):
        unauthorized = await self.client.get("/api/state")
        self.assertEqual(unauthorized.status, 401)

        health = await self.client.get("/healthz")
        self.assertEqual(health.status, 200)
        self.assertEqual(await health.json(), {
            "ok": True, "service": "peak-adventure", "database": "ok"
        })
        self.assertEqual(health.headers.get("Cache-Control"), "no-store")

        state = await self.client.get("/api/state", headers=self.headers)
        self.assertEqual(state.status, 200)
        payload = await state.json()
        self.assertEqual(payload["first_name"], "HttpHero")
        self.assertTrue(payload["class_selected"])
        self.assertEqual(payload["hero_class"], "Knight")
        self.assertFalse(payload["battle_active"])

    async def test_authenticated_http_exploration_persists_active_battle(self):
        response = await self.client.post(
            "/api/explore", json={"monster_level": 1}, headers=self.headers
        )
        self.assertEqual(response.status, 200)
        payload = await response.json()
        self.assertTrue(payload["state"]["battle_active"])
        self.assertIsNotNone(payload["state"]["battle"])
        self.assertEqual(payload["state"]["battle"]["level"], 1)

        refreshed = await self.client.get("/api/state", headers=self.headers)
        self.assertEqual(refreshed.status, 200)
        state = await refreshed.json()
        self.assertTrue(state["battle_active"])
        self.assertEqual(state["battle"]["level"], 1)

    async def test_http_rate_limit_middleware_blocks_authenticated_request(self):
        with patch.object(main.api_rate_limiter, "allow", return_value=(False, 9)):
            response = await self.client.get("/api/state", headers=self.headers)
        self.assertEqual(response.status, 429)
        self.assertEqual(response.headers.get("Retry-After"), "9")
        self.assertIn("Too many requests", (await response.json())["error"])

    async def test_miniapp_static_entrypoint_is_served_by_http_application(self):
        response = await self.client.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("text/html", response.headers.get("Content-Type", ""))


if __name__ == "__main__":
    unittest.main()
