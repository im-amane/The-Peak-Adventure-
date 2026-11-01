"""Transactional player auction house for equipped weapons and armor."""
import time
import aiosqlite

class AuctionError(ValueError):
    pass

DEFAULTS = {"weapon": ("Rusty Sword", 0), "armor": ("Traveler Clothes", 0)}

async def init_auction_tables(db):
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS auction_listings (
      listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
      seller_id INTEGER NOT NULL,
      slot TEXT NOT NULL CHECK(slot IN ('weapon','armor')),
      item_name TEXT NOT NULL,
      item_stat INTEGER NOT NULL CHECK(item_stat >= 0),
      start_price INTEGER NOT NULL CHECK(start_price > 0),
      current_bid INTEGER NOT NULL DEFAULT 0,
      highest_bidder INTEGER,
      ends_at INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','sold','expired','cancelled')),
      created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_auction_active ON auction_listings(status, ends_at);
    CREATE INDEX IF NOT EXISTS idx_auction_seller ON auction_listings(seller_id, status);
    CREATE TABLE IF NOT EXISTS auction_stash(
      stash_id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,
      slot TEXT NOT NULL CHECK(slot IN ('weapon','armor')),item_name TEXT NOT NULL,
      item_stat INTEGER NOT NULL,source_listing_id INTEGER,created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_auction_stash_user ON auction_stash(user_id,stash_id);
    """)
    await db.commit()

async def _has_active_battle(db, user_id):
    cur = await db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='battles'")
    if not await cur.fetchone():
        return False
    cur = await db.execute("SELECT 1 FROM battles WHERE user_id=?", (user_id,))
    return await cur.fetchone() is not None

async def _settle_due(db, now):
    cur = await db.execute("SELECT * FROM auction_listings WHERE status='active' AND ends_at<=?", (now,))
    rows = await cur.fetchall()
    for row in rows:
        if row["highest_bidder"] is not None:
            seller = await db.execute("UPDATE players SET coins=coins+? WHERE user_id=?", (row["current_bid"], row["seller_id"]))
            buyer = await db.execute("SELECT 1 FROM players WHERE user_id=?", (row["highest_bidder"],))
            if seller.rowcount and await buyer.fetchone():
                column = row["slot"]
                stat_column = "weapon_attack" if column == "weapon" else "armor_defense"
                current = await db.execute(f"SELECT {column}, {stat_column} FROM players WHERE user_id=?", (row["highest_bidder"],))
                equipped = await current.fetchone()
                default_name, default_stat = DEFAULTS[column]
                if await _has_active_battle(db, row["highest_bidder"]):
                    await db.execute("INSERT INTO auction_stash(user_id,slot,item_name,item_stat,source_listing_id,created_at) VALUES(?,?,?,?,?,?)",
                      (row["highest_bidder"],column,row["item_name"],row["item_stat"],row["listing_id"],now))
                else:
                    if equipped and (equipped[column] != default_name or equipped[stat_column] != default_stat):
                        await db.execute("INSERT INTO auction_stash(user_id,slot,item_name,item_stat,source_listing_id,created_at) VALUES(?,?,?,?,?,?)",
                          (row["highest_bidder"],column,equipped[column],equipped[stat_column],row["listing_id"],now))
                    await db.execute(f"UPDATE players SET {column}=?, {stat_column}=? WHERE user_id=?", (row["item_name"], row["item_stat"], row["highest_bidder"]))
                await db.execute("UPDATE auction_listings SET status='sold' WHERE listing_id=?", (row["listing_id"],))
            else:
                await db.execute("UPDATE players SET coins=coins+? WHERE user_id=?", (row["current_bid"], row["highest_bidder"]))
                await db.execute("UPDATE auction_listings SET status='expired' WHERE listing_id=?", (row["listing_id"],))
        else:
            column = "weapon" if row["slot"] == "weapon" else "armor"
            stat_column = "weapon_attack" if row["slot"] == "weapon" else "armor_defense"
            await db.execute(f"UPDATE players SET {column}=?, {stat_column}=? WHERE user_id=?", (row["item_name"], row["item_stat"], row["seller_id"]))
            await db.execute("UPDATE auction_listings SET status='expired' WHERE listing_id=?", (row["listing_id"],))
    if rows:
        await db.commit()

async def create_listing(db, seller_id, slot, start_price, duration_hours=24, now=None):
    now = int(time.time()) if now is None else int(now)
    if not isinstance(seller_id, int) or isinstance(seller_id, bool) or seller_id <= 0:
        raise AuctionError("Invalid seller account.")
    if slot not in DEFAULTS:
        raise AuctionError("Only equipped weapons and armor can be listed.")
    if not isinstance(start_price, int) or isinstance(start_price, bool) or not 1 <= start_price <= 10_000_000:
        raise AuctionError("Starting bid must be between 1 and 10,000,000 coins.")
    if not isinstance(duration_hours, int) or isinstance(duration_hours, bool) or not 1 <= duration_hours <= 168:
        raise AuctionError("Auction duration must be between 1 and 168 hours.")
    await _settle_due(db, now)
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute("SELECT * FROM players WHERE user_id=?", (seller_id,))
        player = await cur.fetchone()
        if not player:
            raise AuctionError("Register before using the auction house.")
        if await _has_active_battle(db, seller_id):
            raise AuctionError("Finish your active battle before listing equipped gear.")
        cur = await db.execute("SELECT 1 FROM auction_listings WHERE seller_id=? AND status='active'", (seller_id,))
        if await cur.fetchone():
            raise AuctionError("You already have an active auction.")
        item_name, item_stat = player[slot], player["weapon_attack" if slot == "weapon" else "armor_defense"]
        if item_name == DEFAULTS[slot][0] and item_stat == 0:
            raise AuctionError("Your starter equipment cannot be auctioned.")
        column = slot
        stat_column = "weapon_attack" if slot == "weapon" else "armor_defense"
        await db.execute(f"UPDATE players SET {column}=?, {stat_column}=? WHERE user_id=?", (*DEFAULTS[slot], seller_id))
        cur = await db.execute("""INSERT INTO auction_listings
          (seller_id,slot,item_name,item_stat,start_price,ends_at,created_at)
          VALUES(?,?,?,?,?,?,?)""",
          (seller_id,slot,item_name,item_stat,start_price,now+duration_hours*3600,now))
        listing_id = cur.lastrowid
        await db.commit()
        return listing_id
    except Exception:
        await db.rollback()
        raise

async def place_bid(db, bidder_id, listing_id, amount, now=None):
    now = int(time.time()) if now is None else int(now)
    if not isinstance(bidder_id,int) or isinstance(bidder_id,bool) or bidder_id <= 0:
        raise AuctionError("Invalid bidder account.")
    if not isinstance(listing_id,int) or isinstance(listing_id,bool) or listing_id <= 0:
        raise AuctionError("Invalid auction ID.")
    if not isinstance(amount,int) or isinstance(amount,bool) or amount <= 0:
        raise AuctionError("Bid must be a positive whole number.")
    await _settle_due(db, now)
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute("SELECT * FROM auction_listings WHERE listing_id=? AND status='active'", (listing_id,))
        listing = await cur.fetchone()
        if not listing or listing["ends_at"] <= now:
            raise AuctionError("This auction is no longer active.")
        if bidder_id == listing["seller_id"]:
            raise AuctionError("You cannot bid on your own item.")
        minimum = max(listing["start_price"], listing["current_bid"] + max(1, listing["current_bid"] // 20))
        if amount < minimum:
            raise AuctionError(f"Minimum next bid is {minimum} coins.")
        cur = await db.execute("UPDATE players SET coins=coins-? WHERE user_id=? AND coins>=?", (amount,bidder_id,amount))
        if cur.rowcount != 1:
            raise AuctionError("Insufficient coins or player account not found.")
        if listing["highest_bidder"] is not None:
            await db.execute("UPDATE players SET coins=coins+? WHERE user_id=?", (listing["current_bid"],listing["highest_bidder"]))
        await db.execute("UPDATE auction_listings SET current_bid=?,highest_bidder=? WHERE listing_id=?", (amount,bidder_id,listing_id))
        await db.commit()
        return minimum, amount
    except Exception:
        await db.rollback()
        raise

async def cancel_listing(db, seller_id, listing_id, now=None):
    now = int(time.time()) if now is None else int(now)
    await _settle_due(db, now)
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute("SELECT * FROM auction_listings WHERE listing_id=? AND status='active'", (listing_id,))
        row = await cur.fetchone()
        if not row or row["seller_id"] != seller_id:
            raise AuctionError("Active auction not found for your account.")
        if row["highest_bidder"] is not None:
            raise AuctionError("An auction with bids cannot be cancelled.")
        column = row["slot"]
        stat_column = "weapon_attack" if column == "weapon" else "armor_defense"
        await db.execute(f"UPDATE players SET {column}=?,{stat_column}=? WHERE user_id=?", (row["item_name"],row["item_stat"],seller_id))
        await db.execute("UPDATE auction_listings SET status='cancelled' WHERE listing_id=?", (listing_id,))
        await db.commit()
    except Exception:
        await db.rollback()
        raise

async def list_active_auctions(db, now=None, limit=20):
    now = int(time.time()) if now is None else int(now)
    await _settle_due(db, now)
    cur = await db.execute("""SELECT listing_id,seller_id,slot,item_name,item_stat,start_price,current_bid,
      highest_bidder,ends_at FROM auction_listings WHERE status='active' AND ends_at>?
      ORDER BY ends_at ASC,listing_id ASC LIMIT ?""", (now,max(1,min(int(limit),50))))
    return await cur.fetchall()

async def get_auction(db, listing_id, now=None):
    rows = await list_active_auctions(db, now, 50)
    return next((row for row in rows if row["listing_id"] == listing_id), None)

async def list_stash(db, user_id):
    cur = await db.execute("SELECT stash_id,slot,item_name,item_stat,created_at FROM auction_stash WHERE user_id=? ORDER BY stash_id", (user_id,))
    return await cur.fetchall()

async def equip_stashed_item(db, user_id, stash_id):
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute("SELECT * FROM auction_stash WHERE stash_id=? AND user_id=?", (stash_id,user_id))
        item = await cur.fetchone()
        if not item:
            raise AuctionError("That stored item does not belong to your account.")
        if await _has_active_battle(db, user_id):
            raise AuctionError("Finish your active battle before changing equipment.")
        slot = item["slot"]
        stat_column = "weapon_attack" if slot == "weapon" else "armor_defense"
        cur = await db.execute(f"SELECT {slot},{stat_column} FROM players WHERE user_id=?", (user_id,))
        player = await cur.fetchone()
        if not player:
            raise AuctionError("Player account not found.")
        await db.execute("INSERT INTO auction_stash(user_id,slot,item_name,item_stat,source_listing_id,created_at) VALUES(?,?,?,?,?,?)",
          (user_id,slot,player[slot],player[stat_column],None,int(time.time())))
        await db.execute(f"UPDATE players SET {slot}=?,{stat_column}=? WHERE user_id=?", (item["item_name"],item["item_stat"],user_id))
        await db.execute("DELETE FROM auction_stash WHERE stash_id=?", (stash_id,))
        await db.commit()
        return item["item_name"],slot,item["item_stat"]
    except Exception:
        await db.rollback()
        raise
