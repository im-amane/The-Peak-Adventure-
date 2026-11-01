"""Persistent stamina with passive regeneration for The Peak Adventure."""
import time

MAX_STAMINA = 100
EXPLORE_COST = 10
REGEN_SECONDS = 300


class StaminaError(ValueError):
    pass


def _valid_user(user_id):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise StaminaError("Invalid player account.")


async def init_stamina_tables(db):
    await db.execute("""CREATE TABLE IF NOT EXISTS player_stamina(
      user_id INTEGER PRIMARY KEY,
      stamina INTEGER NOT NULL DEFAULT 100 CHECK(stamina BETWEEN 0 AND 100),
      updated_at INTEGER NOT NULL
    )""")
    await db.commit()


async def get_stamina(db, user_id, now=None):
    _valid_user(user_id)
    now = int(time.time() if now is None else now)
    await db.execute(
        "INSERT OR IGNORE INTO player_stamina(user_id,stamina,updated_at) VALUES(?,?,?)",
        (user_id, MAX_STAMINA, now),
    )
    cur = await db.execute("SELECT stamina,updated_at FROM player_stamina WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    elapsed = max(0, now - row["updated_at"])
    gained = min(MAX_STAMINA - row["stamina"], elapsed // REGEN_SECONDS)
    stamina = row["stamina"] + gained
    updated_at = row["updated_at"] + gained * REGEN_SECONDS if gained else row["updated_at"]
    if gained:
        await db.execute(
            "UPDATE player_stamina SET stamina=?,updated_at=? WHERE user_id=?",
            (stamina, updated_at, user_id),
        )
    await db.commit()
    return {"stamina": stamina, "max_stamina": MAX_STAMINA,
            "next_regen_seconds": 0 if stamina >= MAX_STAMINA else REGEN_SECONDS - ((now - updated_at) % REGEN_SECONDS)}


async def consume_stamina(db, user_id, amount, now=None):
    _valid_user(user_id)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0 or amount > MAX_STAMINA:
        raise StaminaError("Invalid stamina cost.")
    state = await get_stamina(db, user_id, now)
    if state["stamina"] < amount:
        raise StaminaError(f"Not enough stamina. Need {amount}; you have {state['stamina']}.")
    await db.execute("UPDATE player_stamina SET stamina=stamina-? WHERE user_id=?", (amount, user_id))
    await db.commit()
    return await get_stamina(db, user_id, now)


async def restore_stamina(db, user_id, amount, now=None):
    _valid_user(user_id)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0 or amount > MAX_STAMINA:
        raise StaminaError("Invalid stamina restore amount.")
    await get_stamina(db, user_id, now)
    await db.execute(
        "UPDATE player_stamina SET stamina=MIN(?,stamina+?),updated_at=? WHERE user_id=?",
        (MAX_STAMINA, amount, int(time.time() if now is None else now), user_id),
    )
    await db.commit()
    return await get_stamina(db, user_id, now)
