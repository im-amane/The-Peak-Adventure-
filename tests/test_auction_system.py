import unittest
import aiosqlite
from auction_system import *

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
        listing=await create_listing(self.db,1,"armor",100,now=1000)
        await cancel_listing(self.db,1,listing,now=1001)
        row=await self.db.execute("SELECT armor,armor_defense FROM players WHERE user_id=1")
        self.assertEqual(tuple(await row.fetchone()),("Traveler Clothes",0))
    async def test_cannot_cancel_after_bid(self):
        listing=await create_listing(self.db,1,"weapon",100,now=1000)
        await place_bid(self.db,2,listing,100,now=1001)
        with self.assertRaises(AuctionError): await cancel_listing(self.db,1,listing,now=1002)
    async def test_invalid_listing_duration(self):
        with self.assertRaises(AuctionError): await create_listing(self.db,1,"weapon",100,169,now=1000)

if __name__=="__main__": unittest.main()
