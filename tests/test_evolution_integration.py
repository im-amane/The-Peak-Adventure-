import tempfile
import unittest
from pathlib import Path

import main


class EvolutionDatabaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "evolution-test.db")
        main.db = None
        await main.init_db()

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def test_evolution_mastery_and_battle_flag_are_initialized(self):
        cur = await main.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='player_monster_mastery'"
        )
        self.assertIsNotNone(await cur.fetchone())
        cur = await main.db.execute("PRAGMA table_info(battles)")
        columns = {row["name"] for row in await cur.fetchall()}
        self.assertIn("is_evolved", columns)


if __name__ == "__main__":
    unittest.main()
