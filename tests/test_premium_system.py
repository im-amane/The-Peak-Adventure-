import unittest
import aiosqlite
from unittest.mock import patch

from premium_system import (
    PREMIUM_SHOP_ITEMS, PremiumError, buy_premium_item, consume_xp_boost,
    credit_premium_purchase, get_premium_balance, get_premium_packages,
    init_premium_tables, make_invoice_payload, parse_invoice_payload,
)


class PremiumSystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("CREATE TABLE players(user_id INTEGER PRIMARY KEY,potions INTEGER NOT NULL DEFAULT 0)")
        await self.db.execute("CREATE TABLE player_stamina(user_id INTEGER PRIMARY KEY,stamina INTEGER NOT NULL,updated_at INTEGER NOT NULL)")
        await self.db.execute("INSERT INTO players(user_id,potions) VALUES(101,2)")
        await self.db.execute("INSERT INTO player_stamina VALUES(101,30,1800000000)")
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

    async def test_shop_purchases_apply_effects_and_deduct_gems(self):
        await self.db.execute("INSERT INTO premium_wallets(user_id,balance) VALUES(101,200)")
        await self.db.commit()
        potion = await buy_premium_item(self.db, 101, "potion_bundle")
        self.assertEqual(potion["balance"], 160)
        cur = await self.db.execute("SELECT potions FROM players WHERE user_id=101")
        self.assertEqual((await cur.fetchone())["potions"], 7)
        stamina = await buy_premium_item(self.db, 101, "stamina_crystal")
        self.assertEqual(stamina["balance"], 135)
        cur = await self.db.execute("SELECT stamina FROM player_stamina WHERE user_id=101")
        self.assertEqual((await cur.fetchone())["stamina"], 80)

    async def test_xp_charm_adds_three_wins_and_is_consumed_once_per_victory(self):
        await self.db.execute("INSERT INTO premium_wallets(user_id,balance) VALUES(101,100)")
        await self.db.commit()
        await buy_premium_item(self.db, 101, "xp_charm")
        self.assertTrue(await consume_xp_boost(self.db, 101))
        self.assertTrue(await consume_xp_boost(self.db, 101))
        self.assertTrue(await consume_xp_boost(self.db, 101))
        self.assertFalse(await consume_xp_boost(self.db, 101))
        await self.db.commit()

    async def test_xp_boost_rejects_invalid_player_id(self):
        with self.assertRaises(PremiumError):
            await consume_xp_boost(self.db, True)

    async def test_shop_purchase_preserves_outer_transaction(self):
        await self.db.commit()
        await self.db.execute("INSERT INTO premium_wallets(user_id,balance) VALUES(101,100)")
        await buy_premium_item(self.db, 101, "potion_bundle")
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertEqual(await get_premium_balance(self.db, 101), 0)
        cur = await self.db.execute("SELECT potions FROM players WHERE user_id=101")
        self.assertEqual((await cur.fetchone())["potions"], 2)

    async def test_shop_rejects_insufficient_balance_without_partial_effect(self):
        await self.db.execute("INSERT INTO premium_wallets(user_id,balance) VALUES(101,10)")
        await self.db.commit()
        with self.assertRaises(PremiumError):
            await buy_premium_item(self.db, 101, "potion_bundle")
        cur = await self.db.execute("SELECT potions FROM players WHERE user_id=101")
        self.assertEqual((await cur.fetchone())["potions"], 2)
        self.assertEqual(await get_premium_balance(self.db, 101), 10)

    async def test_stars_purchase_requires_registered_player(self):
        package = get_premium_packages()["spark"]
        with self.assertRaisesRegex(PremiumError, "Player account not found"):
            await credit_premium_purchase(self.db, 202, "spark", package["stars"], "charge-unregistered")
        self.assertEqual(await get_premium_balance(self.db, 202), 0)

    async def test_payment_credit_preserves_outer_transaction(self):
        await self.db.commit()
        await self.db.execute("UPDATE players SET potions=potions WHERE user_id=101")
        package = get_premium_packages()["spark"]
        await credit_premium_purchase(self.db, 101, "spark", package["stars"], "charge-nested")
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertEqual(await get_premium_balance(self.db, 101), 0)
        cur = await self.db.execute("SELECT COUNT(*) AS total FROM premium_transactions")
        self.assertEqual((await cur.fetchone())["total"], 0)

    async def test_charge_id_cannot_be_replayed_for_another_account(self):
        package = get_premium_packages()["spark"]
        await credit_premium_purchase(self.db, 101, "spark", package["stars"], "charge-replay")
        await self.db.execute("INSERT INTO players(user_id,potions) VALUES(202,0)")
        await self.db.commit()
        with self.assertRaisesRegex(PremiumError, "different purchase"):
            await credit_premium_purchase(self.db, 202, "spark", package["stars"], "charge-replay")
        self.assertEqual(await get_premium_balance(self.db, 202), 0)

    async def test_invoice_package_type_is_validated(self):
        with self.assertRaises(PremiumError):
            make_invoice_payload([], 101)

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
