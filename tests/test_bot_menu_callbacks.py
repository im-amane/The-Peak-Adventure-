import re
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

    def test_every_static_menu_callback_has_a_registered_handler(self):
        source = Path(main.__file__).read_text(encoding="utf-8")
        callback_values = set(
            re.findall(r'callback_data\s*=\s*"([^"]+)"', source)
        )
        exact_handlers = set(
            re.findall(r'F\.data\s*==\s*"([^"]+)"', source)
        )
        prefix_handlers = re.findall(
            r'F\.data\.startswith\("([^"]+)"\)', source
        )
        for group in re.findall(r'F\.data\.in_\(\{([^}]+)\}\)', source):
            exact_handlers.update(re.findall(r'"([^"]+)"', group))
        unhandled = sorted(
            value for value in callback_values
            if value not in exact_handlers
            and not any(value.startswith(prefix) for prefix in prefix_handlers)
        )
        self.assertEqual(unhandled, [])

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
