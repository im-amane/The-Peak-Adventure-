"""Telegram Stars premium-currency ledger with idempotent payment crediting."""
import os
import aiosqlite


class PremiumError(ValueError):
    pass


PREMIUM_SHOP_ITEMS = {
    "stamina_crystal": {"cost": 25, "title": "Stamina Crystal", "description": "Restore up to 50 stamina."},
    "potion_bundle": {"cost": 40, "title": "Potion Bundle", "description": "Receive 5 healing potions."},
    "xp_charm": {"cost": 60, "title": "XP Charm", "description": "Double XP from your next 3 victories."},
}


def get_premium_packages():
    def price(name, default):
        raw = os.getenv(f"PREMIUM_{name.upper()}_STARS", str(default))
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise PremiumError(f"Invalid Stars price for {name}.")
        if not 1 <= value <= 100_000:
            raise PremiumError(f"Stars price for {name} must be between 1 and 100000.")
        return value

    return {
        "spark": {"gems": 50, "stars": price("spark", 25), "title": "Spark Pack"},
        "crest": {"gems": 120, "stars": price("crest", 50), "title": "Crest Pack"},
        "crown": {"gems": 260, "stars": price("crown", 100), "title": "Crown Pack"},
    }


def make_invoice_payload(package_id, user_id):
    if package_id not in get_premium_packages():
        raise PremiumError("Unknown premium package.")
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise PremiumError("Invalid player account.")
    return f"peak-gems:{package_id}:{user_id}"


def parse_invoice_payload(payload):
    if not isinstance(payload, str) or len(payload) > 100:
        raise PremiumError("Invalid premium payment payload.")
    parts = payload.split(":")
    if len(parts) != 3 or parts[0] != "peak-gems" or parts[1] not in get_premium_packages():
        raise PremiumError("Unknown premium payment package.")
    if not parts[2].isdigit() or int(parts[2]) <= 0:
        raise PremiumError("Invalid premium payment owner.")
    return parts[1], int(parts[2])


async def init_premium_tables(db):
    await db.executescript("""CREATE TABLE IF NOT EXISTS premium_wallets(
      user_id INTEGER PRIMARY KEY,balance INTEGER NOT NULL DEFAULT 0 CHECK(balance>=0),
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS premium_transactions(
      transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
      telegram_charge_id TEXT NOT NULL UNIQUE,
      provider_charge_id TEXT NOT NULL DEFAULT '',
      user_id INTEGER NOT NULL,
      package_id TEXT NOT NULL,
      stars INTEGER NOT NULL CHECK(stars>0),
      gems INTEGER NOT NULL CHECK(gems>0),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_premium_transactions_user
      ON premium_transactions(user_id,transaction_id DESC);
    CREATE TABLE IF NOT EXISTS player_xp_boosts(
      user_id INTEGER PRIMARY KEY,remaining_wins INTEGER NOT NULL DEFAULT 0 CHECK(remaining_wins>=0)
    );
    CREATE TABLE IF NOT EXISTS premium_shop_purchases(
      purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,
      item_id TEXT NOT NULL,gems_spent INTEGER NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    await db.commit()


async def get_premium_balance(db, user_id):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise PremiumError("Invalid player account.")
    cur = await db.execute("SELECT balance FROM premium_wallets WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return row["balance"] if row else 0


async def credit_premium_purchase(db, user_id, package_id, stars, telegram_charge_id, provider_charge_id=""):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise PremiumError("Invalid player account.")
    packages = get_premium_packages()
    package = packages.get(package_id) if isinstance(package_id, str) else None
    if not package:
        raise PremiumError("Unknown premium package.")
    if not isinstance(stars, int) or isinstance(stars, bool) or stars != package["stars"]:
        raise PremiumError("The paid Stars amount does not match this package.")
    if not isinstance(telegram_charge_id, str) or not telegram_charge_id.strip() or len(telegram_charge_id) > 255:
        raise PremiumError("Invalid Telegram payment charge ID.")
    provider_charge_id = str(provider_charge_id or "")[:255]
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT transaction_id FROM premium_transactions WHERE telegram_charge_id=?",
            (telegram_charge_id,),
        )
        if await cur.fetchone():
            await db.commit()
            return {"credited": False, "balance": await get_premium_balance(db, user_id), "gems": 0}
        await db.execute(
            "INSERT INTO premium_wallets(user_id,balance) VALUES(?,0) ON CONFLICT(user_id) DO NOTHING",
            (user_id,),
        )
        await db.execute(
            """INSERT INTO premium_transactions(
                 telegram_charge_id,provider_charge_id,user_id,package_id,stars,gems
               ) VALUES(?,?,?,?,?,?)""",
            (telegram_charge_id, provider_charge_id, user_id, package_id, stars, package["gems"]),
        )
        await db.execute(
            "UPDATE premium_wallets SET balance=balance+?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (package["gems"], user_id),
        )
        await db.commit()
        return {"credited": True, "balance": await get_premium_balance(db, user_id), "gems": package["gems"]}
    except Exception:
        await db.rollback()
        raise


async def buy_premium_item(db, user_id, item_id):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise PremiumError("Invalid player account.")
    if not isinstance(item_id, str) or item_id not in PREMIUM_SHOP_ITEMS:
        raise PremiumError("Unknown premium shop item.")
    item = PREMIUM_SHOP_ITEMS[item_id]
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute("SELECT 1 FROM players WHERE user_id=?", (user_id,))
        if not await cur.fetchone():
            raise PremiumError("Player account not found.")
        cur = await db.execute("SELECT balance FROM premium_wallets WHERE user_id=?", (user_id,))
        wallet = await cur.fetchone()
        balance = wallet["balance"] if wallet else 0
        if balance < item["cost"]:
            raise PremiumError(f"You need {item['cost']} gems; your balance is {balance}.")
        if item_id == "stamina_crystal":
            cur = await db.execute("SELECT stamina,max_stamina FROM player_stamina WHERE user_id=?", (user_id,))
            stamina = await cur.fetchone()
            if not stamina:
                raise PremiumError("Stamina data is not ready for this player.")
            restored = min(50, stamina["max_stamina"] - stamina["stamina"])
            if restored <= 0:
                raise PremiumError("Your stamina is already full.")
            await db.execute("UPDATE player_stamina SET stamina=stamina+? WHERE user_id=?", (restored, user_id))
        elif item_id == "potion_bundle":
            await db.execute("UPDATE players SET potions=potions+5 WHERE user_id=?", (user_id,))
        elif item_id == "xp_charm":
            await db.execute(
                """INSERT INTO player_xp_boosts(user_id,remaining_wins) VALUES(?,3)
                   ON CONFLICT(user_id) DO UPDATE SET remaining_wins=remaining_wins+3""",
                (user_id,),
            )
        await db.execute("UPDATE premium_wallets SET balance=balance-? WHERE user_id=?", (item["cost"], user_id))
        await db.execute(
            "INSERT INTO premium_shop_purchases(user_id,item_id,gems_spent) VALUES(?,?,?)",
            (user_id, item_id, item["cost"]),
        )
        await db.commit()
        return {"item_id": item_id, "title": item["title"], "cost": item["cost"],
                "balance": balance - item["cost"]}
    except Exception:
        await db.rollback()
        raise


async def consume_xp_boost(db, user_id):
    cur = await db.execute("SELECT remaining_wins FROM player_xp_boosts WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if not row or row["remaining_wins"] <= 0:
        return False
    await db.execute(
        "UPDATE player_xp_boosts SET remaining_wins=remaining_wins-1 WHERE user_id=? AND remaining_wins>0",
        (user_id,),
    )
    return True
