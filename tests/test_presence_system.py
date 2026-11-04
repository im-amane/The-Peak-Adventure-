import unittest
import aiosqlite
from presence_system import *

class PresenceTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:");self.db.row_factory=aiosqlite.Row
  await self.db.executescript("""
  CREATE TABLE players(user_id INTEGER PRIMARY KEY,username TEXT,level INTEGER);
  CREATE TABLE friend_requests(user_low INTEGER,user_high INTEGER,status TEXT);
  CREATE TABLE player_settings(user_id INTEGER,profile_visibility TEXT);
  INSERT INTO players VALUES(1,'Ash',5),(2,'Mira',7);
  INSERT INTO friend_requests VALUES(1,2,'accepted');
  """)
  await init_presence_tables(self.db)
 async def asyncTearDown(self):await self.db.close()
 async def test_presence_touch_preserves_outer_transaction(self):
  await self.db.execute("BEGIN")
  await touch_presence(self.db,1)
  self.assertTrue(self.db.in_transaction)
  await self.db.rollback()
  self.assertEqual(await count_online_players(self.db),0)
 async def test_table_initialization_preserves_outer_transaction(self):
  db=await aiosqlite.connect(":memory:");db.row_factory=aiosqlite.Row
  try:
   await db.execute("BEGIN")
   await init_presence_tables(db)
   self.assertTrue(db.in_transaction)
   await db.rollback()
   cur=await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='player_presence'")
   self.assertIsNone(await cur.fetchone())
  finally: await db.close()
 async def test_presence_touch_does_not_create_orphan_for_missing_player(self):
  await touch_presence(self.db,999)
  cur=await self.db.execute("SELECT COUNT(*) AS total FROM player_presence WHERE user_id=999")
  self.assertEqual((await cur.fetchone())["total"],0)

 async def test_presence_touch_creates_online_record(self):
  await touch_presence(self.db,1)
  self.assertEqual(await count_online_players(self.db),1)
 async def test_presence_touch_updates_existing_record(self):
  await touch_presence(self.db,1);await touch_presence(self.db,1)
  self.assertEqual(await count_online_players(self.db),1)
 async def test_online_friends_only_returns_accepted_friends(self):
  await touch_presence(self.db,2)
  rows=await list_online_friends(self.db,1)
  self.assertEqual([row["user_id"] for row in rows],[2])
 async def test_online_friend_query_rejects_invalid_player_ids(self):
  for user_id in (True,False,0,-1,"1",None):
   with self.subTest(user_id=user_id),self.assertRaisesRegex(ValueError,"Invalid player account"):
    await list_online_friends(self.db,user_id)

 async def test_invalid_presence_window_rejected(self):
  with self.assertRaises(ValueError):await count_online_players(self.db,61)
 async def test_invalid_user_does_not_create_presence(self):
  await touch_presence(self.db,True)
  self.assertEqual(await count_online_players(self.db),0)
if __name__=="__main__":unittest.main()
