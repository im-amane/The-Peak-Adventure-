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
 async def test_boolean_and_out_of_range_player_levels_are_rejected(self):
  await self.db.execute("INSERT INTO player_materials VALUES(1,'iron_ore',3),(1,'ember_shard',1)")
  for level in (True,False,0,101,1.5):
   with self.subTest(level=level),self.assertRaises(CraftingError):
    await craft_item(self.db,1,level,"iron_sword")
  self.assertEqual(await get_materials(self.db,1),{"ember_shard":1,"iron_ore":3})

 async def test_missing_player_does_not_consume_materials_or_create_recipe(self):
  await self.db.execute("INSERT INTO player_materials VALUES(999,'iron_ore',3),(999,'ember_shard',1)")
  with self.assertRaises(CraftingError):
   await craft_item(self.db,999,10,"iron_sword")
  self.assertEqual(await get_materials(self.db,999),{"ember_shard":1,"iron_ore":3})
  cur=await self.db.execute("SELECT COUNT(*) AS n FROM crafted_items WHERE user_id=999")
  self.assertEqual((await cur.fetchone())["n"],0)

 async def test_failed_multi_material_craft_rolls_back_partial_debits(self):
  await self.db.execute("INSERT INTO player_materials VALUES(1,'iron_ore',3),(1,'ember_shard',0)")
  with self.assertRaises(CraftingError):
   await craft_item(self.db,1,10,"iron_sword")
  self.assertEqual(await get_materials(self.db,1),{"ember_shard":0,"iron_ore":3})

 async def test_crafting_respects_existing_caller_transaction(self):
  await self.db.execute("INSERT INTO player_materials VALUES(1,'iron_ore',3),(1,'ember_shard',1)")
  await self.db.commit()
  await self.db.execute("BEGIN")
  await self.db.execute("UPDATE players SET weapon='Pending Weapon' WHERE user_id=1")
  await craft_item(self.db,1,10,"iron_sword")
  self.assertTrue(self.db.in_transaction)
  await self.db.rollback()
  cur=await self.db.execute("SELECT weapon FROM players WHERE user_id=1")
  self.assertEqual((await cur.fetchone())["weapon"],"Rusty Sword")
  self.assertEqual(await get_materials(self.db,1),{"ember_shard":1,"iron_ore":3})
  cur=await self.db.execute("SELECT COUNT(*) AS n FROM crafted_items WHERE user_id=1")
  self.assertEqual((await cur.fetchone())["n"],0)

 async def test_invalid_account_and_recipe_types_are_rejected(self):
  for user_id,recipe_id in ((True,"iron_sword"),(0,"iron_sword"),(1,[])):
   with self.subTest(user_id=user_id,recipe_id=recipe_id),self.assertRaises(CraftingError):
    await craft_item(self.db,user_id,10,recipe_id)

 async def test_unknown_recipe_rejected(self):
  with self.assertRaises(CraftingError):await craft_item(self.db,1,1,"nope")
if __name__=="__main__":unittest.main()
