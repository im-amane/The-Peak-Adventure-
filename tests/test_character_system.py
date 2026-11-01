import unittest
import aiosqlite
from character_system import AppearanceError, get_appearance, init_character_tables, save_appearance

class CharacterAppearanceTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.db=await aiosqlite.connect(":memory:"); self.db.row_factory=aiosqlite.Row
  await init_character_tables(self.db)
 async def asyncTearDown(self): await self.db.close()
 async def test_default_appearance(self):
  self.assertEqual(await get_appearance(self.db,101),{"race":"Human","skin":"warm","hair":"short","outfit":"traveler","face":"soft","body":"balanced"})
 async def test_save_and_persist_appearance(self):
  saved=await save_appearance(self.db,101,{"race":"Elf","skin":"deep","hair":"braided","outfit":"ranger","face":"angular","body":"broad"})
  self.assertEqual(saved["race"],"Elf"); self.assertEqual(await get_appearance(self.db,101),saved)
 async def test_partial_update_uses_safe_defaults(self):
  self.assertEqual(await save_appearance(self.db,101,{"race":"Dwarf"}),{"race":"Dwarf","skin":"warm","hair":"short","outfit":"traveler","face":"soft","body":"balanced"})

 async def test_invalid_face_and_body_rejected(self):
  with self.assertRaises(AppearanceError): await save_appearance(self.db,101,{"face":"mask"})
  with self.assertRaises(AppearanceError): await save_appearance(self.db,101,{"body":"giant"})

 async def test_existing_appearance_table_is_migrated(self):
  legacy=await aiosqlite.connect(":memory:"); legacy.row_factory=aiosqlite.Row
  await legacy.execute("""CREATE TABLE character_appearance(
    user_id INTEGER PRIMARY KEY,race TEXT NOT NULL DEFAULT 'Human',
    skin TEXT NOT NULL DEFAULT 'warm',hair TEXT NOT NULL DEFAULT 'short',
    outfit TEXT NOT NULL DEFAULT 'traveler',updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )""")
  await legacy.execute("INSERT INTO character_appearance(user_id) VALUES(202)")
  await legacy.commit()
  await init_character_tables(legacy)
  appearance=await get_appearance(legacy,202)
  self.assertEqual(appearance["face"],"soft")
  self.assertEqual(appearance["body"],"balanced")
  await legacy.close()

 async def test_invalid_race_rejected(self):
  with self.assertRaises(AppearanceError): await save_appearance(self.db,101,{"race":"Dragon"})
 async def test_invalid_skin_rejected(self):
  with self.assertRaises(AppearanceError): await save_appearance(self.db,101,{"skin":"invisible"})
 async def test_unknown_field_rejected(self):
  with self.assertRaises(AppearanceError): await save_appearance(self.db,101,{"admin":True})
 async def test_non_object_payload_rejected(self):
  with self.assertRaises(AppearanceError): await save_appearance(self.db,101,[])
if __name__=="__main__": unittest.main()
