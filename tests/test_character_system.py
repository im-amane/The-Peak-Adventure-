import unittest
import aiosqlite
from character_system import AppearanceError, get_appearance, init_character_tables, save_appearance

class CharacterAppearanceTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:"); self.db.row_factory=aiosqlite.Row
  await init_character_tables(self.db)
 async def asyncTearDown(self): await self.db.close()
 async def test_default_appearance(self):
  self.assertEqual(await get_appearance(self.db,101),{"race":"Human","skin":"warm","hair":"short","outfit":"traveler"})
 async def test_save_and_persist_appearance(self):
  saved=await save_appearance(self.db,101,{"race":"Elf","skin":"deep","hair":"braided","outfit":"ranger"})
  self.assertEqual(saved["race"],"Elf"); self.assertEqual(await get_appearance(self.db,101),saved)
 async def test_partial_update_uses_safe_defaults(self):
  self.assertEqual(await save_appearance(self.db,101,{"race":"Dwarf"}),{"race":"Dwarf","skin":"warm","hair":"short","outfit":"traveler"})
 async def test_invalid_race_rejected(self):
  with self.assertRaises(AppearanceError): await save_appearance(self.db,101,{"race":"Dragon"})
 async def test_invalid_skin_rejected(self):
  with self.assertRaises(AppearanceError): await save_appearance(self.db,101,{"skin":"invisible"})
 async def test_unknown_field_rejected(self):
  with self.assertRaises(AppearanceError): await save_appearance(self.db,101,{"admin":True})
 async def test_non_object_payload_rejected(self):
  with self.assertRaises(AppearanceError): await save_appearance(self.db,101,[])
if __name__=="__main__": unittest.main()
