import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class FakeRequest:
    def __init__(self, payload):
        self.headers = {"X-Telegram-Init-Data": "signed-test-data"}
        self.content_length = len(json.dumps(payload).encode("utf-8"))
        self._payload = payload

    async def json(self):
        return self._payload


class MiniAppValidationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "validation-test.db")
        main.db = None
        await main.init_db()
        self.user = {"id": 987654990, "first_name": "ValidationHero"}
        await main.get_player(self.user["id"], self.user["first_name"])

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def _call(self, handler, payload):
        with patch("main.validate_init_data", return_value=self.user):
            return await handler(FakeRequest(payload))

    async def _assert_event(self, event_type):
        cur = await main.db.execute(
            "SELECT event_type FROM security_events WHERE user_id=? ORDER BY event_id DESC LIMIT 1",
            (self.user["id"],),
        )
        row = await cur.fetchone()
        self.assertEqual(row["event_type"], event_type)

    async def test_miniapp_attack_executes_and_advances_active_battle(self):
        user_id = self.user["id"]
        await main.db.execute(
            "UPDATE players SET class_selected=1,hp=100,max_hp=100,armor_defense=1000 WHERE user_id=?",
            (user_id,),
        )
        await main.db.execute(
            """INSERT INTO battles(user_id,monster_level,monster_hp,turn_count,is_elite,is_evolved)
               VALUES(?,1,77,0,0,0)""",
            (user_id,),
        )
        await main.db.commit()

        response = await self._call(main.api_action, {"action": "attack"})
        self.assertEqual(response.status, 200)
        payload = json.loads(response.text)
        self.assertIn("message", payload)
        self.assertIn("state", payload)
        cur = await main.db.execute(
            "SELECT turn_count,monster_hp FROM battles WHERE user_id=?",
            (user_id,),
        )
        battle = await cur.fetchone()
        self.assertEqual(battle["turn_count"], 1)
        self.assertLess(battle["monster_hp"], 77)
        player = await main.get_player(user_id)
        self.assertLess(player["hp"], 100)

    async def test_lethal_attack_keeps_battle_and_rewards_in_one_transaction(self):
        user_id = self.user["id"]
        await main.db.execute(
            "UPDATE players SET class_selected=1,hp=100,max_hp=100 WHERE user_id=?",
            (user_id,),
        )
        await main.db.execute(
            """INSERT INTO battles(user_id,monster_level,monster_hp,turn_count,is_elite,is_evolved)
               VALUES(?,1,1,0,0,0)""",
            (user_id,),
        )
        await main.db.commit()

        with patch("main.finish_battle", side_effect=RuntimeError("simulated reward failure")):
            with self.assertRaisesRegex(RuntimeError, "simulated reward failure"):
                await self._call(main.api_action, {"action": "attack"})

        self.assertTrue(main.db.in_transaction)
        await main.db.rollback()
        cur = await main.db.execute(
            "SELECT monster_hp,turn_count FROM battles WHERE user_id=?",
            (user_id,),
        )
        battle = await cur.fetchone()
        self.assertEqual((battle["monster_hp"],battle["turn_count"]), (1,0))
        player = await main.get_player(user_id)
        self.assertEqual(player["hp"], 100)
        cur = await main.db.execute("SELECT 1 FROM player_mana WHERE user_id=?", (user_id,))
        self.assertIsNone(await cur.fetchone())

    async def test_defeat_keeps_battle_and_mana_updates_in_one_transaction(self):
        user_id = self.user["id"]
        await main.db.execute(
            "UPDATE players SET class_selected=1,hp=100,max_hp=100 WHERE user_id=?",
            (user_id,),
        )
        await main.db.execute(
            """INSERT INTO battles(user_id,monster_level,monster_hp,turn_count,is_elite,is_evolved)
               VALUES(?,1,77,0,0,0)""",
            (user_id,),
        )
        await main.db.commit()
        defeated = {
            "monster_hp": 50, "enemy_damage": 100, "evaded": False,
            "special_turn": False, "reflect_damage": 0, "poison_damage": 0,
            "player_hp": 0, "effect_notes": [],
        }
        with patch("main.resolve_enemy_turn", return_value=defeated), patch(
            "main.finish_battle", side_effect=RuntimeError("simulated defeat finalization failure")
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated defeat finalization failure"):
                await self._call(main.api_action, {"action": "attack"})

        self.assertTrue(main.db.in_transaction)
        await main.db.rollback()
        cur = await main.db.execute(
            "SELECT monster_hp,turn_count FROM battles WHERE user_id=?",
            (user_id,),
        )
        battle = await cur.fetchone()
        self.assertEqual((battle["monster_hp"],battle["turn_count"]), (77,0))
        player = await main.get_player(user_id)
        self.assertEqual(player["hp"], 100)
        cur = await main.db.execute("SELECT 1 FROM player_mana WHERE user_id=?", (user_id,))
        self.assertIsNone(await cur.fetchone())

    async def test_coin_shop_rolls_back_debit_when_equipment_update_fails(self):
        user_id = self.user["id"]
        await main.db.execute(
            "UPDATE players SET class_selected=1,level=2,coins=100 WHERE user_id=?",
            (user_id,),
        )
        await main.db.execute(
            f"""CREATE TRIGGER reject_coin_shop_weapon
                BEFORE UPDATE OF weapon,weapon_attack ON players
                WHEN OLD.user_id={user_id}
                BEGIN SELECT RAISE(ABORT, 'equipment write unavailable'); END"""
        )
        await main.db.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            await main.buy_shop_item(user_id,"iron_sword")

        player=await main.get_player(user_id)
        self.assertEqual(player["coins"],100)
        self.assertEqual(player["weapon_attack"],0)

    async def test_coin_shop_rejects_ignored_inventory_update_without_charging(self):
        user_id = self.user["id"]
        await main.db.execute(
            "UPDATE players SET class_selected=1,level=2,coins=100 WHERE user_id=?",
            (user_id,),
        )
        await main.db.execute(
            f"""CREATE TRIGGER ignore_coin_shop_weapon
                BEFORE UPDATE OF weapon,weapon_attack ON players
                WHEN OLD.user_id={user_id}
                BEGIN SELECT RAISE(IGNORE); END"""
        )
        await main.db.commit()

        with self.assertRaisesRegex(main.ShopError,"No coins were deducted"):
            await main.buy_shop_item(user_id,"iron_sword")

        player=await main.get_player(user_id)
        self.assertEqual(player["coins"],100)
        self.assertEqual(player["weapon_attack"],0)

    async def test_coin_shop_potion_purchase_updates_inventory_and_wallet(self):
        user_id = self.user["id"]
        await main.db.execute(
            "UPDATE players SET class_selected=1,level=1,coins=100,potions=0 WHERE user_id=?",
            (user_id,),
        )
        await main.db.commit()

        item=await main.buy_shop_item(user_id,"health_potion")
        player=await main.get_player(user_id)
        self.assertEqual(item["name"],"Health Potion")
        self.assertEqual((player["coins"],player["potions"]),(75,1))

    async def test_coin_shop_purchase_preserves_outer_transaction(self):
        user_id = self.user["id"]
        await main.db.execute(
            "UPDATE players SET class_selected=1,level=1,coins=100,potions=0 WHERE user_id=?",
            (user_id,),
        )
        await main.db.commit()
        await main.db.execute("BEGIN")

        await main.buy_shop_item(user_id,"health_potion")

        self.assertTrue(main.db.in_transaction)
        await main.db.rollback()
        player=await main.get_player(user_id)
        self.assertEqual((player["coins"],player["potions"]),(100,0))

    async def test_unhashable_battle_action_returns_400_and_is_logged(self):
        response = await self._call(main.api_action, {"action": []})
        self.assertEqual(response.status, 400)
        await self._assert_event("invalid_battle_action")

    async def test_unhashable_dungeon_action_returns_400_and_is_logged(self):
        response = await self._call(main.api_dungeon, {"action": []})
        self.assertEqual(response.status, 400)
        await self._assert_event("invalid_dungeon_action")

    async def test_unhashable_story_action_returns_400_and_is_logged(self):
        response = await self._call(main.api_story, {"action": []})
        self.assertEqual(response.status, 400)
        await self._assert_event("invalid_story_action")

    async def test_unhashable_world_action_returns_400_and_is_logged(self):
        response = await self._call(main.api_world, {"action": []})
        self.assertEqual(response.status, 400)
        await self._assert_event("invalid_world_action")

    async def test_invalid_monster_level_is_logged(self):
        response = await self._call(main.api_explore, {"monster_level": []})
        self.assertEqual(response.status, 400)
        await self._assert_event("invalid_monster_request")


if __name__ == "__main__":
    unittest.main()
