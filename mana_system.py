"""Persistent mana resource for class skills."""
import time

MAX_MANA = 100
SKILL_MANA_COST = 30
TURN_MANA_REGEN = 5
REGEN_SECONDS = 60


class ManaError(ValueError):
    pass


def _validate_user(user_id):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        raise ManaError("Invalid player account.")


async def init_mana_tables(db):
    await db.execute("""CREATE TABLE IF NOT EXISTS player_mana(
      user_id INTEGER PRIMARY KEY,mana INTEGER NOT NULL DEFAULT 100 CHECK(mana BETWEEN 0 AND 100),
      updated_at INTEGER NOT NULL
    )""")
    await db.commit()


async def get_mana(db,user_id,now=None):
    _validate_user(user_id)
    now=int(time.time() if now is None else now)
    await db.execute("INSERT OR IGNORE INTO player_mana(user_id,mana,updated_at) VALUES(?,?,?)",(user_id,MAX_MANA,now))
    cur=await db.execute("SELECT mana,updated_at FROM player_mana WHERE user_id=?",(user_id,))
    row=await cur.fetchone()
    elapsed=max(0,now-row["updated_at"])
    gained=min(MAX_MANA-row["mana"],elapsed//REGEN_SECONDS)
    mana=row["mana"]+gained
    updated=row["updated_at"]+gained*REGEN_SECONDS if gained else row["updated_at"]
    if mana>=MAX_MANA:
        updated=now
    if gained or updated!=row["updated_at"]:
        await db.execute("UPDATE player_mana SET mana=?,updated_at=? WHERE user_id=?",(mana,updated,user_id))
    await db.commit()
    elapsed_since=max(0,now-updated)
    return {"mana":mana,"max_mana":MAX_MANA,
            "next_regen_seconds":0 if mana>=MAX_MANA else REGEN_SECONDS-(elapsed_since%REGEN_SECONDS)}


async def consume_mana(db,user_id,amount=SKILL_MANA_COST,now=None):
    _validate_user(user_id)
    if not isinstance(amount,int) or isinstance(amount,bool) or not 1<=amount<=MAX_MANA:
        raise ManaError("Invalid mana cost.")
    state=await get_mana(db,user_id,now)
    if state["mana"]<amount:
        raise ManaError(f"Not enough mana. Need {amount}; you have {state['mana']}.")
    await db.execute("UPDATE player_mana SET mana=mana-? WHERE user_id=?",(amount,user_id))
    await db.commit()
    return await get_mana(db,user_id,now)


async def restore_mana(db,user_id,amount=TURN_MANA_REGEN,now=None):
    _validate_user(user_id)
    if not isinstance(amount,int) or isinstance(amount,bool) or not 1<=amount<=MAX_MANA:
        raise ManaError("Invalid mana restore amount.")
    await get_mana(db,user_id,now)
    await db.execute("UPDATE player_mana SET mana=MIN(?,mana+?),updated_at=? WHERE user_id=?",
      (MAX_MANA,amount,int(time.time() if now is None else now),user_id))
    await db.commit()
    return await get_mana(db,user_id,now)
