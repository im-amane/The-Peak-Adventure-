import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from party_system import create_party


class FakeRequest:
    def __init__(self, payload):
        self.headers = {"X-Telegram-Init-Data": "signed-test-data"}
        self.content_length = len(json.dumps(payload).encode("utf-8"))
        self._payload = payload

    async def json(self):
        return self._payload


class MiniAppSocialApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "social-api-test.db")
        main.db = None
        await main.init_db()

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()


    async def test_trade_invitation_can_only_be_answered_by_invited_player(self):
        initiator_id = 987654911
        partner_id = 987654912
        await main.get_player(initiator_id, "TradeInitiator")
        await main.get_player(partner_id, "TradePartner")
        cur = await main.db.execute(
            "INSERT INTO trades(chat_id,initiator_id,partner_id,status) VALUES(?,?,?,'pending')",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "TradeInitiator"}):
            denied = await main.api_social(FakeRequest({"action": "trade_accept", "trade_id": trade_id}))
        self.assertEqual(denied.status, 409)

        with patch("main.validate_init_data", return_value={"id": partner_id, "first_name": "TradePartner"}):
            accepted = await main.api_social(FakeRequest({"action": "trade_accept", "trade_id": trade_id}))
        self.assertEqual(accepted.status, 200)
        payload = json.loads(accepted.text)
        self.assertEqual(payload["result"]["status"], "open")

        cur = await main.db.execute("SELECT status FROM trades WHERE trade_id=?", (trade_id,))
        self.assertEqual((await cur.fetchone())["status"], "open")

    async def test_trade_invitation_can_be_created_only_for_an_accepted_friend(self):
        initiator_id = 987654919
        friend_id = 987654920
        stranger_id = 987654921
        for user_id, username in (
            (initiator_id, "TradeInitiator"),
            (friend_id, "TradeFriend"),
            (stranger_id, "TradeStranger"),
        ):
            await main.get_player(user_id, username)
            await main.db.execute(
                "UPDATE players SET class_selected=1 WHERE user_id=?", (user_id,)
            )
        low_id, high_id = sorted((initiator_id, friend_id))
        await main.db.execute(
            """INSERT INTO friend_requests(user_low,user_high,requester_id,target_id,status)
               VALUES(?,?,?,?, 'accepted')""",
            (low_id, high_id, initiator_id, friend_id),
        )
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "TradeInitiator"}):
            created = await main.api_social(FakeRequest({"action": "trade_create", "target_id": friend_id}))
            denied = await main.api_social(FakeRequest({"action": "trade_create", "target_id": stranger_id}))
        self.assertEqual(created.status, 200)
        created_payload = json.loads(created.text)["result"]
        self.assertEqual(created_payload["status"], "pending")
        self.assertEqual(denied.status, 409)

        cur = await main.db.execute(
            "SELECT initiator_id,partner_id,status FROM trades WHERE trade_id=?",
            (created_payload["trade_id"],),
        )
        trade = await cur.fetchone()
        self.assertEqual((trade["initiator_id"], trade["partner_id"], trade["status"]),
                         (initiator_id, friend_id, "pending"))

    async def test_trade_creation_rejects_self_and_invalid_target(self):
        user_id = 987654922
        await main.get_player(user_id, "TradeSelf")
        with patch("main.validate_init_data", return_value={"id": user_id, "first_name": "TradeSelf"}):
            self_response = await main.api_social(FakeRequest({"action": "trade_create", "target_id": user_id}))
            invalid_response = await main.api_social(FakeRequest({"action": "trade_create", "target_id": True}))
        self.assertEqual(self_response.status, 400)
        self.assertEqual(invalid_response.status, 400)

    async def test_trade_can_only_be_cancelled_by_a_participant(self):
        initiator_id = 987654914
        partner_id = 987654915
        outsider_id = 987654916
        for user_id, username in (
            (initiator_id, "TradeInitiator"),
            (partner_id, "TradePartner"),
            (outsider_id, "TradeOutsider"),
        ):
            await main.get_player(user_id, username)
        cur = await main.db.execute(
            "INSERT INTO trades(chat_id,initiator_id,partner_id,status) VALUES(?,?,?,'pending')",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": outsider_id, "first_name": "TradeOutsider"}):
            denied = await main.api_social(FakeRequest({"action": "trade_cancel", "trade_id": trade_id}))
        self.assertEqual(denied.status, 409)

        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "TradeInitiator"}):
            cancelled = await main.api_social(FakeRequest({"action": "trade_cancel", "trade_id": trade_id}))
        self.assertEqual(cancelled.status, 200)
        self.assertEqual(json.loads(cancelled.text)["result"]["status"], "cancelled")
        cur = await main.db.execute("SELECT status FROM trades WHERE trade_id=?", (trade_id,))
        self.assertEqual((await cur.fetchone())["status"], "cancelled")

    async def test_trade_cannot_be_cancelled_twice(self):
        initiator_id = 987654917
        partner_id = 987654918
        await main.get_player(initiator_id, "TradeInitiator")
        await main.get_player(partner_id, "TradePartner")
        cur = await main.db.execute(
            "INSERT INTO trades(chat_id,initiator_id,partner_id,status) VALUES(?,?,?,'cancelled')",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()
        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "TradeInitiator"}):
            response = await main.api_social(FakeRequest({"action": "trade_cancel", "trade_id": trade_id}))
        self.assertEqual(response.status, 409)

    async def test_trade_response_rejects_invalid_payload(self):
        partner_id = 987654913
        await main.get_player(partner_id, "TradePartner")
        with patch("main.validate_init_data", return_value={"id": partner_id, "first_name": "TradePartner"}):
            response = await main.api_social(FakeRequest({"action": "trade_decline", "trade_id": True}))
        self.assertEqual(response.status, 400)

    async def test_party_invite_does_not_create_unknown_player(self):
        leader_id = 987654901
        unknown_target_id = 987654902
        await main.get_player(leader_id, "PartyLeader")
        await main.db.execute(
            "UPDATE players SET class_selected=1, hero_class='Knight' WHERE user_id=?",
            (leader_id,),
        )
        await main.db.commit()
        await create_party(main.db, leader_id)

        request = FakeRequest({
            "action": "party_invite",
            "target_id": unknown_target_id,
        })
        with patch("main.validate_init_data", return_value={
            "id": leader_id,
            "first_name": "PartyLeader",
        }):
            response = await main.api_social(request)

        self.assertEqual(response.status, 409)
        self.assertIn("has not joined", json.loads(response.text)["error"])
        cur = await main.db.execute(
            "SELECT 1 FROM players WHERE user_id=?",
            (unknown_target_id,),
        )
        self.assertIsNone(await cur.fetchone())


if __name__ == "__main__":
    unittest.main()
