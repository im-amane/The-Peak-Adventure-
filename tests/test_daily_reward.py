import tempfile
import unittest
from pathlib import Path

import main


class DailyRewardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_path = main.DB_PATH
        self.previous_db = main.db
        main.DB_PATH = str(Path(self.temp_dir.name) / "daily-reward-test.db")
        main.db = None
        await main.init_db()
        self.user_id = 987654797
        await main.get_player(self.user_id, "DailyRewardHero")
        await main.db.commit()

    async def asyncTearDown(self):
        if main.db is not None:
            await main.db.close()
        main.db = self.previous_db
        main.DB_PATH = self.previous_path
        self.temp_dir.cleanup()

    async def test_daily_reward_uses_rolling_24_hour_cooldown(self):
        self.assertTrue(await main.claim_daily_reward(self.user_id, now=100000))
        self.assertFalse(await main.claim_daily_reward(self.user_id, now=100001))
        self.assertTrue(await main.claim_daily_reward(self.user_id, now=186400))
        cur = await main.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.user_id,)
        )
        player = await cur.fetchone()
        self.assertEqual((player["coins"],player["potions"]),(100,5))

    async def test_daily_reward_preserves_outer_transaction(self):
        await main.db.execute("BEGIN")
        self.assertTrue(await main.claim_daily_reward(self.user_id, now=100000))
        self.assertTrue(main.db.in_transaction)
        await main.db.rollback()
        cur = await main.db.execute(
            "SELECT 1 FROM daily_claims WHERE user_id=?", (self.user_id,)
        )
        self.assertIsNone(await cur.fetchone())
        cur = await main.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.user_id,)
        )
        player = await cur.fetchone()
        self.assertEqual((player["coins"],player["potions"]),(0,3))

    async def test_failed_wallet_credit_rolls_back_daily_claim(self):
        await main.db.execute(
            f"""CREATE TRIGGER ignore_daily_wallet
                BEFORE UPDATE OF coins ON players WHEN OLD.user_id={self.user_id}
                BEGIN SELECT RAISE(IGNORE); END"""
        )
        await main.db.commit()
        with self.assertRaisesRegex(RuntimeError,"wallet update failed"):
            await main.claim_daily_reward(self.user_id,now=100000)
        self.assertFalse(main.db.in_transaction)
        cur = await main.db.execute(
            "SELECT 1 FROM daily_claims WHERE user_id=?", (self.user_id,)
        )
        self.assertIsNone(await cur.fetchone())
        cur = await main.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.user_id,)
        )
        player = await cur.fetchone()
        self.assertEqual((player["coins"],player["potions"]),(0,3))

    async def test_invalid_daily_reward_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            await main.claim_daily_reward(self.user_id,now=True)


if __name__ == "__main__":
    unittest.main()
