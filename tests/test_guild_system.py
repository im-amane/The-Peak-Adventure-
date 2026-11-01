import unittest
import aiosqlite
from guild_system import *

class GuildFeatureTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:"); self.db.row_factory=aiosqlite.Row
  await self.db.executescript("""
  CREATE TABLE players(user_id INTEGER PRIMARY KEY,username TEXT,level INTEGER,xp INTEGER);
  CREATE TABLE guilds(guild_id INTEGER PRIMARY KEY,name TEXT,leader_id INTEGER,guild_level INTEGER DEFAULT 1,guild_xp INTEGER DEFAULT 0);
  CREATE TABLE guild_members(user_id INTEGER PRIMARY KEY,guild_id INTEGER,role TEXT,joined_at TEXT DEFAULT CURRENT_TIMESTAMP);
  INSERT INTO players VALUES(1,'leader',10,0),(2,'member',5,0),(3,'guest',2,0);
  INSERT INTO guilds VALUES(10,'Peak',1,1,0);
  INSERT INTO guild_members VALUES(1,10,'leader',CURRENT_TIMESTAMP),(2,10,'member',CURRENT_TIMESTAMP);
  """)
  await self.db.execute("INSERT INTO players VALUES(?,?,?,?)",(4,"other",4,0))
  await self.db.execute("INSERT INTO guilds VALUES(?,?,?,?,?)",(20,"Other",4,1,0))
  await self.db.execute("INSERT INTO guild_members VALUES(?,?,?,CURRENT_TIMESTAMP)",(4,20,"leader"))
  await init_guild_features(self.db)
 async def asyncTearDown(self): await self.db.close()
 async def test_leader_can_invite_and_target_accepts(self):
  invite=await create_guild_invite(self.db,10,1,3)
  self.assertEqual(await respond_guild_invite(self.db,invite,3,True),10)
  self.assertEqual(await guild_role(self.db,10,3),"member")
 async def test_non_officer_cannot_invite(self):
  with self.assertRaises(GuildFeatureError): await create_guild_invite(self.db,10,2,3)
 async def test_invite_target_only_can_respond(self):
  invite=await create_guild_invite(self.db,10,1,3)
  with self.assertRaises(GuildFeatureError): await respond_guild_invite(self.db,invite,2,True)
 async def test_duplicate_pending_invite_blocked(self):
  await create_guild_invite(self.db,10,1,3)
  with self.assertRaises(GuildFeatureError): await create_guild_invite(self.db,10,1,3)
 async def test_only_leader_can_change_roles(self):
  with self.assertRaises(GuildFeatureError): await set_guild_role(self.db,10,2,3,"officer")
  await set_guild_role(self.db,10,1,2,"officer")
  self.assertEqual(await guild_role(self.db,10,2),"officer")
 async def test_leader_role_cannot_be_changed(self):
  with self.assertRaises(GuildFeatureError): await set_guild_role(self.db,10,1,1,"officer")
 async def test_officer_can_post_announcement(self):
  await set_guild_role(self.db,10,1,2,"officer")
  await set_guild_announcement(self.db,10,2,"  Rally   at dawn  ")
  self.assertEqual((await get_guild_announcement(self.db,10))["message"],"Rally at dawn")
 async def test_member_cannot_post_announcement(self):
  with self.assertRaises(GuildFeatureError): await set_guild_announcement(self.db,10,2,"Hello")
 async def test_guild_mission_progress_and_reward(self):
  await record_guild_activity(self.db,10,2,"battle",5)
  with self.assertRaises(GuildFeatureError): await claim_guild_mission(self.db,10,2,"battles")
  self.assertEqual(await claim_guild_mission(self.db,10,1,"battles"),60)
  with self.assertRaises(GuildFeatureError): await claim_guild_mission(self.db,10,1,"battles")
 async def test_activity_from_nonmember_is_ignored(self):
  self.assertEqual(await record_guild_activity(self.db,10,3,"battle"),[])
 async def test_guild_raid_and_member_attack(self):
  await start_guild_raid(self.db,10,1,10,"Root Warden",100)
  result=await attack_guild_raid(self.db,10,2,100)
  self.assertEqual(result["status"],"won")
 async def test_nonmember_cannot_attack_raid(self):
  await start_guild_raid(self.db,10,1,10,"Root Warden",100)
  with self.assertRaises(GuildFeatureError): await attack_guild_raid(self.db,10,3,10)
 async def test_raid_cooldown(self):
  await start_guild_raid(self.db,10,1,10,"Root Warden",1000)
  await attack_guild_raid(self.db,10,2,10)
  with self.assertRaises(GuildFeatureError): await attack_guild_raid(self.db,10,2,10)

 async def test_leader_can_declare_war_and_target_leader_accepts(self):
  war=await declare_guild_war(self.db,10,1,20)
  self.assertEqual(await respond_guild_war(self.db,war,4,True),"active")
 async def test_non_leader_cannot_declare_war(self):
  with self.assertRaises(GuildFeatureError): await declare_guild_war(self.db,10,2,20)
 async def test_only_target_leader_can_accept_war(self):
  war=await declare_guild_war(self.db,10,1,20)
  with self.assertRaises(GuildFeatureError): await respond_guild_war(self.db,war,2,True)
 async def test_guild_war_completes_after_three_wins(self):
  war=await declare_guild_war(self.db,10,1,20)
  await respond_guild_war(self.db,war,4,True)
  for _ in range(3):
   result=await record_guild_war_duel(self.db,1,4,1)
  self.assertEqual(result["status"],"completed")
  self.assertEqual(result["winner_guild"],10)
 async def test_duplicate_war_is_blocked(self):
  await declare_guild_war(self.db,10,1,20)
  with self.assertRaises(GuildFeatureError): await declare_guild_war(self.db,20,4,10)


 async def test_guild_members_can_chat_and_read_history(self):
  message_id=await send_guild_message(self.db,10,2,"  Rally   at dawn  ")
  rows=await get_guild_chat(self.db,10,1)
  self.assertEqual(rows[0]["message_id"],message_id)
  self.assertEqual(rows[0]["message"],"Rally at dawn")
  self.assertEqual(rows[0]["username"],"member")
 async def test_nonmember_cannot_read_or_post_guild_chat(self):
  with self.assertRaises(GuildFeatureError): await send_guild_message(self.db,10,3,"Hello")
  with self.assertRaises(GuildFeatureError): await get_guild_chat(self.db,10,3)
 async def test_guild_chat_message_length_is_limited(self):
  with self.assertRaises(GuildFeatureError): await send_guild_message(self.db,10,2," ")
  with self.assertRaises(GuildFeatureError): await send_guild_message(self.db,10,2,"x"*501)

if __name__=="__main__": unittest.main()
