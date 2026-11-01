import unittest
import aiosqlite
from admin_tools import AdminError, adjust_player_coins, dashboard_stats, export_player_data, init_admin_tables, parse_admin_ids, recent_admin_actions

class AdminToolsTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:"); self.db.row_factory=aiosqlite.Row
  await self.db.executescript("""
  CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER DEFAULT 0);
  CREATE TABLE battles(user_id INTEGER PRIMARY KEY);
  CREATE TABLE guilds(guild_id INTEGER PRIMARY KEY);
  CREATE TABLE group_profiles(chat_id INTEGER PRIMARY KEY);
  CREATE TABLE duels(duel_id INTEGER PRIMARY KEY,challenger_id INTEGER,opponent_id INTEGER,status TEXT);
  CREATE TABLE quest_progress(user_id INTEGER,quest_id TEXT);
  CREATE TABLE achievement_progress(user_id INTEGER,achievement_id TEXT);
  CREATE TABLE character_appearance(user_id INTEGER PRIMARY KEY,race TEXT);
  CREATE TABLE player_settings(user_id INTEGER PRIMARY KEY,notifications_enabled INTEGER,profile_visibility TEXT);
  CREATE TABLE friend_requests(user_low INTEGER,user_high INTEGER,status TEXT);
  CREATE TABLE player_materials(user_id INTEGER,material_id TEXT,quantity INTEGER);
  CREATE TABLE crafted_items(user_id INTEGER,recipe_id TEXT);
  CREATE TABLE player_worlds(user_id INTEGER,current_world INTEGER);
  CREATE TABLE player_presence(user_id INTEGER,last_seen TEXT);
  CREATE TABLE world_discoveries(user_id INTEGER,world_id INTEGER);
  CREATE TABLE player_story(user_id INTEGER,chapter_id INTEGER,choice_id TEXT);
  CREATE TABLE story_flags(user_id INTEGER,flag TEXT,value TEXT);
  CREATE TABLE story_reward_claims(user_id INTEGER,chapter_id INTEGER);
  CREATE TABLE dungeon_runs(user_id INTEGER,dungeon_id INTEGER);
  CREATE TABLE dungeon_rewards(user_id INTEGER,dungeon_id INTEGER);
  CREATE TABLE monster_discoveries(user_id INTEGER,monster_level INTEGER);
  CREATE TABLE boss_defeats(user_id INTEGER,monster_level INTEGER);
  INSERT INTO players VALUES(101,50);
  """)
  await init_admin_tables(self.db)
 async def asyncTearDown(self): await self.db.close()
 def test_admin_id_parser_ignores_bad_values(self):
  self.assertEqual(parse_admin_ids("101, abc, 202, -3,0,101"),{101,202})
 async def test_coin_adjustment_add_and_remove(self):
  self.assertEqual(await adjust_player_coins(self.db,101,25),75)
  self.assertEqual(await adjust_player_coins(self.db,101,-15),60)
 async def test_coin_adjustment_cannot_make_negative_balance(self):
  with self.assertRaises(AdminError): await adjust_player_coins(self.db,101,-100)
 async def test_coin_adjustment_rejects_boolean_and_extreme(self):
  for value in (True,100001,0):
   with self.assertRaises(AdminError): await adjust_player_coins(self.db,101,value)
 async def test_unknown_player_is_rejected(self):
  with self.assertRaises(AdminError): await adjust_player_coins(self.db,202,10)
 async def test_coin_adjustment_is_audited(self):
  await adjust_player_coins(self.db,101,10,999)
  logs=await recent_admin_actions(self.db)
  self.assertEqual(logs[0]["action"],"coin_adjustment")
  self.assertEqual(logs[0]["actor_id"],999)
 async def test_dashboard_counts(self):
  self.assertEqual(await dashboard_stats(self.db),{"players":1,"active_battles":0,"guilds":0,"registered_groups":0,"active_duels":0,"security_events_24h":0,"stars_received":0,"premium_gems_issued":0})
 async def test_player_export_contains_account_data(self):
  data=await export_player_data(self.db,101)
  self.assertEqual(data["data"]["profile"][0]["coins"],50)
  self.assertEqual(data["data"]["security_events"],[])
  self.assertEqual(data["data"]["secret_areas"],[])
  self.assertEqual(data["data"]["premium_wallet"],[])
  self.assertEqual(data["data"]["premium_transactions"],[])
  with self.assertRaises(AdminError): await export_player_data(self.db,202)

if __name__=="__main__": unittest.main()
