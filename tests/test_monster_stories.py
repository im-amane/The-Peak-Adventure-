import json
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class MonsterStoryEditorialTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.monsters=json.loads((ROOT/"monsters.json").read_text(encoding="utf-8"))
 def test_exactly_one_hundred_monsters_have_stories(self):
  self.assertEqual(len(self.monsters),100)
  self.assertTrue(all(isinstance(m.get("story"),str) and len(m["story"])>=100 for m in self.monsters))
 def test_every_monster_story_is_unique(self):
  stories=[m["story"] for m in self.monsters]
  self.assertEqual(len(set(stories)),100)
 def test_stories_cover_all_ten_world_arcs(self):
  arcs={m["story"].split("]",1)[0] for m in self.monsters}
  self.assertEqual(len(arcs),10)
 def test_monsters_are_ordered_from_level_one_to_one_hundred(self):
  self.assertEqual([m["level"] for m in self.monsters],list(range(1,101)))
 def test_boss_stories_close_each_world_arc(self):
  bosses=[m for m in self.monsters if m["boss"]]
  self.assertEqual(len(bosses),10)
  self.assertTrue(all(m["level"]%10==0 and len(m["story"])>=180 for m in bosses))
if __name__=="__main__":unittest.main()
