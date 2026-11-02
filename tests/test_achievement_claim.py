import sqlite3
import tempfile
import unittest
from pathlib import Path

import main


class AchievementClaimTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "achievement-test.db")
        main.db = None
        await main.init_db()
        self.user_id = 987654799
        await main.get_player(self.user_id, "AchievementHero")
        self.achievement = next(item for item in main.ACHIEVEMENTS if item["kind"] == "wins")
        await main.db.execute(
            "UPDATE players SET wins=? WHERE user_id=?",
            (self.achievement["target"], self.user_id),
        )
        await main.db.commit()
        await main.refresh_achievement_progress(self.user_id)

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def test_achievement_reward_can_only_be_claimed_once(self):
        before = await main.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.user_id,)
        )
        old = await before.fetchone()
        result = await main.claim_achievement_reward(self.user_id, self.achievement["id"])
        self.assertIn("reward claimed", result)
        duplicate = await main.claim_achievement_reward(self.user_id, self.achievement["id"])
        self.assertIn("already claimed", duplicate)
        cur = await main.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.user_id,)
        )
        new = await cur.fetchone()
        self.assertEqual(
            (new["coins"] - old["coins"], new["potions"] - old["potions"]),
            (self.achievement["coins"], self.achievement["potions"]),
        )

    async def test_achievement_claim_preserves_outer_transaction(self):
        await main.db.execute("BEGIN")
        await main.claim_achievement_reward(self.user_id, self.achievement["id"])
        self.assertTrue(main.db.in_transaction)
        await main.db.rollback()
        cur = await main.db.execute(
            "SELECT claimed FROM achievement_progress WHERE user_id=? AND achievement_id=?",
            (self.user_id, self.achievement["id"]),
        )
        self.assertEqual((await cur.fetchone())["claimed"], 0)
        cur = await main.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.user_id,)
        )
        player = await cur.fetchone()
        self.assertEqual((player["coins"], player["potions"]), (0, 3))

    async def test_failed_player_wallet_update_does_not_consume_claim(self):
        await main.db.execute(
            f"""CREATE TRIGGER ignore_achievement_wallet
                BEFORE UPDATE OF coins ON players WHEN OLD.user_id={self.user_id}
                BEGIN SELECT RAISE(IGNORE); END"""
        )
        await main.db.commit()
        with self.assertRaisesRegex(RuntimeError, "wallet update failed"):
            await main.claim_achievement_reward(self.user_id, self.achievement["id"])
        self.assertFalse(main.db.in_transaction)
        cur = await main.db.execute(
            "SELECT claimed FROM achievement_progress WHERE user_id=? AND achievement_id=?",
            (self.user_id, self.achievement["id"]),
        )
        self.assertEqual((await cur.fetchone())["claimed"], 0)
        cur = await main.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.user_id,)
        )
        player = await cur.fetchone()
        self.assertEqual((player["coins"], player["potions"]), (0, 3))

    async def test_ignored_claim_update_rolls_back_wallet_credit(self):
        await main.db.execute(
            f"""CREATE TRIGGER ignore_achievement_claim
                BEFORE UPDATE OF claimed ON achievement_progress
                WHEN OLD.user_id={self.user_id}
                BEGIN SELECT RAISE(IGNORE); END"""
        )
        await main.db.commit()
        with self.assertRaisesRegex(RuntimeError, "already claimed"):
            await main.claim_achievement_reward(self.user_id, self.achievement["id"])
        cur = await main.db.execute(
            "SELECT claimed FROM achievement_progress WHERE user_id=? AND achievement_id=?",
            (self.user_id, self.achievement["id"]),
        )
        self.assertEqual((await cur.fetchone())["claimed"], 0)
        cur = await main.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.user_id,)
        )
        player = await cur.fetchone()
        self.assertEqual((player["coins"], player["potions"]), (0, 3))


if __name__ == "__main__":
    unittest.main()
