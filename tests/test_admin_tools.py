import unittest
import sqlite3
import aiosqlite
from admin_tools import AdminError, adjust_player_coins, dashboard_stats, export_player_data, init_admin_tables, parse_admin_ids, perform_audited_action, recent_admin_actions

class AdminToolsTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:"); self.db.row_factory=aiosqlite.Row
  await self.db.executescript("""
  CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER DEFAULT 0);
  CREATE TABLE battles(user_id INTEGER PRIMARY KEY);
  CREATE TABLE guilds(guild_id INTEGER PRIMARY KEY);
  CREATE TABLE group_profiles(chat_id INTEGER PRIMARY KEY,owner_id INTEGER);
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
 async def test_coin_adjustment_cannot_overflow_database_integer_balance(self):
  await self.db.execute("UPDATE players SET coins=? WHERE user_id=101",((1<<63)-1,))
  await self.db.commit()
  with self.assertRaisesRegex(AdminError,"maximum supported coin balance"):
   await adjust_player_coins(self.db,101,1)
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=101")
  self.assertEqual((await cur.fetchone())["coins"],(1<<63)-1)

 async def test_coin_adjustment_is_audited(self):
  await adjust_player_coins(self.db,101,10,999)
  logs=await recent_admin_actions(self.db)
  self.assertEqual(logs[0]["action"],"coin_adjustment")
  self.assertEqual(logs[0]["actor_id"],999)
 async def test_dashboard_counts(self):
  self.assertEqual(await dashboard_stats(self.db),{"players":1,"active_battles":0,"guilds":0,"registered_groups":0,"active_duels":0,"security_events_24h":0,"stars_received":0,"premium_gems_issued":0})
 async def test_player_export_includes_social_economy_and_matchmaking_data(self):
  await self.db.executescript("""
  CREATE TABLE trades(trade_id INTEGER PRIMARY KEY,initiator_id INTEGER,partner_id INTEGER);
  CREATE TABLE auction_listings(listing_id INTEGER PRIMARY KEY,seller_id INTEGER,highest_bidder INTEGER);
  CREATE TABLE auction_stash(stash_id INTEGER PRIMARY KEY,user_id INTEGER);
  CREATE TABLE matchmaking_matches(match_id INTEGER PRIMARY KEY,player_one_id INTEGER,player_two_id INTEGER);
  CREATE TABLE matchmaking_queue(user_id INTEGER,status TEXT,match_id INTEGER);
  CREATE TABLE matchmaking_rate_limits(user_id INTEGER,last_joined_at INTEGER);
  CREATE TABLE matchmaking_battles(match_id INTEGER);
  CREATE TABLE matchmaking_battle_stats(match_id INTEGER,user_id INTEGER);
  CREATE TABLE party_members(user_id INTEGER,party_id INTEGER);
  CREATE TABLE party_invites(invite_id INTEGER,inviter_id INTEGER,target_id INTEGER);
  CREATE TABLE party_battle_contributions(user_id INTEGER,battle_id INTEGER);
  CREATE TABLE party_battle_cooldowns(user_id INTEGER,battle_id INTEGER);
  CREATE TABLE party_battle_rewards(user_id INTEGER,battle_id INTEGER);
  CREATE TABLE guild_members(user_id INTEGER,guild_id INTEGER);
  CREATE TABLE guild_invites(invite_id INTEGER,inviter_id INTEGER,target_id INTEGER);
  CREATE TABLE guild_chat_messages(message_id INTEGER,user_id INTEGER);
  CREATE TABLE guild_announcements(guild_id INTEGER,author_id INTEGER);
  CREATE TABLE guild_raid_contributions(user_id INTEGER,raid_id INTEGER);
  CREATE TABLE guild_raid_cooldowns(user_id INTEGER,raid_id INTEGER);
  CREATE TABLE guild_war_duel_events(duel_id INTEGER,winner_id INTEGER);
  CREATE TABLE group_admins(user_id INTEGER,chat_id INTEGER);
  CREATE TABLE group_players(user_id INTEGER,chat_id INTEGER);
  CREATE TABLE group_bans(user_id INTEGER,actor_id INTEGER,chat_id INTEGER);
  CREATE TABLE group_raid_contributions(user_id INTEGER,raid_id INTEGER);
  CREATE TABLE group_raid_cooldowns(user_id INTEGER,raid_id INTEGER);
  CREATE TABLE player_reports(report_id INTEGER,reporter_id INTEGER,target_id INTEGER);
  CREATE TABLE player_bans(user_id INTEGER);
  INSERT INTO trades VALUES(1,101,202);
  INSERT INTO auction_listings VALUES(1,101,202);
  INSERT INTO auction_stash VALUES(1,101);
  INSERT INTO matchmaking_matches VALUES(1,101,202);
  INSERT INTO matchmaking_queue VALUES(101,'matched',1);
  INSERT INTO matchmaking_rate_limits VALUES(101,123);
  INSERT INTO matchmaking_battles VALUES(1);
  INSERT INTO matchmaking_battle_stats VALUES(1,101);
  INSERT INTO party_members VALUES(101,7);
  INSERT INTO party_invites VALUES(1,101,202);
  INSERT INTO party_battle_contributions VALUES(101,8);
  INSERT INTO party_battle_cooldowns VALUES(101,8);
  INSERT INTO party_battle_rewards VALUES(101,8);
  INSERT INTO guild_members VALUES(101,9);
  INSERT INTO guild_invites VALUES(1,101,202);
  INSERT INTO guild_chat_messages VALUES(1,101);
  INSERT INTO guild_announcements VALUES(9,101);
  INSERT INTO guild_raid_contributions VALUES(101,10);
  INSERT INTO guild_raid_cooldowns VALUES(101,10);
  INSERT INTO guild_war_duel_events VALUES(1,101);
  INSERT INTO group_profiles VALUES(-100,101);
  INSERT INTO group_admins VALUES(101,-100);
  INSERT INTO group_players VALUES(101,-100);
  INSERT INTO group_bans VALUES(101,101,-100);
  INSERT INTO group_raid_contributions VALUES(101,11);
  INSERT INTO group_raid_cooldowns VALUES(101,11);
  INSERT INTO player_reports VALUES(1,101,202);
  INSERT INTO player_bans VALUES(101);
  """)
  data=await export_player_data(self.db,101)
  for key in (
   "trades","auction_listings","auction_stash","matchmaking_queue",
   "matchmaking_rate_limits","matchmaking_matches","matchmaking_battles",
   "matchmaking_battle_stats","party_memberships","party_invites",
   "party_battle_contributions","party_battle_cooldowns","party_battle_rewards",
   "guild_memberships","guild_invites","guild_chat_messages","guild_announcements",
   "guild_raid_contributions","guild_raid_cooldowns","guild_war_duel_events",
   "group_profiles_owned","group_admin_roles","group_memberships","group_bans",
   "group_raid_contributions","group_raid_cooldowns","player_reports","player_bans",
  ):
   self.assertTrue(data["data"][key],key)

 async def test_player_export_contains_account_data(self):
  data=await export_player_data(self.db,101)
  self.assertEqual(data["data"]["profile"][0]["coins"],50)
  self.assertEqual(data["data"]["security_events"],[])
  self.assertEqual(data["data"]["secret_areas"],[])
  self.assertEqual(data["data"]["premium_wallet"],[])
  self.assertEqual(data["data"]["premium_transactions"],[])
  with self.assertRaises(AdminError): await export_player_data(self.db,202)

 async def test_audited_admin_action_rolls_back_mutation_if_log_fails(self):
  await self.db.execute("CREATE TRIGGER reject_admin_audit BEFORE INSERT ON admin_audit_log BEGIN SELECT RAISE(ABORT,'audit unavailable'); END")
  await self.db.commit()
  async def mutation():
   await self.db.execute("UPDATE players SET coins=coins+10 WHERE user_id=101")
   return True
  with self.assertRaisesRegex(AdminError,"could not be recorded; the change was rolled back"):
   await perform_audited_action(self.db,999,"test_mutation",101,mutation,"test")
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=101")
  self.assertEqual((await cur.fetchone())[0],50)
  self.assertEqual(await recent_admin_actions(self.db),[])

 async def test_audited_admin_action_preserves_outer_transaction(self):
  await self.db.execute("BEGIN")
  async def mutation():
   await self.db.execute("UPDATE players SET coins=coins+10 WHERE user_id=101")
   return True
  self.assertTrue(await perform_audited_action(self.db,999,"test_mutation",101,mutation,"test"))
  self.assertTrue(self.db.in_transaction)
  await self.db.rollback()
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=101")
  self.assertEqual((await cur.fetchone())[0],50)
  self.assertEqual(await recent_admin_actions(self.db),[])
 async def test_coin_adjustment_preserves_outer_transaction(self):
  await self.db.execute("BEGIN")
  self.assertEqual(await adjust_player_coins(self.db,101,25,999),75)
  self.assertTrue(self.db.in_transaction)
  await self.db.rollback()
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=101")
  self.assertEqual((await cur.fetchone())[0],50)
  self.assertEqual(await recent_admin_actions(self.db),[])

 async def test_audit_failure_rolls_back_coin_adjustment(self):
  await self.db.execute("CREATE TRIGGER reject_admin_audit BEFORE INSERT ON admin_audit_log BEGIN SELECT RAISE(ABORT,'audit unavailable'); END")
  await self.db.commit()
  with self.assertRaisesRegex(AdminError,"could not be recorded; the change was rolled back"):
   await adjust_player_coins(self.db,101,25,999)
  self.assertFalse(self.db.in_transaction)
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=101")
  self.assertEqual((await cur.fetchone())[0],50)
  self.assertEqual(await recent_admin_actions(self.db),[])

 async def test_ignored_coin_update_is_not_reported_as_success(self):
  await self.db.execute("CREATE TRIGGER ignore_admin_coin_update BEFORE UPDATE OF coins ON players WHEN OLD.user_id=101 BEGIN SELECT RAISE(IGNORE); END")
  await self.db.commit()
  with self.assertRaisesRegex(AdminError,"balance changed"):
   await adjust_player_coins(self.db,101,25)
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=101")
  self.assertEqual((await cur.fetchone())[0],50)

 async def test_invalid_audit_actor_does_not_change_balance(self):
  with self.assertRaises(AdminError):
   await adjust_player_coins(self.db,101,25,True)
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=101")
  self.assertEqual((await cur.fetchone())[0],50)

 async def test_admin_table_initialization_preserves_outer_transaction(self):
  db=await aiosqlite.connect(":memory:")
  try:
   await db.execute("CREATE TABLE marker(value INTEGER)")
   await db.execute("BEGIN")
   await db.execute("INSERT INTO marker VALUES(1)")
   await init_admin_tables(db)
   self.assertTrue(db.in_transaction)
   await db.rollback()
   cur=await db.execute("SELECT COUNT(*) FROM marker")
   self.assertEqual((await cur.fetchone())[0],0)
   cur=await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admin_audit_log'")
   self.assertIsNone(await cur.fetchone())
  finally:
   await db.close()
if __name__=="__main__": unittest.main()
