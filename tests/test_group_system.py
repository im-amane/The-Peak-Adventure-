import unittest
import aiosqlite
from group_system import *

class GroupTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:"); self.db.row_factory=aiosqlite.Row
  await self.db.execute("CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER NOT NULL DEFAULT 0)")
  await self.db.executemany("INSERT INTO players(user_id,coins) VALUES(?,0)",[(101,),(202,)])
  await self.db.commit()
  await init_group_tables(self.db); await register_group(self.db,-1001,"Peak Raiders",101)
  await set_group_admin(self.db,-1001,202,"admin")
  await record_group_player(self.db,-1001,101,"Ash",10)
  await record_group_player(self.db,-1001,202,"Mira",20)
 async def asyncTearDown(self): await self.db.close()
 async def test_group_actions_reject_malformed_types_with_domain_errors(self):
  with self.assertRaisesRegex(GroupError,"title must be text"):
   await register_group(self.db,-1003,["Peak"],101)
  with self.assertRaises(GroupError):
   await set_group_admin(self.db,-1001,202,[])
  with self.assertRaises(GroupError):
   await record_group_activity(self.db,-1001,[])
  with self.assertRaises(GroupError):
   await claim_group_mission(self.db,-1001,202,[])
  with self.assertRaises(GroupError):
   await claim_group_mission(self.db,-1001,[], "battles")

 async def test_group_registration_admin_and_roster_require_existing_players(self):
  with self.assertRaisesRegex(GroupError,"owner account not found"):
   await register_group(self.db,-1003,"Ghost Group",999)
  with self.assertRaisesRegex(GroupError,"administrator account not found"):
   await set_group_admin(self.db,-1001,999,"admin")
  with self.assertRaisesRegex(GroupError,"player account not found"):
   await record_group_player(self.db,-1001,999,"Ghost",10)
  cur=await self.db.execute("SELECT COUNT(*) FROM group_profiles WHERE chat_id=-1003")
  self.assertEqual((await cur.fetchone())[0],0)

 async def test_register_and_verify_admin(self):
  p=await get_group_profile(self.db,-1001); self.assertEqual(p["admin_count"],2); self.assertTrue(await is_group_admin(self.db,-1001,202))
 async def test_private_chat_rejected(self):
  with self.assertRaises(GroupError): await register_group(self.db,123,"private",101)
 async def test_roster_upsert(self):
  await record_group_player(self.db,-1001,202,"Mira",21); self.assertEqual((await list_group_players(self.db,-1001))[0]["player_level"],21)
 async def test_group_xp_levels(self):
  self.assertEqual(await award_group_xp(self.db,-1001,500),(2,0))
 async def test_invalid_xp(self):
  with self.assertRaises(GroupError): await award_group_xp(self.db,-1001,0)
 async def test_daily_mission_progress(self):
  rows=await record_group_activity(self.db,-1001,"battle",10); self.assertTrue(next(x for x in rows if x["id"]=="battles")["completed"])
 async def test_claim_once_and_admin_only(self):
  await record_group_activity(self.db,-1001,"battle",5)
  with self.assertRaises(GroupError): await claim_group_mission(self.db,-1001,303,"battles")
  self.assertEqual(await claim_group_mission(self.db,-1001,202,"battles"),(120,40))
  with self.assertRaises(GroupError): await claim_group_mission(self.db,-1001,202,"battles")
 async def test_raid_start_attack(self):
  await start_group_raid(self.db,-1001,202,10,"Root Warden",1000)
  result=await attack_group_raid(self.db,-1001,101,1000); self.assertEqual(result["status"],"won")
 async def test_raid_attack_cooldown(self):
  await start_group_raid(self.db,-1001,202,10,"Root Warden",1000)
  await attack_group_raid(self.db,-1001,101,10)
  with self.assertRaisesRegex(GroupError,"cooldown"):
   await attack_group_raid(self.db,-1001,101,10)
 async def test_unrostered_cannot_attack(self):
  await start_group_raid(self.db,-1001,202,10,"Root Warden",1000)
  with self.assertRaises(GroupError): await attack_group_raid(self.db,-1001,303,10)
 async def test_active_raid_is_unique(self):
  await start_group_raid(self.db,-1001,202,10,"Root Warden",1000)
  with self.assertRaises(GroupError): await start_group_raid(self.db,-1001,202,10,"Root Warden",1000)
 async def test_group_ban_requires_admin_and_unban(self):
  with self.assertRaises(GroupError): await set_group_ban(self.db,-1001,303,404,True)
  await set_group_ban(self.db,-1001,202,404,True,"spam"); self.assertTrue(await is_group_banned(self.db,-1001,404))
  await set_group_ban(self.db,-1001,202,404,False); self.assertFalse(await is_group_banned(self.db,-1001,404))
 async def test_owner_cannot_be_banned(self):
  with self.assertRaises(GroupError): await set_group_ban(self.db,-1001,202,101,True)
 async def test_group_campaign_progress_is_sequential_and_persistent(self):
  rows=await get_group_campaign(self.db,-1001)
  self.assertTrue(rows[0]["unlocked"])
  self.assertFalse(rows[1]["unlocked"])
  await record_group_activity(self.db,-1001,"battle",10)
  rows=await get_group_campaign(self.db,-1001)
  self.assertTrue(rows[0]["completed"])
  self.assertFalse(rows[1]["unlocked"])
  await claim_group_campaign_reward(self.db,-1001,202,1)
  rows=await get_group_campaign(self.db,-1001)
  self.assertTrue(rows[1]["unlocked"])
  self.assertEqual(rows[0]["progress"],10)

 async def test_group_campaign_requires_matching_activity(self):
  await record_group_activity(self.db,-1001,"trade",4)
  rows=await get_group_campaign(self.db,-1001)
  self.assertEqual(rows[0]["progress"],0)
  self.assertEqual(rows[2]["progress"],0)

 async def test_group_campaign_claim_requires_completion_and_admin(self):
  with self.assertRaisesRegex(GroupError,"Complete"):
   await claim_group_campaign_reward(self.db,-1001,202,1)
  await record_group_activity(self.db,-1001,"battle",10)
  with self.assertRaisesRegex(GroupError,"verified group admins"):
   await claim_group_campaign_reward(self.db,-1001,303,1)
  self.assertEqual(await claim_group_campaign_reward(self.db,-1001,202,1),(100,50))
  with self.assertRaisesRegex(GroupError,"already claimed"):
   await claim_group_campaign_reward(self.db,-1001,202,1)

 async def test_group_campaign_reward_rolls_back_claim_and_xp_if_coin_credit_fails(self):
  await record_group_activity(self.db,-1001,"battle",10)
  await self.db.execute("CREATE TRIGGER reject_campaign_coins BEFORE UPDATE OF coins ON players WHEN OLD.user_id=202 BEGIN SELECT RAISE(ABORT,'coin credit unavailable'); END")
  await self.db.commit()
  with self.assertRaises(Exception):
   await claim_group_campaign_reward(self.db,-1001,202,1)
  rows=await get_group_campaign(self.db,-1001)
  self.assertFalse(rows[0]["claimed"])
  cur=await self.db.execute("SELECT group_xp FROM group_profiles WHERE chat_id=-1001")
  self.assertEqual((await cur.fetchone())[0],0)

 async def test_group_campaign_preserves_outer_transaction(self):
  await self.db.execute("BEGIN")
  await record_group_activity(self.db,-1001,"battle",3)
  self.assertTrue(self.db.in_transaction)
  await self.db.rollback()
  rows=await get_group_campaign(self.db,-1001)
  self.assertEqual(rows[0]["progress"],0)

 async def test_group_ranking(self):
  await self.db.execute("INSERT INTO players(user_id,coins) VALUES(303,0)")
  await self.db.commit()
  await register_group(self.db,-1002,"Summit",303); await award_group_xp(self.db,-1002,500)
  self.assertEqual((await top_groups(self.db))[0]["chat_id"],-1002)

 async def test_group_table_initialization_preserves_outer_transaction(self):
  db=await aiosqlite.connect(":memory:")
  try:
   await db.execute("CREATE TABLE transaction_marker(value INTEGER)")
   await db.execute("BEGIN")
   await db.execute("INSERT INTO transaction_marker VALUES(1)")
   await init_group_tables(db)
   self.assertTrue(db.in_transaction)
   await db.rollback()
   cur=await db.execute("SELECT COUNT(*) FROM transaction_marker")
   self.assertEqual((await cur.fetchone())[0],0)
   cur=await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='group_profiles'")
   self.assertIsNone(await cur.fetchone())
  finally:
   await db.close()

 async def test_group_activity_preserves_outer_transaction(self):
  await self.db.execute("BEGIN")
  await record_group_activity(self.db,-1001,"battle",2)
  self.assertTrue(self.db.in_transaction)
  await self.db.rollback()
  cur=await self.db.execute("SELECT COUNT(*) FROM group_missions WHERE chat_id=-1001")
  self.assertEqual((await cur.fetchone())[0],0)

 async def test_claim_mission_preserves_outer_transaction(self):
  await record_group_activity(self.db,-1001,"battle",5)
  await self.db.execute("BEGIN")
  await claim_group_mission(self.db,-1001,202,"battles")
  self.assertTrue(self.db.in_transaction)
  await self.db.rollback()
  cur=await self.db.execute("SELECT claimed FROM group_missions WHERE chat_id=-1001 AND mission_date=? AND mission_id='battles'",(today(),))
  self.assertEqual((await cur.fetchone())["claimed"],0)
  cur=await self.db.execute("SELECT group_xp FROM group_profiles WHERE chat_id=-1001")
  self.assertEqual((await cur.fetchone())["group_xp"],0)

 async def test_mission_claim_rolls_back_when_group_xp_update_fails(self):
  await record_group_activity(self.db,-1001,"battle",5)
  await self.db.execute("CREATE TRIGGER reject_group_xp BEFORE UPDATE OF group_xp ON group_profiles BEGIN SELECT RAISE(ABORT,'xp unavailable'); END")
  await self.db.commit()
  with self.assertRaises(Exception):
   await claim_group_mission(self.db,-1001,202,"battles")
  cur=await self.db.execute("SELECT claimed FROM group_missions WHERE chat_id=-1001 AND mission_date=? AND mission_id='battles'",(today(),))
  self.assertEqual((await cur.fetchone())["claimed"],0)
  cur=await self.db.execute("SELECT group_xp FROM group_profiles WHERE chat_id=-1001")
  self.assertEqual((await cur.fetchone())["group_xp"],0)

 async def test_raid_attack_rolls_back_when_contribution_fails(self):
  await start_group_raid(self.db,-1001,202,10,"Root Warden",1000)
  await self.db.execute("CREATE TRIGGER reject_group_contribution BEFORE INSERT ON group_raid_contributions BEGIN SELECT RAISE(ABORT,'contribution unavailable'); END")
  await self.db.commit()
  with self.assertRaises(Exception):
   await attack_group_raid(self.db,-1001,101,100)
  cur=await self.db.execute("SELECT hp,status FROM group_raids WHERE chat_id=-1001")
  raid=await cur.fetchone()
  self.assertEqual((raid["hp"],raid["status"]),(1000,"active"))
  cur=await self.db.execute("SELECT COUNT(*) FROM group_raid_cooldowns")
  self.assertEqual((await cur.fetchone())[0],0)

 async def test_raid_damage_mission_and_xp_roll_back_together(self):
  await start_group_raid(self.db,-1001,202,10,"Root Warden",1000)
  await self.db.execute("CREATE TRIGGER reject_group_reward_xp BEFORE UPDATE OF group_xp ON group_profiles BEGIN SELECT RAISE(ABORT,'xp unavailable'); END")
  await self.db.commit()
  with self.assertRaises(Exception):
   await attack_group_raid_and_reward(self.db,-1001,101,100)
  cur=await self.db.execute("SELECT hp,status FROM group_raids WHERE chat_id=-1001")
  raid=await cur.fetchone()
  self.assertEqual((raid["hp"],raid["status"]),(1000,"active"))
  cur=await self.db.execute("SELECT COUNT(*) FROM group_raid_cooldowns")
  self.assertEqual((await cur.fetchone())[0],0)
  cur=await self.db.execute("SELECT COUNT(*) FROM group_raid_contributions")
  self.assertEqual((await cur.fetchone())[0],0)
  cur=await self.db.execute("SELECT COUNT(*) FROM group_missions WHERE chat_id=-1001 AND progress>0")
  self.assertEqual((await cur.fetchone())[0],0)
  await self.db.execute("DROP TRIGGER reject_group_reward_xp")
  result=await attack_group_raid_and_reward(self.db,-1001,101,100)
  self.assertEqual((result["hp"],result["status"]),(900,"active"))
  cur=await self.db.execute("SELECT group_xp FROM group_profiles WHERE chat_id=-1001")
  self.assertEqual((await cur.fetchone())[0],10)
  cur=await self.db.execute("SELECT progress FROM group_missions WHERE chat_id=-1001 AND mission_id='battles'")
  self.assertEqual((await cur.fetchone())[0],1)
 async def test_group_activity_progress_rolls_back_if_xp_award_fails(self):
  await self.db.execute("CREATE TRIGGER reject_group_activity_xp BEFORE UPDATE OF group_xp ON group_profiles BEGIN SELECT RAISE(ABORT,'xp unavailable'); END")
  await self.db.commit()
  with self.assertRaises(Exception):
   await record_group_activity_reward(self.db,-1001,"battle",20)
  cur=await self.db.execute("SELECT progress FROM group_missions WHERE chat_id=-1001 AND mission_date=? AND mission_id='battles'",(today(),))
  self.assertIsNone(await cur.fetchone())
  cur=await self.db.execute("SELECT group_xp FROM group_profiles WHERE chat_id=-1001")
  self.assertEqual((await cur.fetchone())[0],0)
  await self.db.execute("DROP TRIGGER reject_group_activity_xp")
  await record_group_activity_reward(self.db,-1001,"battle",20)
  cur=await self.db.execute("SELECT progress FROM group_missions WHERE chat_id=-1001 AND mission_date=? AND mission_id='battles'",(today(),))
  self.assertEqual((await cur.fetchone())[0],1)
  cur=await self.db.execute("SELECT group_xp FROM group_profiles WHERE chat_id=-1001")
  self.assertEqual((await cur.fetchone())[0],20)
 async def test_group_mission_coin_reward_rolls_back_claim_and_xp_if_credit_fails(self):
  await record_group_activity(self.db,-1001,"battle",5)
  await self.db.execute("CREATE TRIGGER reject_group_mission_coins BEFORE UPDATE OF coins ON players WHEN OLD.user_id=202 BEGIN SELECT RAISE(ABORT,'coin credit unavailable'); END")
  await self.db.commit()
  with self.assertRaises(Exception):
   await claim_group_mission_reward(self.db,-1001,202,"battles")
  cur=await self.db.execute("SELECT claimed FROM group_missions WHERE chat_id=-1001 AND mission_date=? AND mission_id='battles'",(today(),))
  self.assertEqual((await cur.fetchone())[0],0)
  cur=await self.db.execute("SELECT group_xp FROM group_profiles WHERE chat_id=-1001")
  self.assertEqual((await cur.fetchone())[0],0)
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=202")
  self.assertEqual((await cur.fetchone())[0],0)
  await self.db.execute("DROP TRIGGER reject_group_mission_coins")
  self.assertEqual(await claim_group_mission_reward(self.db,-1001,202,"battles"),(120,40))
  cur=await self.db.execute("SELECT claimed FROM group_missions WHERE chat_id=-1001 AND mission_date=? AND mission_id='battles'",(today(),))
  self.assertEqual((await cur.fetchone())[0],1)
  cur=await self.db.execute("SELECT group_xp FROM group_profiles WHERE chat_id=-1001")
  self.assertEqual((await cur.fetchone())[0],40)
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=202")
  self.assertEqual((await cur.fetchone())[0],120)
 async def test_group_xp_award_preserves_outer_transaction(self):
  await self.db.execute("BEGIN")
  await award_group_xp(self.db,-1001,500)
  self.assertTrue(self.db.in_transaction)
  await self.db.rollback()
  cur=await self.db.execute("SELECT group_level,group_xp FROM group_profiles WHERE chat_id=-1001")
  row=await cur.fetchone()
  self.assertEqual((row["group_level"],row["group_xp"]),(1,0))

 async def test_group_xp_award_rolls_back_failed_update(self):
  await self.db.execute("CREATE TRIGGER reject_group_xp BEFORE UPDATE OF group_xp ON group_profiles BEGIN SELECT RAISE(ABORT,'xp unavailable'); END")
  await self.db.commit()
  with self.assertRaises(Exception):
   await award_group_xp(self.db,-1001,500)
  self.assertFalse(self.db.in_transaction)
  cur=await self.db.execute("SELECT group_level,group_xp FROM group_profiles WHERE chat_id=-1001")
  row=await cur.fetchone()
  self.assertEqual((row["group_level"],row["group_xp"]),(1,0))
if __name__=="__main__": unittest.main()
