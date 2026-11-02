import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main


class FakeDuelMessage:
    def __init__(self):
        self.text = None
        self.reply_markup = None

    async def edit_text(self, text, reply_markup=None):
        self.text = text
        self.reply_markup = reply_markup


class FakeDuelCallback:
    def __init__(self, user_id, data):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.message = FakeDuelMessage()
        self.answer_args = None

    async def answer(self, *args, **kwargs):
        self.answer_args = (args, kwargs)


class DuelCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "duel-test.db")
        main.db = None
        await main.init_db()
        self.challenger_id = 987654701
        self.opponent_id = 987654702
        await main.get_player(self.challenger_id, "DuelChallenger")
        await main.get_player(self.opponent_id, "DuelOpponent")

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def _create_duel(self, opponent_hp=1000):
        cur = await main.db.execute(
            """INSERT INTO duels(
                 chat_id,challenger_id,opponent_id,challenger_hp,opponent_hp,
                 turn_user_id,status
               ) VALUES(?,?,?,?,?,?,'active')""",
            (12345,self.challenger_id,self.opponent_id,1000,opponent_hp,self.challenger_id),
        )
        await main.db.commit()
        return cur.lastrowid

    async def test_duplicate_callback_cannot_reuse_the_same_turn(self):
        duel_id = await self._create_duel()
        callback = FakeDuelCallback(
            self.challenger_id, f"duel_action:attack:{duel_id}"
        )
        with patch("main.random.randint", return_value=0):
            await main.duel_action(callback)
            await main.duel_action(callback)

        cur = await main.db.execute(
            "SELECT opponent_hp,turn_user_id,status FROM duels WHERE duel_id=?",
            (duel_id,),
        )
        duel = await cur.fetchone()
        self.assertEqual(duel["opponent_hp"], 995)
        self.assertEqual(duel["turn_user_id"], self.opponent_id)
        self.assertEqual(duel["status"], "active")
        self.assertTrue(callback.answer_args[1].get("show_alert"))

    async def test_failed_pvp_stat_update_rolls_back_duel_finish(self):
        duel_id = await self._create_duel(opponent_hp=1)
        await main.db.execute(
            f"""CREATE TRIGGER reject_duel_pvp_win
                BEFORE UPDATE OF pvp_wins ON players
                WHEN OLD.user_id={self.challenger_id}
                BEGIN SELECT RAISE(ABORT,'pvp stats unavailable'); END"""
        )
        await main.db.commit()
        callback = FakeDuelCallback(
            self.challenger_id, f"duel_action:attack:{duel_id}"
        )

        with patch("main.random.randint", return_value=0):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "pvp stats unavailable"):
                await main.duel_action(callback)

        self.assertFalse(main.db.in_transaction)
        cur = await main.db.execute(
            "SELECT opponent_hp,status,winner_id FROM duels WHERE duel_id=?",
            (duel_id,),
        )
        duel = await cur.fetchone()
        self.assertEqual(
            (duel["opponent_hp"],duel["status"],duel["winner_id"]),
            (1,"active",None),
        )
        cur = await main.db.execute(
            "SELECT pvp_wins,pvp_losses FROM players WHERE user_id=?",
            (self.challenger_id,),
        )
        stats = await cur.fetchone()
        self.assertEqual((stats["pvp_wins"],stats["pvp_losses"]),(0,0))


if __name__ == "__main__":
    unittest.main()
