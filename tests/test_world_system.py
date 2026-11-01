import unittest
import aiosqlite
from world_system import *

class WorldSystemTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:"); self.db.row_factory=aiosqlite.Row
  await init_world_tables(self.db)
 async def asyncTearDown(self): await self.db.close()
 async def test_new_player_starts_in_first_world(self):
  self.assertEqual(await get_current_world(self.db,101,1),1)
 async def test_level_unlocks_next_world_every_ten_levels(self):
  self.assertEqual(unlocked_world_count(10),1)
  self.assertEqual(unlocked_world_count(11),2)
  self.assertEqual(unlocked_world_count(100),10)
 async def test_cannot_travel_to_locked_world(self):
  with self.assertRaises(WorldError): await travel_to_world(self.db,101,10,2)
 async def test_can_travel_to_unlocked_world(self):
  result=await travel_to_world(self.db,101,21,3)
  self.assertEqual(result["name"],"Stormglass Highlands")
  self.assertEqual(await get_current_world(self.db,101,21),3)
 async def test_world_choice_marks_current_and_locked(self):
  await travel_to_world(self.db,101,30,2)
  rows=await get_world_choices(self.db,101,30)
  self.assertTrue(rows[1]["current"]); self.assertFalse(rows[3]["unlocked"])
 async def test_level_downgrade_clamps_current_world(self):
  await travel_to_world(self.db,101,51,5)
  self.assertEqual(await get_current_world(self.db,101,21),3)
 async def test_invalid_world_rejected(self):
  with self.assertRaises(WorldError): await travel_to_world(self.db,101,10,0)
 async def test_encounters_stay_inside_selected_world(self):
  for world in range(1,11):
   levels=world_encounter_levels(100,world,False)
   self.assertTrue(all((world-1)*10<level<=world*10 for level in levels))
 async def test_unbeaten_boss_is_mandatory_at_world_cap(self):
  self.assertEqual(world_encounter_levels(100,10,False),(100,))
 async def test_defeated_boss_allows_regular_monsters(self):
  levels=world_encounter_levels(100,10,True)
  self.assertTrue(levels); self.assertNotIn(100,levels)
if __name__=="__main__": unittest.main()
