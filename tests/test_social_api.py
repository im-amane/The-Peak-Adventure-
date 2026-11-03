import json
import tempfile
import time
import unittest
from types import SimpleNamespace
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


class FakeCallbackMessage:
    def __init__(self):
        self.text = None

    async def edit_text(self, text):
        self.text = text


class FakeCallback:
    def __init__(self, user_id, data):
        from types import SimpleNamespace
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.message = FakeCallbackMessage()
        self.answer_args = None

    async def answer(self, *args, **kwargs):
        self.answer_args = (args, kwargs)


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


    async def test_abandoned_trades_expire_without_affecting_recent_trades(self):
        initiator_id = 987654940
        partner_id = 987654941
        await main.get_player(initiator_id, "TradeInitiator")
        await main.get_player(partner_id, "TradePartner")
        stale_pending = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,created_at)
               VALUES(?,?,?,'pending',datetime('now','-25 hours'))""",
            (-100123, initiator_id, partner_id),
        )
        stale_open = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,created_at)
               VALUES(?,?,?,'open',datetime('now','-2 days'))""",
            (-100123, partner_id, initiator_id),
        )
        recent = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,created_at)
               VALUES(?,?,?,'pending',datetime('now','-23 hours'))""",
            (-100123, initiator_id, partner_id),
        )
        await main.db.commit()

        expired_count = await main.expire_stale_trades()
        self.assertEqual(expired_count, 2)
        cur = await main.db.execute(
            "SELECT trade_id,status FROM trades WHERE trade_id IN (?,?,?)",
            (stale_pending.lastrowid, stale_open.lastrowid, recent.lastrowid),
        )
        statuses = {row["trade_id"]: row["status"] for row in await cur.fetchall()}
        self.assertEqual(statuses[stale_pending.lastrowid], "expired")
        self.assertEqual(statuses[stale_open.lastrowid], "expired")
        self.assertEqual(statuses[recent.lastrowid], "pending")

    async def test_expiry_preserves_caller_owned_transaction(self):
        initiator_id = 987654952
        partner_id = 987654953
        await main.get_player(initiator_id, "TradeInitiator")
        await main.get_player(partner_id, "TradePartner")
        cur = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,created_at)
               VALUES(?,?,?,'pending',datetime('now','-2 days'))""",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()
        await main.db.execute("UPDATE players SET coins=coins WHERE user_id=?", (initiator_id,))

        self.assertEqual(await main.expire_stale_trades(), 1)
        self.assertTrue(main.db.in_transaction)
        await main.db.rollback()
        cur = await main.db.execute("SELECT status FROM trades WHERE trade_id=?", (trade_id,))
        self.assertEqual((await cur.fetchone())["status"], "pending")

    async def test_telegram_trade_callback_cannot_accept_expired_invitation(self):
        initiator_id = 987654954
        partner_id = 987654955
        await main.get_player(initiator_id, "TradeInitiator")
        await main.get_player(partner_id, "TradePartner")
        cur = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,created_at)
               VALUES(?,?,?,'pending',datetime('now','-2 days'))""",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()

        callback = FakeCallback(partner_id, f"trade_accept:{trade_id}")
        await main.accept_trade(callback)

        self.assertIsNotNone(callback.answer_args)
        self.assertTrue(callback.answer_args[1].get("show_alert"))
        cur = await main.db.execute("SELECT status FROM trades WHERE trade_id=?", (trade_id,))
        self.assertEqual((await cur.fetchone())["status"], "expired")

    async def test_expired_trade_invitation_cannot_be_accepted(self):
        initiator_id = 987654942
        partner_id = 987654943
        await main.get_player(initiator_id, "TradeInitiator")
        await main.get_player(partner_id, "TradePartner")
        cur = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,created_at)
               VALUES(?,?,?,'pending',datetime('now','-3 days'))""",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": partner_id, "first_name": "TradePartner"}):
            response = await main.api_social(FakeRequest({"action": "trade_accept", "trade_id": trade_id}))
        self.assertEqual(response.status, 409)
        cur = await main.db.execute("SELECT status FROM trades WHERE trade_id=?", (trade_id,))
        self.assertEqual((await cur.fetchone())["status"], "expired")

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

    async def test_trade_confirmation_rejects_changed_equipment_without_transferring_assets(self):
        initiator_id = 987654928
        partner_id = 987654929
        await main.get_player(initiator_id, "TradeInitiator")
        await main.get_player(partner_id, "TradePartner")
        await main.db.execute(
            "UPDATE players SET coins=100,weapon='Rusty Sword',weapon_attack=0 WHERE user_id=?",
            (initiator_id,),
        )
        await main.db.execute(
            "UPDATE players SET coins=50,weapon='Rusty Sword',weapon_attack=0 WHERE user_id=?",
            (partner_id,),
        )
        cur = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,
               initiator_coins,partner_coins,initiator_weapon,initiator_weapon_attack,
               partner_weapon,partner_weapon_attack)
               VALUES(?,?,?,'open',10,20,'Changed Blade',12,'Rusty Sword',0)""",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "TradeInitiator"}):
            first = await main.api_social(FakeRequest({"action": "trade_confirm", "trade_id": trade_id}))
        with patch("main.validate_init_data", return_value={"id": partner_id, "first_name": "TradePartner"}):
            rejected = await main.api_social(FakeRequest({"action": "trade_confirm", "trade_id": trade_id}))
        self.assertEqual(first.status, 200)
        self.assertEqual(rejected.status, 409)

        cur = await main.db.execute(
            "SELECT status,initiator_confirmed,partner_confirmed FROM trades WHERE trade_id=?",
            (trade_id,),
        )
        trade = await cur.fetchone()
        self.assertEqual((trade["status"],trade["initiator_confirmed"],trade["partner_confirmed"]), ("open",0,0))
        cur = await main.db.execute("SELECT coins FROM players WHERE user_id=?", (initiator_id,))
        self.assertEqual((await cur.fetchone())["coins"], 100)
        cur = await main.db.execute("SELECT coins FROM players WHERE user_id=?", (partner_id,))
        self.assertEqual((await cur.fetchone())["coins"], 50)

    async def test_trade_offer_checks_balance_and_resets_confirmations(self):
        initiator_id = 987654923
        partner_id = 987654924
        outsider_id = 987654925
        for user_id, username in (
            (initiator_id, "TradeInitiator"),
            (partner_id, "TradePartner"),
            (outsider_id, "TradeOutsider"),
        ):
            await main.get_player(user_id, username)
        await main.db.execute(
            "UPDATE players SET coins=100,potions=5 WHERE user_id=?", (initiator_id,)
        )
        cur = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,
               initiator_confirmed,partner_confirmed) VALUES(?,?,?,'open',1,1)""",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "TradeInitiator"}):
            saved = await main.api_social(FakeRequest({
                "action": "trade_offer", "trade_id": trade_id, "coins": 25, "potions": 2,
                "offer_weapon": True, "offer_armor": False,
            }))
            too_much = await main.api_social(FakeRequest({
                "action": "trade_offer", "trade_id": trade_id, "coins": 101, "potions": 0,
                "offer_weapon": False, "offer_armor": False,
            }))
        with patch("main.validate_init_data", return_value={"id": outsider_id, "first_name": "TradeOutsider"}):
            denied = await main.api_social(FakeRequest({
                "action": "trade_offer", "trade_id": trade_id, "coins": 1, "potions": 0,
                "offer_weapon": False, "offer_armor": False,
            }))
        self.assertEqual(saved.status, 200)
        self.assertEqual(too_much.status, 409)
        self.assertEqual(denied.status, 409)
        events = await main.get_security_events(main.db, outsider_id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "invalid_economy_action")
        self.assertEqual(events[0]["severity"], 4)
        self.assertIn("trade access by non-participant", events[0]["details"])
        cur = await main.db.execute(
            "SELECT initiator_coins,initiator_potions,initiator_weapon,initiator_armor,initiator_confirmed,partner_confirmed FROM trades WHERE trade_id=?",
            (trade_id,),
        )
        trade = await cur.fetchone()
        self.assertEqual(
            (trade["initiator_coins"],trade["initiator_potions"],trade["initiator_weapon"],trade["initiator_armor"],trade["initiator_confirmed"],trade["partner_confirmed"]),
            (25,2,"Rusty Sword",None,0,0),
        )

    async def test_party_raid_requires_stamina_and_reports_shortage(self):
        user_id = 987654940
        await main.get_player(user_id, "RaidLeader")
        await main.db.execute("UPDATE players SET class_selected=1 WHERE user_id=?", (user_id,))
        party_id = await main.create_party(main.db, user_id)
        await main.get_stamina(main.db, user_id)
        await main.db.execute("UPDATE player_stamina SET stamina=0 WHERE user_id=?", (user_id,))
        await main.db.commit()

        class FakePartyMessage:
            text = "/party battle start"
            from_user = SimpleNamespace(id=user_id, username="RaidLeader", full_name="Raid Leader")
            responses = []

            async def answer(self, text, **kwargs):
                self.responses.append(text)

        message = FakePartyMessage()
        message.responses = []
        await main.party_command(message)
        self.assertTrue(any("stamina" in response.lower() for response in message.responses))
        cur = await main.db.execute("SELECT 1 FROM party_battles WHERE party_id=? AND status='active'", (party_id,))
        self.assertIsNone(await cur.fetchone())

        await main.db.execute("UPDATE player_stamina SET stamina=100,updated_at=? WHERE user_id=?", (int(time.time()), user_id))
        await main.db.commit()
        successful_message = FakePartyMessage()
        successful_message.responses = []
        await main.party_command(successful_message)
        cur = await main.db.execute("SELECT stamina FROM player_stamina WHERE user_id=?", (user_id,))
        self.assertEqual((await cur.fetchone())["stamina"], 90)
        cur = await main.db.execute("SELECT 1 FROM party_battles WHERE party_id=? AND status='active'", (party_id,))
        self.assertIsNotNone(await cur.fetchone())

    async def test_empty_trade_cannot_complete_or_farm_guild_mission_progress(self):
        initiator_id = 987654930
        partner_id = 987654931
        await main.get_player(initiator_id, "EmptyTradeInitiator")
        await main.get_player(partner_id, "EmptyTradePartner")
        cur = await main.db.execute(
            "INSERT INTO trades(chat_id,initiator_id,partner_id,status) VALUES(0,?,?,'open')",
            (initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "EmptyTradeInitiator"}):
            first = await main.api_social(FakeRequest({"action": "trade_confirm", "trade_id": trade_id}))
        self.assertEqual(first.status, 200)

        with patch("main.validate_init_data", return_value={"id": partner_id, "first_name": "EmptyTradePartner"}):
            second = await main.api_social(FakeRequest({"action": "trade_confirm", "trade_id": trade_id}))
        self.assertEqual(second.status, 409)
        self.assertIn("at least one item, coin, or potion", json.loads(second.text)["error"])

        cur = await main.db.execute(
            "SELECT status,initiator_confirmed,partner_confirmed FROM trades WHERE trade_id=?",
            (trade_id,),
        )
        state = await cur.fetchone()
        self.assertEqual((state["status"],state["initiator_confirmed"],state["partner_confirmed"]),("open",0,0))

    async def test_trade_confirmation_exchanges_balances_once(self):
        initiator_id = 987654926
        partner_id = 987654927
        await main.get_player(initiator_id, "TradeInitiator")
        await main.get_player(partner_id, "TradePartner")
        await main.db.execute(
            "UPDATE players SET coins=100,potions=5 WHERE user_id=?", (initiator_id,)
        )
        await main.db.execute(
            "UPDATE players SET coins=50,potions=2 WHERE user_id=?", (partner_id,)
        )
        cur = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,
               initiator_coins,initiator_potions,partner_coins,partner_potions)
               VALUES(?,?,?,'open',10,1,20,1)""",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "TradeInitiator"}):
            first = await main.api_social(FakeRequest({"action": "trade_confirm", "trade_id": trade_id}))
        self.assertEqual(first.status, 200)
        self.assertEqual(json.loads(first.text)["result"]["status"], "open")

        with patch("main.validate_init_data", return_value={"id": partner_id, "first_name": "TradePartner"}):
            second = await main.api_social(FakeRequest({"action": "trade_confirm", "trade_id": trade_id}))
            repeated = await main.api_social(FakeRequest({"action": "trade_confirm", "trade_id": trade_id}))
        self.assertEqual(second.status, 200)
        self.assertEqual(json.loads(second.text)["result"]["status"], "completed")
        self.assertEqual(repeated.status, 409)

        cur = await main.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (initiator_id,)
        )
        initiator = await cur.fetchone()
        cur = await main.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (partner_id,)
        )
        partner = await cur.fetchone()
        self.assertEqual((initiator["coins"],initiator["potions"]), (110,5))
        self.assertEqual((partner["coins"],partner["potions"]), (40,2))

    async def test_trade_settlement_rolls_back_both_players_if_second_update_fails(self):
        initiator_id = 987654950
        partner_id = 987654951
        await main.get_player(initiator_id, "TradeInitiator")
        await main.get_player(partner_id, "TradePartner")
        await main.db.execute(
            "UPDATE players SET coins=100,potions=5 WHERE user_id=?", (initiator_id,)
        )
        await main.db.execute(
            "UPDATE players SET coins=50,potions=2 WHERE user_id=?", (partner_id,)
        )
        cur = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,
               initiator_coins,initiator_potions,partner_coins,partner_potions)
               VALUES(?,?,?,'open',10,1,20,1)""",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()
        await main.db.execute(
            f"""CREATE TRIGGER reject_partner_trade_update
                BEFORE UPDATE OF coins,potions,weapon,weapon_attack,armor,armor_defense ON players
                WHEN OLD.user_id={partner_id}
                BEGIN SELECT RAISE(IGNORE); END"""
        )
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "TradeInitiator"}):
            first = await main.api_social(FakeRequest({"action": "trade_confirm", "trade_id": trade_id}))
        with patch("main.validate_init_data", return_value={"id": partner_id, "first_name": "TradePartner"}):
            second = await main.api_social(FakeRequest({"action": "trade_confirm", "trade_id": trade_id}))

        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 409)
        cur = await main.db.execute(
            "SELECT status,initiator_confirmed,partner_confirmed FROM trades WHERE trade_id=?",
            (trade_id,),
        )
        trade = await cur.fetchone()
        self.assertEqual((trade["status"],trade["initiator_confirmed"],trade["partner_confirmed"]), ("open",0,0))
        cur = await main.db.execute("SELECT coins,potions FROM players WHERE user_id=?", (initiator_id,))
        self.assertEqual(tuple(await cur.fetchone()), (100,5))
        cur = await main.db.execute("SELECT coins,potions FROM players WHERE user_id=?", (partner_id,))
        self.assertEqual(tuple(await cur.fetchone()), (50,2))

    async def test_simultaneous_trade_confirmations_settle_exactly_once(self):
        initiator_id = 987654930
        partner_id = 987654931
        await main.get_player(initiator_id, "TradeInitiator")
        await main.get_player(partner_id, "TradePartner")
        await main.db.execute(
            "UPDATE players SET coins=100,potions=5 WHERE user_id=?", (initiator_id,)
        )
        await main.db.execute(
            "UPDATE players SET coins=50,potions=2 WHERE user_id=?", (partner_id,)
        )
        cur = await main.db.execute(
            """INSERT INTO trades(chat_id,initiator_id,partner_id,status,
               initiator_coins,initiator_potions,partner_coins,partner_potions)
               VALUES(?,?,?,'open',10,1,20,1)""",
            (-100123, initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.commit()

        initiator_request = FakeRequest({"action": "trade_confirm", "trade_id": trade_id})
        partner_request = FakeRequest({"action": "trade_confirm", "trade_id": trade_id})
        initiator_request.headers["X-Telegram-Init-Data"] = "initiator"
        partner_request.headers["X-Telegram-Init-Data"] = "partner"
        users = {
            "initiator": {"id": initiator_id, "first_name": "TradeInitiator"},
            "partner": {"id": partner_id, "first_name": "TradePartner"},
        }

        with patch("main.validate_init_data", side_effect=lambda token, _bot_token: users[token]):
            responses = await __import__("asyncio").gather(
                main.api_social(initiator_request),
                main.api_social(partner_request),
            )

        self.assertEqual([response.status for response in responses], [200, 200])
        cur = await main.db.execute(
            "SELECT status,initiator_confirmed,partner_confirmed FROM trades WHERE trade_id=?",
            (trade_id,),
        )
        trade = await cur.fetchone()
        self.assertEqual(
            (trade["status"],trade["initiator_confirmed"],trade["partner_confirmed"]),
            ("completed",1,1),
        )
        cur = await main.db.execute("SELECT coins,potions FROM players WHERE user_id=?", (initiator_id,))
        initiator = await cur.fetchone()
        cur = await main.db.execute("SELECT coins,potions FROM players WHERE user_id=?", (partner_id,))
        partner = await cur.fetchone()
        self.assertEqual((initiator["coins"],initiator["potions"]), (110,5))
        self.assertEqual((partner["coins"],partner["potions"]), (40,2))

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

    async def test_legacy_trade_invitation_cannot_be_accepted_during_active_battle(self):
        initiator_id = 987654932
        partner_id = 987654933
        await main.get_player(initiator_id, "LegacyTradeInitiator")
        await main.get_player(partner_id, "LegacyTradePartner")
        cur = await main.db.execute(
            "INSERT INTO trades(chat_id,initiator_id,partner_id,status) VALUES(0,?,?,'pending')",
            (initiator_id, partner_id),
        )
        trade_id = cur.lastrowid
        await main.db.execute(
            "INSERT INTO battles(user_id,monster_level,monster_hp) VALUES(?,?,?)",
            (initiator_id, 1, 100),
        )
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": partner_id, "first_name": "LegacyTradePartner"}):
            response = await main.api_social(FakeRequest({"action": "trade_accept", "trade_id": trade_id}))
        self.assertEqual(response.status, 409)
        cur = await main.db.execute("SELECT status FROM trades WHERE trade_id=?", (trade_id,))
        self.assertEqual((await cur.fetchone())["status"], "pending")

    async def test_trade_creation_rejects_players_in_battles_or_duels(self):
        initiator_id = 987654925
        friend_id = 987654926
        for user_id, username in ((initiator_id, "ModeInitiator"), (friend_id, "ModeFriend")):
            await main.get_player(user_id, username)
            await main.db.execute("UPDATE players SET class_selected=1 WHERE user_id=?", (user_id,))
        low_id, high_id = sorted((initiator_id, friend_id))
        await main.db.execute(
            """INSERT INTO friend_requests(user_low,user_high,requester_id,target_id,status)
               VALUES(?,?,?,?, 'accepted')""",
            (low_id, high_id, initiator_id, friend_id),
        )
        await main.db.execute("INSERT INTO battles(user_id,monster_level,monster_hp) VALUES(?,1,100)", (friend_id,))
        await main.db.commit()

        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "ModeInitiator"}):
            battle_blocked = await main.api_social(FakeRequest({"action": "trade_create", "target_id": friend_id}))
        self.assertEqual(battle_blocked.status, 409)

        await main.db.execute("DELETE FROM battles WHERE user_id=?", (friend_id,))
        await main.db.execute(
            """INSERT INTO duels(chat_id,challenger_id,opponent_id,challenger_hp,opponent_hp,status)
               VALUES(0,?,?,100,100,'pending')""",
            (friend_id, initiator_id),
        )
        await main.db.commit()
        with patch("main.validate_init_data", return_value={"id": initiator_id, "first_name": "ModeInitiator"}):
            duel_blocked = await main.api_social(FakeRequest({"action": "trade_create", "target_id": friend_id}))
        self.assertEqual(duel_blocked.status, 409)

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
