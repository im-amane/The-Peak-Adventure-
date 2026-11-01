import unittest
import aiosqlite
from story_system import *

class StoryTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:");self.db.row_factory=aiosqlite.Row
  await self.db.executescript("""
  CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER DEFAULT 0);
  CREATE TABLE party_members(user_id INTEGER,party_id INTEGER);
  CREATE TABLE story_reward_claims(user_id INTEGER,chapter_id INTEGER,PRIMARY KEY(user_id,chapter_id));
  INSERT INTO players VALUES(1,0);
  """)
  await init_story_tables(self.db)
 async def asyncTearDown(self):await self.db.close()
 async def test_first_chapter_unlocked(self):
  rows=await get_story_chapters(self.db,1,1)
  self.assertTrue(rows[0]["unlocked"]);self.assertFalse(rows[1]["unlocked"])
 async def test_level_gate_blocks_chapter(self):
  with self.assertRaises(StoryError):await choose_story_path(self.db,1,4,2,"trust_mira")
 async def test_previous_chapter_required(self):
  with self.assertRaises(StoryError):await choose_story_path(self.db,1,11,3,"speak_truth")
 async def test_branch_choice_sets_flag(self):
  await choose_story_path(self.db,1,5,1,"follow_mira")
  await choose_story_path(self.db,1,5,2,"trust_mira")
  self.assertEqual((await get_story_flags(self.db,1))["trust_path"],"mira")
 async def test_invalid_choice_rejected(self):
  with self.assertRaises(StoryError):await choose_story_path(self.db,1,1,1,"wrong")
 async def test_party_chapter_requires_party(self):
  for cid in range(1,8):
   chapter=CHAPTERS[cid-1]
   await choose_story_path(self.db,1,100,cid,next(iter(chapter["choices"])))
  with self.assertRaises(StoryError):await choose_story_path(self.db,1,100,8,"light_together")
 async def test_party_chapter_unlocks_for_party_member(self):
  for cid in range(1,8):
   await choose_story_path(self.db,1,100,cid,next(iter(CHAPTERS[cid-1]["choices"])))
  await self.db.execute("INSERT INTO party_members VALUES(1,10)")
  result=await choose_story_path(self.db,1,100,8,"light_together")
  self.assertEqual(result["chapter"]["title"],"The Last Lantern")
 async def test_reward_can_be_claimed_once(self):
  await choose_story_path(self.db,1,1,1,"follow_mira")
  self.assertEqual(await claim_story_reward(self.db,1,1),80)
  with self.assertRaises(StoryError):await claim_story_reward(self.db,1,1)
if __name__=="__main__":unittest.main()
