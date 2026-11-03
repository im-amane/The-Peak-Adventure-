import asyncio
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import aiosqlite
from auction_system import *
from auction_system import _for_update, _settle_due

class AuctionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db=await aiosqlite.connect(":memory:")
        self.db.row_factory=aiosqlite.Row
        await self.db.executescript("""
        CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER NOT NULL,
          weapon TEXT NOT NULL,weapon_attack INTEGER NOT NULL,armor TEXT NOT NULL,armor_defense INTEGER NOT NULL);
        INSERT INTO players VALUES(1,100,'Stormblade',25,'Traveler Clothes',0);
        INSERT INTO players VALUES(2,1000,'Rusty Sword',0,'Dragon Mail',40);
        INSERT INTO players VALUES(3,1000,'Rusty Sword',0,'Traveler Clothes',0);
        CREATE TABLE battles(user_id INTEGER PRIMARY KEY);
        CREATE TABLE duels(
          duel_id INTEGER PRIMARY KEY AUTOINCREMENT,
          challenger_id INTEGER NOT NULL,opponent_id INTEGER NOT NULL,
          status TEXT NOT NULL
        );
        CREATE TABLE trades(
          trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
          initiator_id INTEGER NOT NULL,partner_id INTEGER NOT NULL,
          status TEXT NOT NULL
        );
        CREATE TABLE matchmaking_queue(user_id INTEGER PRIMARY KEY,status TEXT NOT NULL,queued_at INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE dungeon_runs(user_id INTEGER PRIMARY KEY,status TEXT NOT NULL);
        """)
        await init_auction_tables(self.db)
    async def asyncTearDown(self): await self.db.close()
    async def test_create_listing_removes_item_from_seller(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        row=await self.db.execute("SELECT weapon,weapon_attack FROM players WHERE user_id=1")
        self.assertEqual(tuple(await row.fetchone()),("Rusty Sword",0))
        self.assertIsNotNone(await get_auction(self.db,listing,1001))
    async def test_bid_and_outbid_refund(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        await place_bid(self.db,3,listing,105,now=1002)
        row=await self.db.execute("SELECT coins FROM players WHERE user_id=2")
        self.assertEqual((await row.fetchone())["coins"],1000)
        row=await self.db.execute("SELECT coins FROM players WHERE user_id=3")
        self.assertEqual((await row.fetchone())["coins"],895)
    async def test_seller_cannot_bid(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        with self.assertRaises(AuctionError): await place_bid(self.db,1,listing,100,now=1001)
    async def test_insufficient_funds(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        with self.assertRaises(AuctionError): await place_bid(self.db,3,listing,2000,now=1001)
    async def test_minimum_increment(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        with self.assertRaises(AuctionError): await place_bid(self.db,3,listing,101,now=1002)
    async def test_expiry_settles_item_and_coins(self):
        listing=await create_listing(self.db,1,"weapon",100,1,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        await list_active_auctions(self.db,now=4601)
        row=await self.db.execute("SELECT weapon,weapon_attack FROM players WHERE user_id=2")
        self.assertEqual(tuple(await row.fetchone()),("Stormblade",25))
        row=await self.db.execute("SELECT coins FROM players WHERE user_id=1")
        self.assertEqual((await row.fetchone())["coins"],200)
    async def test_no_bid_expiry_returns_item(self):
        listing=await create_listing(self.db,1,"weapon",100,1,now=1000)
        await list_active_auctions(self.db,now=4601)
        row=await self.db.execute("SELECT weapon FROM players WHERE user_id=1")
        self.assertEqual((await row.fetchone())["weapon"],"Stormblade")
    async def test_cancel_without_bid(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        await cancel_listing(self.db,1,listing,now=1001)
        row=await self.db.execute("SELECT weapon,weapon_attack FROM players WHERE user_id=1")
        self.assertEqual(tuple(await row.fetchone()),("Stormblade",25))
    async def test_cannot_cancel_after_bid(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        with self.assertRaises(AuctionError): await cancel_listing(self.db,1,listing,now=1002)

    async def test_cancel_locks_listing_row_before_checking_for_bids(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        with patch("auction_system._for_update", wraps=_for_update) as lock_query:
            await cancel_listing(self.db,1,listing,now=1001)

        self.assertTrue(any(
            "SELECT * FROM auction_listings WHERE listing_id=? AND status='active'" in call.args[1]
            for call in lock_query.call_args_list
        ))
    async def test_buyer_old_equipment_is_preserved_in_stash(self):
        listing=await create_listing(self.db,1,"weapon",100,1,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        await list_active_auctions(self.db,now=4601)
        stash=await list_stash(self.db,2)
        self.assertEqual(len(stash),1)
        self.assertEqual((stash[0]["item_name"],stash[0]["item_stat"]),("Rusty Sword",0))
        name,slot,stat=await equip_stashed_item(self.db,2,stash[0]["stash_id"])
        self.assertEqual((name,slot,stat),("Rusty Sword","weapon",0))


    async def test_cannot_list_equipment_during_battle(self):
        await self.db.execute("INSERT INTO battles VALUES(1)")
        await self.db.commit()
        with self.assertRaisesRegex(AuctionError,"active battle"):
            await create_listing(self.db,1,"weapon",100,now=1000)

    async def test_auction_item_goes_to_stash_if_buyer_is_in_battle(self):
        listing=await create_listing(self.db,1,"weapon",100,1,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        await self.db.execute("INSERT INTO battles VALUES(2)")
        await list_active_auctions(self.db,now=4601)
        row=await self.db.execute("SELECT weapon FROM players WHERE user_id=2")
        self.assertEqual((await row.fetchone())["weapon"],"Rusty Sword")
        stash=await list_stash(self.db,2)
        self.assertEqual(stash[0]["item_name"],"Stormblade")

    async def test_cannot_list_or_equip_items_during_active_duel(self):
        await self.db.execute("INSERT INTO duels(challenger_id,opponent_id,status) VALUES(1,2,'active')")
        await self.db.commit()
        with self.assertRaisesRegex(AuctionError,"active duel, trade, PvP queue, or dungeon"):
            await create_listing(self.db,1,"weapon",100,now=1000)

        await self.db.execute(
            "INSERT INTO auction_stash(user_id,slot,item_name,item_stat,created_at) VALUES(1,'weapon','Stormblade',25,1000)"
        )
        await self.db.commit()
        stash = await list_stash(self.db,1)
        with self.assertRaisesRegex(AuctionError,"active duel, trade, PvP queue, or dungeon"):
            await equip_stashed_item(self.db,1,stash[0]["stash_id"])

    async def test_cannot_list_or_equip_items_during_open_trade(self):
        await self.db.execute("INSERT INTO trades(initiator_id,partner_id,status) VALUES(1,2,'open')")
        await self.db.commit()
        with self.assertRaisesRegex(AuctionError,"active duel, trade, PvP queue, or dungeon"):
            await create_listing(self.db,1,"weapon",100,now=1000)

    async def test_auction_expiry_stashes_gear_if_buyer_is_in_a_duel(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        await self.db.execute("INSERT INTO duels(challenger_id,opponent_id,status) VALUES(2,3,'active')")
        await self.db.commit()
        await list_active_auctions(self.db,now=1000+24*3600+1)

        row=await self.db.execute("SELECT weapon,weapon_attack FROM players WHERE user_id=2")
        self.assertEqual(tuple(await row.fetchone()),("Rusty Sword",0))
        stash=await list_stash(self.db,2)
        self.assertEqual(stash[0]["item_name"],"Stormblade")

    async def test_auction_expiry_returns_seller_item_to_stash_during_duel(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        await self.db.execute("INSERT INTO duels(challenger_id,opponent_id,status) VALUES(1,2,'active')")
        await self.db.commit()
        await list_active_auctions(self.db,now=1000+24*3600+1)

        row=await self.db.execute("SELECT weapon,weapon_attack FROM players WHERE user_id=1")
        self.assertEqual(tuple(await row.fetchone()),("Rusty Sword",0))
        stash=await list_stash(self.db,1)
        self.assertEqual(stash[0]["item_name"],"Stormblade")

    async def test_cannot_list_or_equip_items_while_queued_for_pvp(self):
        await self.db.execute("INSERT INTO matchmaking_queue(user_id,status) VALUES(1,'queued')")
        await self.db.commit()
        with self.assertRaisesRegex(AuctionError,"active duel, trade, PvP queue, or dungeon"):
            await create_listing(self.db,1,"weapon",100,now=1000)

        await self.db.execute(
            "INSERT INTO auction_stash(user_id,slot,item_name,item_stat,created_at) VALUES(1,'weapon','Stormblade',25,1000)"
        )
        await self.db.commit()
        stash = await list_stash(self.db,1)
        with self.assertRaisesRegex(AuctionError,"active duel, trade, PvP queue, or dungeon"):
            await equip_stashed_item(self.db,1,stash[0]["stash_id"])

    async def test_auction_expiry_stashes_gear_if_buyer_is_queued(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        await self.db.execute("INSERT INTO matchmaking_queue(user_id,status) VALUES(2,'queued')")
        await self.db.commit()
        await list_active_auctions(self.db,now=1000+24*3600+1)

        row=await self.db.execute("SELECT weapon,weapon_attack FROM players WHERE user_id=2")
        self.assertEqual(tuple(await row.fetchone()),("Rusty Sword",0))
        stash=await list_stash(self.db,2)
        self.assertEqual(stash[0]["item_name"],"Stormblade")

    async def test_cannot_change_equipment_during_active_dungeon(self):
        await self.db.execute("INSERT INTO dungeon_runs(user_id,status) VALUES(1,'active')")
        await self.db.commit()
        with self.assertRaisesRegex(AuctionError,"active duel, trade, PvP queue, or dungeon"):
            await create_listing(self.db,1,"weapon",100,now=1000)

        await self.db.execute(
            "INSERT INTO auction_stash(user_id,slot,item_name,item_stat,created_at) VALUES(1,'weapon','Stormblade',25,1000)"
        )
        await self.db.commit()
        stash = await list_stash(self.db,1)
        with self.assertRaisesRegex(AuctionError,"active duel, trade, PvP queue, or dungeon"):
            await equip_stashed_item(self.db,1,stash[0]["stash_id"])

    async def test_auction_expiry_stashes_gear_if_buyer_is_in_a_dungeon(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        await self.db.execute("INSERT INTO dungeon_runs(user_id,status) VALUES(2,'active')")
        await self.db.commit()
        await list_active_auctions(self.db,now=1000+24*3600+1)

        row=await self.db.execute("SELECT weapon,weapon_attack FROM players WHERE user_id=2")
        self.assertEqual(tuple(await row.fetchone()),("Rusty Sword",0))
        stash=await list_stash(self.db,2)
        self.assertEqual(stash[0]["item_name"],"Stormblade")

    async def test_auction_ids_bids_and_timestamps_reject_invalid_types(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        for bad in (True,0,-1,"1"):
            with self.subTest(value=bad),self.assertRaises(AuctionError):
                await place_bid(self.db,bad,listing,100,now=1001)
            with self.subTest(value=bad),self.assertRaises(AuctionError):
                await cancel_listing(self.db,bad,listing,now=1001)
        for bad in (True,1.5,"1001",-1):
            with self.subTest(timestamp=bad),self.assertRaises(AuctionError):
                await place_bid(self.db,2,listing,100,now=bad)
        for bad in (True,0,1.5,10_000_001):
            with self.subTest(amount=bad),self.assertRaises(AuctionError):
                await place_bid(self.db,2,listing,bad,now=1001)

    async def test_auction_query_and_stash_ids_are_validated(self):
        for bad in (True,0,-1,"1"):
            with self.subTest(user_id=bad),self.assertRaises(AuctionError):
                await list_stash(self.db,bad)
            with self.subTest(listing_id=bad),self.assertRaises(AuctionError):
                await get_auction(self.db,bad,now=1000)
        for bad in (True,0,-1,1.5):
            with self.subTest(limit=bad),self.assertRaises(AuctionError):
                await list_active_auctions(self.db,now=1000,limit=bad)
        for user_id,stash_id in ((True,1),(1,True),(0,1),(1,0)):
            with self.subTest(user_id=user_id,stash_id=stash_id),self.assertRaises(AuctionError):
                await equip_stashed_item(self.db,user_id,stash_id)

    async def test_invalid_auction_slot_and_timestamp_are_rejected(self):
        for slot in ([],None,"ring"):
            with self.subTest(slot=slot),self.assertRaises(AuctionError):
                await create_listing(self.db,1,slot,100,now=1000)
        for timestamp in (True,1.5,"1000",-1):
            with self.subTest(timestamp=timestamp),self.assertRaises(AuctionError):
                await create_listing(self.db,1,"weapon",100,now=timestamp)

    async def test_concurrent_expiry_settlement_pays_and_delivers_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/"auction-race.db")
            first=await aiosqlite.connect(path)
            first.row_factory=aiosqlite.Row
            await first.executescript("""
            CREATE TABLE players(user_id INTEGER PRIMARY KEY,coins INTEGER NOT NULL,
              weapon TEXT NOT NULL,weapon_attack INTEGER NOT NULL,armor TEXT NOT NULL,armor_defense INTEGER NOT NULL);
            INSERT INTO players VALUES(1,100,'Stormblade',25,'Traveler Clothes',0);
            INSERT INTO players VALUES(2,1000,'Rusty Sword',0,'Dragon Mail',40);
            CREATE TABLE battles(user_id INTEGER PRIMARY KEY);
            """)
            await init_auction_tables(first)
            listing=await create_listing(first,1,"weapon",100,1,now=1000)
            await place_bid(first,2,listing,100,now=1001)
            second=await aiosqlite.connect(path)
            second.row_factory=aiosqlite.Row
            try:
                await asyncio.gather(
                    _settle_due(first,4601),
                    _settle_due(second,4601),
                )
                cur=await first.execute("SELECT coins FROM players WHERE user_id=1")
                self.assertEqual((await cur.fetchone())["coins"],200)
                cur=await first.execute("SELECT coins,weapon,weapon_attack FROM players WHERE user_id=2")
                buyer=await cur.fetchone()
                self.assertEqual((buyer["coins"],buyer["weapon"],buyer["weapon_attack"]),(900,"Stormblade",25))
                cur=await first.execute("SELECT COUNT(*) AS n FROM auction_stash WHERE user_id=2")
                self.assertEqual((await cur.fetchone())["n"],1)
                cur=await first.execute("SELECT status FROM auction_listings WHERE listing_id=?",(listing,))
                self.assertEqual((await cur.fetchone())["status"],"sold")
            finally:
                await second.close()
                await first.close()

    async def test_no_bid_expiry_preserves_equipment_acquired_during_listing(self):
        listing=await create_listing(self.db,1,"weapon",100,1,now=1000)
        await self.db.execute(
            "UPDATE players SET weapon='New Blade',weapon_attack=12 WHERE user_id=1"
        )
        await self.db.commit()

        await list_active_auctions(self.db,now=4601)

        cur=await self.db.execute("SELECT weapon,weapon_attack FROM players WHERE user_id=1")
        self.assertEqual(tuple(await cur.fetchone()),("Stormblade",25))
        stash=await list_stash(self.db,1)
        self.assertEqual([(x["item_name"],x["item_stat"]) for x in stash],[("New Blade",12)])

    async def test_cancel_preserves_equipment_acquired_during_listing(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        await self.db.execute(
            "UPDATE players SET weapon='New Blade',weapon_attack=12 WHERE user_id=1"
        )
        await self.db.commit()

        await cancel_listing(self.db,1,listing,now=1001)

        cur=await self.db.execute("SELECT weapon,weapon_attack FROM players WHERE user_id=1")
        self.assertEqual(tuple(await cur.fetchone()),("Stormblade",25))
        stash=await list_stash(self.db,1)
        self.assertEqual([(x["item_name"],x["item_stat"]) for x in stash],[("New Blade",12)])

    async def test_missing_buyer_cannot_trigger_seller_payout(self):
        listing=await create_listing(self.db,1,"weapon",100,1,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        await self.db.execute(
            "UPDATE players SET weapon='New Blade',weapon_attack=12 WHERE user_id=1"
        )
        await self.db.execute("DELETE FROM players WHERE user_id=2")
        await self.db.commit()

        await list_active_auctions(self.db,now=4601)

        cur=await self.db.execute("SELECT coins FROM players WHERE user_id=1")
        self.assertEqual((await cur.fetchone())["coins"],100)
        cur=await self.db.execute("SELECT status FROM auction_listings WHERE listing_id=?",(listing,))
        self.assertEqual((await cur.fetchone())["status"],"expired")
        stash=await list_stash(self.db,1)
        self.assertEqual([(x["item_name"],x["item_stat"]) for x in stash],[("New Blade",12)])

    async def test_missing_seller_refunds_existing_buyer(self):
        listing=await create_listing(self.db,1,"weapon",100,1,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        await self.db.execute("DELETE FROM players WHERE user_id=1")
        await self.db.commit()

        await list_active_auctions(self.db,now=4601)

        cur=await self.db.execute("SELECT coins FROM players WHERE user_id=2")
        self.assertEqual((await cur.fetchone())["coins"],1000)
        cur=await self.db.execute("SELECT status FROM auction_listings WHERE listing_id=?",(listing,))
        self.assertEqual((await cur.fetchone())["status"],"expired")

    async def test_invalid_listing_duration(self):
        with self.assertRaises(AuctionError): await create_listing(self.db,1,"weapon",100,169,now=1000)


    async def test_table_initialization_preserves_outer_transaction(self):
        await self.db.commit()
        await self.db.execute("BEGIN")
        await self.db.execute("UPDATE players SET weapon='Pending Blade' WHERE user_id=1")
        await init_auction_tables(self.db)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cur=await self.db.execute("SELECT weapon FROM players WHERE user_id=1")
        self.assertEqual((await cur.fetchone())["weapon"],"Stormblade")

if __name__=="__main__": unittest.main()
