import unittest
import sqlite3
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
 async def test_story_choice_preserves_outer_transaction(self):
  await self.db.execute("BEGIN")
  await choose_story_path(self.db,1,1,1,"follow_mira")
  self.assertTrue(self.db.in_transaction)
  await self.db.rollback()
  cur=await self.db.execute("SELECT 1 FROM player_story WHERE user_id=1 AND chapter_id=1")
  self.assertIsNone(await cur.fetchone())

 async def test_story_reward_preserves_outer_transaction(self):
  await choose_story_path(self.db,1,1,1,"follow_mira")
  await self.db.commit()
  await self.db.execute("BEGIN")
  self.assertEqual(await claim_story_reward(self.db,1,1),80)
  self.assertTrue(self.db.in_transaction)
  await self.db.rollback()
  cur=await self.db.execute("SELECT 1 FROM story_reward_claims WHERE user_id=1 AND chapter_id=1")
  self.assertIsNone(await cur.fetchone())
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=1")
  self.assertEqual((await cur.fetchone())[0],0)

 async def test_failed_story_coin_credit_rolls_back_reward_claim(self):
  await choose_story_path(self.db,1,1,1,"follow_mira")
  await self.db.execute("CREATE TRIGGER reject_story_coins BEFORE UPDATE OF coins ON players BEGIN SELECT RAISE(ABORT,'coin credit unavailable'); END")
  await self.db.commit()
  with self.assertRaisesRegex(sqlite3.IntegrityError,"coin credit unavailable"):
   await claim_story_reward(self.db,1,1)
  self.assertFalse(self.db.in_transaction)
  cur=await self.db.execute("SELECT 1 FROM story_reward_claims WHERE user_id=1 AND chapter_id=1")
  self.assertIsNone(await cur.fetchone())
  cur=await self.db.execute("SELECT coins FROM players WHERE user_id=1")
  self.assertEqual((await cur.fetchone())[0],0)

 async def test_story_table_initialization_preserves_outer_transaction(self):
  db=await aiosqlite.connect(":memory:")
  try:
   await db.execute("CREATE TABLE marker(value INTEGER)")
   await db.execute("BEGIN")
   await db.execute("INSERT INTO marker VALUES(1)")
   await init_story_tables(db)
   self.assertTrue(db.in_transaction)
   await db.rollback()
   cur=await db.execute("SELECT COUNT(*) FROM marker")
   self.assertEqual((await cur.fetchone())[0],0)
   cur=await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='player_story'")
   self.assertIsNone(await cur.fetchone())
  finally:
   await db.close()

 async def test_unhashable_story_choice_returns_story_error(self):
  with self.assertRaises(StoryError):
   await choose_story_path(self.db,1,1,1,[])

 async def test_invalid_story_user_is_rejected(self):
  with self.assertRaises(StoryError):
   await choose_story_path(self.db,0,1,1,"follow_mira")
if __name__=="__main__":unittest.main()
