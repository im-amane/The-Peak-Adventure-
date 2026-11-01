import unittest
import aiosqlite
from group_system import *

class GroupTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:"); self.db.row_factory=aiosqlite.Row
  await init_group_tables(self.db); await register_group(self.db,-1001,"Peak Raiders",101)
  await set_group_admin(self.db,-1001,202,"admin")
  await record_group_player(self.db,-1001,101,"Ash",10)
  await record_group_player(self.db,-1001,202,"Mira",20)
 async def asyncTearDown(self): await self.db.close()
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
 async def test_group_ranking(self):
  await register_group(self.db,-1002,"Summit",303); await award_group_xp(self.db,-1002,500)
  self.assertEqual((await top_groups(self.db))[0]["chat_id"],-1002)

if __name__=="__main__": unittest.main()
