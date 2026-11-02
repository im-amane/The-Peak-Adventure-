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


def _validate_now(now):
    if now is not None and (not isinstance(now, int) or isinstance(now, bool) or now < 0):
        raise ManaError("Invalid mana timestamp.")
    return int(time.time() if now is None else now)


async def _begin_atomic(db, savepoint):
    nested = db.in_transaction
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    else:
        await db.execute("BEGIN IMMEDIATE")
    return nested


async def _commit_atomic(db, nested, savepoint, commit=True):
    if nested:
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    elif commit:
        await db.commit()


async def _rollback_atomic(db, nested, savepoint):
    if nested:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.rollback()


async def init_mana_tables(db):
    """Initialize mana storage without committing a caller-owned transaction."""
    nested = await _begin_atomic(db, "init_mana_tables")
    try:
        await db.execute("""CREATE TABLE IF NOT EXISTS player_mana(
          user_id INTEGER PRIMARY KEY,mana INTEGER NOT NULL DEFAULT 100 CHECK(mana BETWEEN 0 AND 100),
          updated_at INTEGER NOT NULL
        )""")
        await _commit_atomic(db, nested, "init_mana_tables")
    except Exception:
        await _rollback_atomic(db, nested, "init_mana_tables")
        raise


async def get_mana(db,user_id,now=None,commit=True):
    _validate_user(user_id)
    now = _validate_now(now)
    nested = await _begin_atomic(db, "get_mana")
    try:
        await db.execute(
            "INSERT OR IGNORE INTO player_mana(user_id,mana,updated_at) VALUES(?,?,?)",
            (user_id,MAX_MANA,now),
        )
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
        await _commit_atomic(db, nested, "get_mana", commit)
        elapsed_since=max(0,now-updated)
        return {"mana":mana,"max_mana":MAX_MANA,
                "next_regen_seconds":0 if mana>=MAX_MANA else REGEN_SECONDS-(elapsed_since%REGEN_SECONDS)}
    except Exception:
        await _rollback_atomic(db, nested, "get_mana")
        raise


async def consume_mana(db,user_id,amount=SKILL_MANA_COST,now=None,commit=True):
    _validate_user(user_id)
    if not isinstance(amount,int) or isinstance(amount,bool) or not 1<=amount<=MAX_MANA:
        raise ManaError("Invalid mana cost.")
    now = _validate_now(now)
    nested = await _begin_atomic(db, "consume_mana")
    try:
        state=await get_mana(db,user_id,now)
        if state["mana"]<amount:
            raise ManaError(f"Not enough mana. Need {amount}; you have {state['mana']}.")
        cur=await db.execute(
            "UPDATE player_mana SET mana=mana-? WHERE user_id=? AND mana>=?",
            (amount,user_id,amount),
        )
        if cur.rowcount != 1:
            raise ManaError("Mana changed before the skill could be used. Try again.")
        state=await get_mana(db,user_id,now)
        await _commit_atomic(db, nested, "consume_mana", commit)
        return state
    except Exception:
        await _rollback_atomic(db, nested, "consume_mana")
        raise


async def restore_mana(db,user_id,amount=TURN_MANA_REGEN,now=None,commit=True):
    _validate_user(user_id)
    if not isinstance(amount,int) or isinstance(amount,bool) or not 1<=amount<=MAX_MANA:
        raise ManaError("Invalid mana restore amount.")
    now = _validate_now(now)
    nested = await _begin_atomic(db, "restore_mana")
    try:
        await get_mana(db,user_id,now)
        cur=await db.execute(
            "UPDATE player_mana SET mana=MIN(?,mana+?),updated_at=? WHERE user_id=?",
            (MAX_MANA,amount,now,user_id),
        )
        if cur.rowcount != 1:
            raise ManaError("Mana could not be restored.")
        state=await get_mana(db,user_id,now)
        await _commit_atomic(db, nested, "restore_mana", commit)
        return state
    except Exception:
        await _rollback_atomic(db, nested, "restore_mana")
        raise
