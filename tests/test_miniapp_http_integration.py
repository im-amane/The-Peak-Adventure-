import asyncio
import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
        self.previous_admin_ids = main.ADMIN_IDS
        self.previous_monitor = main.runtime_monitor
        main.DB_PATH = str(Path(self.temp_dir.name) / "miniapp-http.db")
        main.TOKEN = self.token
        main.ADMIN_IDS = set()
        main.runtime_monitor = main.RuntimeMonitor()
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
        main.ADMIN_IDS = self.previous_admin_ids
        main.runtime_monitor = self.previous_monitor
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

    async def test_operations_metrics_require_admin_init_data_and_return_aggregate_health(self):
        unauthorized = await self.client.get("/ops/metrics")
        self.assertEqual(unauthorized.status, 401)

        forbidden = await self.client.get("/ops/metrics", headers=self.headers)
        self.assertEqual(forbidden.status, 403)

        health = await self.client.get("/healthz")
        self.assertEqual(health.status, 200)
        main.ADMIN_IDS = {self.user_id}
        response = await self.client.get("/ops/metrics", headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        payload = await response.json()
        self.assertGreaterEqual(payload["requests_total"], 3)
        self.assertEqual(payload["routes"]["/healthz"]["requests"], 1)
        self.assertIsNotNone(payload["database"]["last_success_at"])
        self.assertNotIn(str(self.user_id), json.dumps(payload))

    async def test_operations_alert_loop_notifies_admin_on_failure_and_recovery(self):
        from unittest.mock import AsyncMock

        main.ADMIN_IDS = {self.user_id}
        calls = 0

        async def fake_healthcheck():
            nonlocal calls
            calls += 1
            main.runtime_monitor.record_database_probe(
                calls > 1,
                None if calls > 1 else "test outage",
            )
            return calls > 1

        bot = type("FakeBot", (), {})()
        bot.send_message = AsyncMock()
        sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])
        with patch("main.database_healthcheck", new=fake_healthcheck), patch(
            "main.asyncio.sleep", new=sleep
        ):
            with self.assertRaises(asyncio.CancelledError):
                await main.operations_alert_loop(bot)

        self.assertEqual(bot.send_message.await_count, 2)
        messages = [call.args[1] for call in bot.send_message.await_args_list]
        self.assertIn("database is unavailable", messages[0])
        self.assertIn("database connection recovered", messages[1])

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

    async def test_http_exploration_can_start_encounters_inside_an_active_dungeon(self):
        await main.db.execute(
            "INSERT INTO dungeon_runs(user_id,dungeon_id,room,status) VALUES(?,1,1,'active')",
            (self.user_id,),
        )
        await main.db.commit()

        response = await self.client.post(
            "/api/explore", json={"monster_level": 1}, headers=self.headers
        )
        self.assertEqual(response.status, 200)
        payload = await response.json()
        self.assertTrue(payload["state"]["battle_active"])
        cur = await main.db.execute("SELECT monster_level FROM battles WHERE user_id=?", (self.user_id,))
        self.assertEqual((await cur.fetchone())["monster_level"], 1)

    async def test_http_dungeon_entry_rejects_a_live_matchmaking_queue(self):
        await main.db.execute(
            """INSERT INTO matchmaking_queue(
                 user_id,mode,player_level,rating,status,queued_at,updated_at
               ) VALUES(?,'casual',1,1000,'queued',?,?)""",
            (self.user_id, int(time.time()), int(time.time())),
        )
        await main.db.commit()

        response = await self.client.post(
            "/api/dungeon", json={"action": "enter", "dungeon_id": 1}, headers=self.headers
        )
        self.assertEqual(response.status, 409)
        self.assertIn("PvP queue", (await response.json())["error"])
        cur = await main.db.execute("SELECT 1 FROM dungeon_runs WHERE user_id=?", (self.user_id,))
        self.assertIsNone(await cur.fetchone())

    async def test_http_rate_limit_middleware_blocks_authenticated_request(self):
        with patch.object(main.database_api_rate_limiter, "allow", new=AsyncMock(return_value=(False, 9))):
            response = await self.client.get("/api/state", headers=self.headers)
        self.assertEqual(response.status, 429)
        self.assertEqual(response.headers.get("Retry-After"), "9")
        self.assertIn("Too many requests", (await response.json())["error"])


    async def test_settings_endpoint_rejects_unsupported_http_methods(self):
        for method in ("HEAD", "PUT", "PATCH", "DELETE"):
            response = await self.client.request(
                method, "/api/settings", headers=self.headers, json={"sound_enabled": False}
            )
            self.assertEqual(response.status, 405, method)
            self.assertIn("GET", response.headers.get("Allow", ""))
            self.assertIn("POST", response.headers.get("Allow", ""))

    async def test_miniapp_static_entrypoint_is_served_by_http_application(self):
        response = await self.client.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("text/html", response.headers.get("Content-Type", ""))

        pathfinding = await self.client.get("/pathfinding.js")
        self.assertEqual(pathfinding.status, 200)
        self.assertIn("javascript", pathfinding.headers.get("Content-Type", ""))
        self.assertIn("PeakPathfinding", await pathfinding.text())


if __name__ == "__main__":
    unittest.main()
