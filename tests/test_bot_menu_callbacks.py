import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import main


class PvpRankMenuCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "pvp-menu-test.db")
        main.db = None
        await main.init_db()
        self.user_id = 987654992
        await main.get_player(self.user_id, "RankMenuHero")
        await main.db.execute(
            "UPDATE players SET pvp_wins=7,pvp_losses=2 WHERE user_id=?",
            (self.user_id,),
        )
        await main.db.commit()

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def test_pvp_rank_menu_callback_displays_rankings(self):
        callback = SimpleNamespace(
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )

        await main.cb_pvprank(callback)

        callback.answer.assert_awaited_once()
        callback.message.answer.assert_awaited_once()
        response = callback.message.answer.call_args.args[0]
        self.assertIn("PvP Rankings", response)
        self.assertIn("RankMenuHero", response)
        self.assertIn("7W / 2L", response)


if __name__ == "__main__":
    unittest.main()
