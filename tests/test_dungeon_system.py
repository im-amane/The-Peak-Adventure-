import unittest
import aiosqlite
from dungeon_system import *

class DungeonTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:");self.db.row_factory=aiosqlite.Row
  await self.db.executescript("CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER DEFAULT 0,potions INTEGER DEFAULT 0);INSERT INTO players VALUES(1,0,0);")
  await init_dungeon_tables(self.db)
 async def asyncTearDown(self):await self.db.close()
 async def test_dungeon_unlocks_by_world_level(self):
  self.assertFalse(available_dungeons(10)[1]["unlocked"])
  self.assertTrue(available_dungeons(11)[1]["unlocked"])
 async def test_locked_dungeon_rejected(self):
  with self.assertRaises(DungeonError):await enter_dungeon(self.db,1,10,2)
 async def test_enter_and_progress_rooms(self):
  state=await enter_dungeon(self.db,1,1,1)
  self.assertEqual(state["room"],1)
  state=await advance_dungeon(self.db,1,state["target_level"])
  self.assertEqual(state["room"],2)
  state=await advance_dungeon(self.db,1,state["target_level"])
  self.assertEqual(state["room"],3)
  state=await advance_dungeon(self.db,1,state["target_level"])
  self.assertEqual(state["status"],"completed")
 async def test_cannot_enter_second_active_dungeon(self):
  await enter_dungeon(self.db,1,1,1)
  with self.assertRaises(DungeonError):await enter_dungeon(self.db,1,11,2)
 async def test_completed_run_must_be_claimed_before_reentering(self):
  state=await enter_dungeon(self.db,1,1,1)
  for _ in range(3):
   state=await get_dungeon_state(self.db,1)
   await advance_dungeon(self.db,1,state["target_level"])
  with self.assertRaises(DungeonError): await enter_dungeon(self.db,1,1,1)
 async def test_room_only_advances_at_target_level(self):
  state=await enter_dungeon(self.db,1,1,1)
  self.assertIsNone(await advance_dungeon(self.db,1,state["target_level"]-1))
 async def test_claim_reward_once(self):
  state=await enter_dungeon(self.db,1,1,1)
  for _ in range(3):
   state=await get_dungeon_state(self.db,1)
   await advance_dungeon(self.db,1,state["target_level"])
  self.assertEqual(await claim_dungeon_reward(self.db,1),(150,2))
  with self.assertRaises(DungeonError):await claim_dungeon_reward(self.db,1)
 async def test_enter_rejects_invalid_level_types(self):
  for level in (True,0,101):
   with self.assertRaises(DungeonError):await enter_dungeon(self.db,1,level,1)
 async def test_reward_claim_rolls_back_when_player_is_missing(self):
  state=await enter_dungeon(self.db,1,1,1)
  for _ in range(3):
   state=await get_dungeon_state(self.db,1)
   await advance_dungeon(self.db,1,state["target_level"])
  await self.db.execute("DELETE FROM players WHERE user_id=1");await self.db.commit()
  with self.assertRaisesRegex(DungeonError,"Player account not found"):
   await claim_dungeon_reward(self.db,1)
  cur=await self.db.execute("SELECT 1 FROM dungeon_rewards WHERE user_id=1")
  self.assertIsNone(await cur.fetchone())
 async def test_abandon_active_run(self):
  await enter_dungeon(self.db,1,1,1)
  await abandon_dungeon(self.db,1)
  self.assertEqual((await get_dungeon_state(self.db,1))["status"],"abandoned")
 async def test_abandoned_dungeon_can_be_reentered(self):
  await enter_dungeon(self.db,1,1,1);await abandon_dungeon(self.db,1)
  self.assertEqual((await enter_dungeon(self.db,1,1,1))["status"],"active")
if __name__=="__main__":unittest.main()
