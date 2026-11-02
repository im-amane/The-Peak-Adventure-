"""Authenticated Mini App HTTP smoke tests against PostgreSQL 16."""
import hashlib
import hmac
import json
import os
import time
import unittest
import uuid
from urllib.parse import urlencode

from aiohttp.test_utils import TestClient, TestServer

import main
from postgres_adapter import PostgresConnection


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresMiniAppHttpIntegrationTests(unittest.IsolatedAsyncioTestCase):
    token = "987654:postgres-miniapp-http-token"
    user_id = 9_300_000_001

    def make_init_data(self):
        fields = {
            "auth_date": str(int(time.time())),
            "query_id": "AAPostgresMiniApp",
            "user": json.dumps(
                {"id": self.user_id, "first_name": "PostgresHero", "username": "postgres_hero"},
                separators=(",", ":"),
            ),
        }
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", self.token.encode(), hashlib.sha256).digest()
        fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        return urlencode(fields)

    async def asyncSetUp(self):
        self.previous_db = main.db
        self.previous_token = main.TOKEN
        self.previous_admin_ids = main.ADMIN_IDS
        self.previous_monitor = main.runtime_monitor
        self.schema = "peak_miniapp_http_" + uuid.uuid4().hex[:12]

        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute(f'CREATE SCHEMA "{self.schema}"')
        await self.db.commit()
        await self.db.execute(f'SET search_path TO "{self.schema}"')
        await self.db.commit()
        await main.init_game_schema(self.db)

        main.db = self.db
        main.TOKEN = self.token
        main.ADMIN_IDS = set()
        main.runtime_monitor = main.RuntimeMonitor()
        await main.get_player(self.user_id, "PostgresHero")
        await self.db.execute(
            """UPDATE players
               SET class_selected=1,hero_class='Knight',hp=100,max_hp=100
               WHERE user_id=?""",
            (self.user_id,),
        )
        await self.db.commit()

        self.client = TestClient(TestServer(main.create_web_app()))
        await self.client.start_server()
        self.headers = {"X-Telegram-Init-Data": self.make_init_data()}

    async def asyncTearDown(self):
        await self.client.close()
        if self.db.in_transaction:
            await self.db.rollback()
        await self.db.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await self.db.commit()
        await self.db.close()
        main.db = self.previous_db
        main.TOKEN = self.previous_token
        main.ADMIN_IDS = self.previous_admin_ids
        main.runtime_monitor = self.previous_monitor

    async def test_authenticated_explore_and_flee_roundtrip_on_postgres(self):
        state_response = await self.client.get("/api/state", headers=self.headers)
        self.assertEqual(state_response.status, 200)
        initial_state = await state_response.json()
        self.assertFalse(initial_state["battle_active"])

        explore_response = await self.client.post(
            "/api/explore",
            json={"monster_level": 1},
            headers=self.headers,
        )
        self.assertEqual(explore_response.status, 200)
        explored = await explore_response.json()
        self.assertTrue(explored["state"]["battle_active"])
        self.assertEqual(explored["state"]["battle"]["level"], 1)

        cursor = await self.db.execute(
            "SELECT monster_level FROM battles WHERE user_id=?",
            (self.user_id,),
        )
        battle = await cursor.fetchone()
        self.assertEqual(battle["monster_level"], 1)

        flee_response = await self.client.post(
            "/api/action",
            json={"action": "flee"},
            headers=self.headers,
        )
        self.assertEqual(flee_response.status, 200)
        fled = await flee_response.json()
        self.assertFalse(fled["state"]["battle_active"])

        cursor = await self.db.execute(
            "SELECT COUNT(*) AS count FROM battles WHERE user_id=?",
            (self.user_id,),
        )
        self.assertEqual((await cursor.fetchone())["count"], 0)

        cursor = await self.db.execute(
            "SELECT stamina FROM player_stamina WHERE user_id=?",
            (self.user_id,),
        )
        self.assertEqual((await cursor.fetchone())["stamina"], 95)


if __name__ == "__main__":
    unittest.main()
