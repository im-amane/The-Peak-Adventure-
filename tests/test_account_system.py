import unittest
import aiosqlite
from account_system import AccountError, delete_player_account, get_settings, init_account_tables, update_settings

class AccountSystemTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:"); self.db.row_factory=aiosqlite.Row
  await self.db.executescript("""
  CREATE TABLE players(user_id INTEGER PRIMARY KEY,username TEXT,level INTEGER,xp INTEGER);
  CREATE TABLE security_events(event_id INTEGER PRIMARY KEY,user_id INTEGER,event_type TEXT,severity INTEGER,details TEXT,created_at TEXT);
  CREATE TABLE guilds(guild_id INTEGER PRIMARY KEY,leader_id INTEGER);
  CREATE TABLE guild_members(user_id INTEGER PRIMARY KEY,guild_id INTEGER,role TEXT,joined_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE guild_invites(invite_id INTEGER PRIMARY KEY,inviter_id INTEGER,target_id INTEGER);
  CREATE TABLE guild_announcements(guild_id INTEGER PRIMARY KEY,message TEXT,author_id INTEGER);
  CREATE TABLE guild_raid_contributions(raid_id INTEGER,user_id INTEGER,damage INTEGER);
  CREATE TABLE guild_raid_cooldowns(raid_id INTEGER,user_id INTEGER,last_attack_at TEXT);
  CREATE TABLE group_profiles(chat_id INTEGER PRIMARY KEY,owner_id INTEGER);
  CREATE TABLE group_admins(chat_id INTEGER,user_id INTEGER,role TEXT);
  CREATE TABLE group_players(chat_id INTEGER,user_id INTEGER);
  CREATE TABLE group_missions(chat_id INTEGER,mission_id TEXT);
  CREATE TABLE group_raids(raid_id INTEGER PRIMARY KEY,chat_id INTEGER);
  CREATE TABLE group_bans(chat_id INTEGER,user_id INTEGER,actor_id INTEGER);
  CREATE TABLE friend_requests(user_low INTEGER,user_high INTEGER);
  CREATE TABLE party_invites(invite_id INTEGER PRIMARY KEY,inviter_id INTEGER,target_id INTEGER);
  CREATE TABLE parties(party_id INTEGER PRIMARY KEY,leader_id INTEGER);
  CREATE TABLE party_battles(battle_id INTEGER PRIMARY KEY,party_id INTEGER);
  CREATE TABLE party_battle_contributions(battle_id INTEGER,user_id INTEGER);
  CREATE TABLE party_battle_cooldowns(battle_id INTEGER,user_id INTEGER);
  CREATE TABLE party_battle_rewards(battle_id INTEGER,user_id INTEGER);
  CREATE TABLE party_members(user_id INTEGER PRIMARY KEY,party_id INTEGER,joined_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE group_raid_contributions(raid_id INTEGER,user_id INTEGER);
  CREATE TABLE group_raid_cooldowns(raid_id INTEGER,user_id INTEGER,last_attack_at TEXT);
  CREATE TABLE duels(duel_id INTEGER PRIMARY KEY,challenger_id INTEGER,opponent_id INTEGER);
  CREATE TABLE trades(trade_id INTEGER PRIMARY KEY,initiator_id INTEGER,partner_id INTEGER);
  CREATE TABLE battles(user_id INTEGER PRIMARY KEY);
  CREATE TABLE daily_claims(user_id INTEGER PRIMARY KEY);
  CREATE TABLE boss_defeats(user_id INTEGER,monster_level INTEGER);
  CREATE TABLE monster_discoveries(user_id INTEGER,monster_level INTEGER);
  CREATE TABLE quest_progress(user_id INTEGER,quest_id TEXT);
  CREATE TABLE achievement_progress(user_id INTEGER,achievement_id TEXT);
  CREATE TABLE character_appearance(user_id INTEGER PRIMARY KEY);
  CREATE TABLE dungeon_runs(user_id INTEGER PRIMARY KEY,dungeon_id INTEGER);
  CREATE TABLE dungeon_rewards(user_id INTEGER,dungeon_id INTEGER);
  CREATE TABLE player_materials(user_id INTEGER,material_id TEXT,quantity INTEGER);
  CREATE TABLE crafted_items(user_id INTEGER,recipe_id TEXT);
  CREATE TABLE player_worlds(user_id INTEGER,current_world INTEGER);
  CREATE TABLE player_presence(user_id INTEGER PRIMARY KEY,last_seen TEXT);
  CREATE TABLE world_discoveries(user_id INTEGER,world_id INTEGER);
  CREATE TABLE player_story(user_id INTEGER,chapter_id INTEGER,choice_id TEXT);
  CREATE TABLE story_flags(user_id INTEGER,flag TEXT,value TEXT);
  CREATE TABLE story_reward_claims(user_id INTEGER,chapter_id INTEGER);
  INSERT INTO players VALUES(1,'leader',10,0),(2,'member',20,0);
  INSERT INTO guilds VALUES(5,1);
  INSERT INTO guild_members VALUES(1,5,'leader',CURRENT_TIMESTAMP),(2,5,'member',CURRENT_TIMESTAMP);
  INSERT INTO friend_requests VALUES(1,2);
  INSERT INTO duels VALUES(1,1,2);
  INSERT INTO trades VALUES(1,1,2);
  """)
  await init_account_tables(self.db)
 async def asyncTearDown(self): await self.db.close()
 async def test_default_settings(self):
  self.assertEqual(await get_settings(self.db,1),{"notifications_enabled":1,"profile_visibility":"public","sound_enabled":1})
 async def test_update_settings(self):
  self.assertEqual(await update_settings(self.db,1,False,"friends"),{"notifications_enabled":0,"profile_visibility":"friends","sound_enabled":1})
 async def test_existing_settings_table_gets_sound_migration(self):
  legacy=await aiosqlite.connect(":memory:")
  legacy.row_factory=aiosqlite.Row
  await legacy.execute("""CREATE TABLE player_settings(
   user_id INTEGER PRIMARY KEY,notifications_enabled INTEGER NOT NULL DEFAULT 1,
   profile_visibility TEXT NOT NULL DEFAULT 'public',updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )""")
  await init_account_tables(legacy)
  cur=await legacy.execute("PRAGMA table_info(player_settings)")
  self.assertIn("sound_enabled",{row["name"] for row in await cur.fetchall()})
  await legacy.close()
 async def test_sound_preference_is_persisted(self):
  self.assertEqual(await update_settings(self.db,1,sound_enabled=False),{"notifications_enabled":1,"profile_visibility":"public","sound_enabled":0})
  self.assertEqual((await get_settings(self.db,1))["sound_enabled"],0)
 async def test_invalid_sound_setting_rejected(self):
  with self.assertRaises(AccountError): await update_settings(self.db,1,sound_enabled="muted")
 async def test_invalid_settings_rejected(self):
  with self.assertRaises(AccountError): await update_settings(self.db,1,"off",None)
  with self.assertRaises(AccountError): await update_settings(self.db,1,None,"private")
 async def test_invalid_account_rejected(self):
  with self.assertRaises(AccountError): await get_settings(self.db,True)

 async def test_account_deletion_respects_outer_transaction(self):
  await self.db.execute("INSERT INTO security_events VALUES(2,1,'invalid_battle_action',1,'pending event',CURRENT_TIMESTAMP)")
  self.assertTrue(self.db.in_transaction)
  await delete_player_account(self.db,1)
  self.assertTrue(self.db.in_transaction)
  cur=await self.db.execute("SELECT 1 FROM players WHERE user_id=1")
  self.assertIsNone(await cur.fetchone())
  await self.db.rollback()
  cur=await self.db.execute("SELECT 1 FROM players WHERE user_id=1")
  self.assertIsNotNone(await cur.fetchone())
  cur=await self.db.execute("SELECT 1 FROM security_events WHERE event_id=2")
  self.assertIsNone(await cur.fetchone())

 async def test_delete_account_removes_security_events(self):
  await self.db.execute("INSERT INTO security_events VALUES(1,1,'invalid_battle_action',2,'bad action',CURRENT_TIMESTAMP)")
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT COUNT(*) n FROM security_events WHERE user_id=1")
  self.assertEqual((await cur.fetchone())["n"],0)
 async def test_account_deletion_rolls_back_partial_changes(self):
  await self.db.execute("""CREATE TRIGGER block_player_delete BEFORE DELETE ON players
   WHEN OLD.user_id=1 BEGIN SELECT RAISE(ABORT,'blocked'); END""")
  with self.assertRaises(Exception):
   await self.db.commit()  # Commit fixture writes before the deletion transaction.
   await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT leader_id FROM guilds WHERE guild_id=5")
  self.assertEqual((await cur.fetchone())["leader_id"],1)
  cur=await self.db.execute("SELECT role FROM guild_members WHERE user_id=1")
  self.assertEqual((await cur.fetchone())["role"],"leader")
  cur=await self.db.execute("SELECT 1 FROM players WHERE user_id=1")
  self.assertIsNotNone(await cur.fetchone())
 async def test_delete_account_transfers_guild_leadership(self):
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT leader_id FROM guilds WHERE guild_id=5")
  self.assertEqual((await cur.fetchone())["leader_id"],2)
  cur=await self.db.execute("SELECT role FROM guild_members WHERE user_id=2")
  self.assertEqual((await cur.fetchone())["role"],"leader")
 async def test_delete_account_removes_social_and_economy_data(self):
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT COUNT(*) n FROM players")
  self.assertEqual((await cur.fetchone())["n"],1)
  cur=await self.db.execute("SELECT user_id FROM players")
  self.assertEqual((await cur.fetchone())["user_id"],2)
  for table in ("friend_requests","duels","trades"):
   cur=await self.db.execute(f"SELECT COUNT(*) n FROM {table}")
   self.assertEqual((await cur.fetchone())["n"],0)
 async def test_delete_party_leader_transfers_leadership(self):
  await self.db.execute("INSERT INTO parties VALUES(7,1)")
  await self.db.execute("INSERT INTO party_members VALUES(1,7,CURRENT_TIMESTAMP),(2,7,CURRENT_TIMESTAMP)")
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT leader_id FROM parties WHERE party_id=7")
  self.assertEqual((await cur.fetchone())["leader_id"],2)
 async def test_delete_missing_account_rejected(self):
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  with self.assertRaises(AccountError): await delete_player_account(self.db,999)
 async def test_delete_account_transfers_group_owner(self):
  await self.db.execute("INSERT INTO group_profiles VALUES(-100,1)")
  await self.db.execute("INSERT INTO group_admins VALUES(-100,1,'owner'),(-100,2,'admin')")
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT owner_id FROM group_profiles WHERE chat_id=-100")
  self.assertEqual((await cur.fetchone())["owner_id"],2)
 async def test_delete_account_removes_orphaned_group(self):
  await self.db.execute("INSERT INTO group_profiles VALUES(-101,1)")
  await self.db.execute("INSERT INTO group_admins VALUES(-101,1,'owner')")
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT 1 FROM group_profiles WHERE chat_id=-101")
  self.assertIsNone(await cur.fetchone())

 async def test_delete_seller_refunds_active_bidder(self):
  await self.db.execute("ALTER TABLE players ADD COLUMN coins INTEGER NOT NULL DEFAULT 0")
  await self.db.execute("CREATE TABLE auction_listings(listing_id INTEGER PRIMARY KEY,seller_id INTEGER,current_bid INTEGER,highest_bidder INTEGER,status TEXT)")
  await self.db.execute("CREATE TABLE auction_stash(stash_id INTEGER PRIMARY KEY,user_id INTEGER)")
  await self.db.execute("UPDATE players SET coins=100 WHERE user_id=2")
  await self.db.execute("INSERT INTO auction_listings VALUES(1,1,75,2,'active')")
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=2")
  self.assertEqual((await cur.fetchone())["coins"],175)
  cur=await self.db.execute("SELECT status FROM auction_listings WHERE listing_id=1")
  self.assertEqual((await cur.fetchone())["status"],"cancelled")
 async def test_delete_highest_bidder_reopens_auction(self):
  await self.db.execute("ALTER TABLE players ADD COLUMN coins INTEGER NOT NULL DEFAULT 0")
  await self.db.execute("CREATE TABLE auction_listings(listing_id INTEGER PRIMARY KEY,seller_id INTEGER,current_bid INTEGER,highest_bidder INTEGER,status TEXT)")
  await self.db.execute("CREATE TABLE auction_stash(stash_id INTEGER PRIMARY KEY,user_id INTEGER)")
  await self.db.execute("INSERT INTO auction_listings VALUES(1,2,75,1,'active')")
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT current_bid,highest_bidder,status FROM auction_listings WHERE listing_id=1")
  row=await cur.fetchone()
  self.assertEqual((row["current_bid"],row["highest_bidder"],row["status"]),(0,None,"active"))


 async def test_delete_account_removes_optional_gameplay_progress(self):
  await self.db.execute("CREATE TABLE player_daily_missions(user_id INTEGER,mission_id TEXT)")
  await self.db.execute("CREATE TABLE player_monster_mastery(user_id INTEGER,monster_level INTEGER)")
  await self.db.execute("CREATE TABLE roaming_event_participants(event_id INTEGER,user_id INTEGER)")
  await self.db.execute("INSERT INTO player_daily_missions VALUES(1,'daily_hunter')")
  await self.db.execute("INSERT INTO player_monster_mastery VALUES(1,5)")
  await self.db.execute("INSERT INTO roaming_event_participants VALUES(10,1)")
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  await delete_player_account(self.db,1)
  for table in ("player_daily_missions","player_monster_mastery","roaming_event_participants"):
   cur=await self.db.execute(f"SELECT COUNT(*) n FROM {table}")
   self.assertEqual((await cur.fetchone())["n"],0)
 async def test_delete_account_removes_guild_chat_history(self):
  await self.db.execute("CREATE TABLE guild_chat_messages(message_id INTEGER PRIMARY KEY,guild_id INTEGER,user_id INTEGER,message TEXT)")
  await self.db.execute("INSERT INTO guild_chat_messages VALUES(1,5,1,'private guild text')")
  await self.db.commit()  # Commit fixture writes before the deletion transaction.
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT COUNT(*) n FROM guild_chat_messages WHERE user_id=1")
  self.assertEqual((await cur.fetchone())["n"],0)

if __name__=="__main__": unittest.main()