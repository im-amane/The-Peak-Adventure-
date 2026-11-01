import unittest
import aiosqlite
from unittest.mock import patch

from premium_system import (
    PremiumError, credit_premium_purchase, get_premium_balance,
    get_premium_packages, init_premium_tables, make_invoice_payload,
    parse_invoice_payload,
)


class PremiumSystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await init_premium_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_invoice_payload_is_bound_to_player_and_package(self):
        payload = make_invoice_payload("spark", 101)
        self.assertEqual(parse_invoice_payload(payload), ("spark", 101))
        with self.assertRaises(PremiumError):
            parse_invoice_payload("peak-gems:spark:0")
        with self.assertRaises(PremiumError):
            parse_invoice_payload("peak-gems:unknown:101")

    async def test_successful_stars_payment_credits_wallet_once(self):
        package = get_premium_packages()["crest"]
        first = await credit_premium_purchase(self.db, 101, "crest", package["stars"], "charge-001", "provider-001")
        second = await credit_premium_purchase(self.db, 101, "crest", package["stars"], "charge-001", "provider-001")
        self.assertTrue(first["credited"])
        self.assertFalse(second["credited"])
        self.assertEqual(first["gems"], package["gems"])
        self.assertEqual(await get_premium_balance(self.db, 101), package["gems"])
        cur = await self.db.execute("SELECT COUNT(*) AS total FROM premium_transactions")
        self.assertEqual((await cur.fetchone())["total"], 1)

    async def test_wrong_paid_amount_and_invalid_player_are_rejected(self):
        package = get_premium_packages()["spark"]
        with self.assertRaises(PremiumError):
            await credit_premium_purchase(self.db, 101, "spark", package["stars"] + 1, "charge-002")
        with self.assertRaises(PremiumError):
            await credit_premium_purchase(self.db, True, "spark", package["stars"], "charge-003")

    async def test_stars_prices_are_configurable_and_bounded(self):
        with patch.dict("os.environ", {"PREMIUM_SPARK_STARS": "35"}):
            self.assertEqual(get_premium_packages()["spark"]["stars"], 35)
        with patch.dict("os.environ", {"PREMIUM_SPARK_STARS": "0"}):
            with self.assertRaises(PremiumError):
                get_premium_packages()


if __name__ == "__main__":
    unittest.main()
