import unittest
import aiosqlite
from crafting_system import *

class CraftingTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:");self.db.row_factory=aiosqlite.Row
  await self.db.executescript("CREATE TABLE players(user_id INTEGER PRIMARY KEY,weapon TEXT,weapon_attack INTEGER,armor TEXT,armor_defense INTEGER);INSERT INTO players VALUES(1,'Rusty Sword',0,'Cloth',0);")
  await init_crafting_tables(self.db)
 async def asyncTearDown(self):await self.db.close()
 async def test_materials_start_empty(self):
  self.assertEqual(await get_materials(self.db,1),{})
 async def test_material_drop_adds_inventory(self):
  class Fixed:
   def __init__(self):self.values=iter([0.0,0.0])
   def random(self):return next(self.values)
  result=await award_material_drop(self.db,1,{"level":1,"boss":False},Fixed())
  self.assertEqual(result["id"],"iron_ore")
  self.assertEqual((await get_materials(self.db,1))["iron_ore"],1)
 async def test_craft_requires_materials(self):
  with self.assertRaises(CraftingError):await craft_item(self.db,1,10,"iron_sword")
 async def test_craft_requires_level(self):
  await self.db.execute("INSERT INTO player_materials VALUES(1,'iron_ore',3),(1,'ember_shard',1)")
  with self.assertRaises(CraftingError):await craft_item(self.db,1,4,"iron_sword")
 async def test_craft_weapon_consumes_materials_and_equips(self):
  await self.db.execute("INSERT INTO player_materials VALUES(1,'iron_ore',3),(1,'ember_shard',1)")
  result=await craft_item(self.db,1,10,"iron_sword")
  self.assertEqual(result["name"],"Forged Iron Sword")
  cur=await self.db.execute("SELECT weapon,weapon_attack FROM players WHERE user_id=1")
  row=await cur.fetchone();self.assertEqual((row["weapon"],row["weapon_attack"]),("Forged Iron Sword",12))
  self.assertEqual(await get_materials(self.db,1),{"ember_shard":0,"iron_ore":0})
 async def test_unique_recipe_cannot_be_crafted_twice(self):
  await self.db.execute("INSERT INTO player_materials VALUES(1,'iron_ore',6),(1,'ember_shard',2)")
  await craft_item(self.db,1,10,"iron_sword")
  with self.assertRaises(CraftingError):await craft_item(self.db,1,10,"iron_sword")
 async def test_boss_drops_double_materials(self):
  class Fixed:
   def __init__(self):self.values=iter([0.0,0.0])
   def random(self):return next(self.values)
  result=await award_material_drop(self.db,1,{"level":10,"boss":True},Fixed())
  self.assertEqual(result["quantity"],2)
 async def test_unknown_recipe_rejected(self):
  with self.assertRaises(CraftingError):await craft_item(self.db,1,1,"nope")
if __name__=="__main__":unittest.main()
