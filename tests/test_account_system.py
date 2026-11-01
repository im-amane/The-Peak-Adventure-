import unittest
import aiosqlite
from account_system import AccountError, delete_player_account, get_settings, init_account_tables, update_settings

class AccountSystemTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:"); self.db.row_factory=aiosqlite.Row
  await self.db.executescript("""
  CREATE TABLE players(user_id INTEGER PRIMARY KEY,username TEXT,level INTEGER,xp INTEGER);
  CREATE TABLE guilds(guild_id INTEGER PRIMARY KEY,leader_id INTEGER);
  CREATE TABLE guild_members(user_id INTEGER PRIMARY KEY,guild_id INTEGER,role TEXT,joined_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE group_profiles(chat_id INTEGER PRIMARY KEY,owner_id INTEGER);
  CREATE TABLE group_admins(chat_id INTEGER,user_id INTEGER,role TEXT);
  CREATE TABLE group_players(chat_id INTEGER,user_id INTEGER);
  CREATE TABLE group_missions(chat_id INTEGER,mission_id TEXT);
  CREATE TABLE group_raids(raid_id INTEGER PRIMARY KEY,chat_id INTEGER);
  CREATE TABLE group_bans(chat_id INTEGER,user_id INTEGER,actor_id INTEGER);
  CREATE TABLE friend_requests(user_low INTEGER,user_high INTEGER);
  CREATE TABLE party_invites(invite_id INTEGER PRIMARY KEY,inviter_id INTEGER,target_id INTEGER);
  CREATE TABLE parties(party_id INTEGER PRIMARY KEY,leader_id INTEGER);
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
  self.assertEqual(await get_settings(self.db,1),{"notifications_enabled":1,"profile_visibility":"public"})
 async def test_update_settings(self):
  self.assertEqual(await update_settings(self.db,1,False,"friends"),{"notifications_enabled":0,"profile_visibility":"friends"})
 async def test_invalid_settings_rejected(self):
  with self.assertRaises(AccountError): await update_settings(self.db,1,"off",None)
  with self.assertRaises(AccountError): await update_settings(self.db,1,None,"private")
 async def test_invalid_account_rejected(self):
  with self.assertRaises(AccountError): await get_settings(self.db,True)
 async def test_delete_account_transfers_guild_leadership(self):
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT leader_id FROM guilds WHERE guild_id=5")
  self.assertEqual((await cur.fetchone())["leader_id"],2)
  cur=await self.db.execute("SELECT role FROM guild_members WHERE user_id=2")
  self.assertEqual((await cur.fetchone())["role"],"leader")
 async def test_delete_account_removes_social_and_economy_data(self):
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
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT leader_id FROM parties WHERE party_id=7")
  self.assertEqual((await cur.fetchone())["leader_id"],2)
 async def test_delete_missing_account_rejected(self):
  with self.assertRaises(AccountError): await delete_player_account(self.db,999)
 async def test_delete_account_transfers_group_owner(self):
  await self.db.execute("INSERT INTO group_profiles VALUES(-100,1)")
  await self.db.execute("INSERT INTO group_admins VALUES(-100,1,'owner'),(-100,2,'admin')")
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT owner_id FROM group_profiles WHERE chat_id=-100")
  self.assertEqual((await cur.fetchone())["owner_id"],2)
 async def test_delete_account_removes_orphaned_group(self):
  await self.db.execute("INSERT INTO group_profiles VALUES(-101,1)")
  await self.db.execute("INSERT INTO group_admins VALUES(-101,1,'owner')")
  await delete_player_account(self.db,1)
  cur=await self.db.execute("SELECT 1 FROM group_profiles WHERE chat_id=-101")
  self.assertIsNone(await cur.fetchone())
if __name__=="__main__": unittest.main()