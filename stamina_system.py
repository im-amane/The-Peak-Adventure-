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


def _validate_now(now):
    if now is not None and (not isinstance(now,int) or isinstance(now,bool) or now<0):
        raise StaminaError("Invalid stamina timestamp.")
    return int(time.time() if now is None else now)


async def _begin_atomic(db, savepoint):
    nested=db.in_transaction
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    else:
        await db.execute("BEGIN IMMEDIATE")
    return nested


async def _commit_atomic(db,nested,savepoint,commit=True):
    if nested:
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    elif commit:
        await db.commit()


async def _rollback_atomic(db,nested,savepoint):
    if nested:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.rollback()


async def init_stamina_tables(db):
    """Initialize stamina storage without committing a caller-owned transaction."""
    nested=await _begin_atomic(db,"init_stamina_tables")
    try:
        await db.execute("""CREATE TABLE IF NOT EXISTS player_stamina(
          user_id INTEGER PRIMARY KEY,
          stamina INTEGER NOT NULL DEFAULT 100 CHECK(stamina BETWEEN 0 AND 100),
          updated_at INTEGER NOT NULL
        )""")
        await _commit_atomic(db,nested,"init_stamina_tables")
    except Exception:
        await _rollback_atomic(db,nested,"init_stamina_tables")
        raise


async def get_stamina(db, user_id, now=None, commit=True):
    _valid_user(user_id)
    now=_validate_now(now)
    nested=await _begin_atomic(db,"get_stamina")
    try:
        await db.execute(
            "INSERT INTO player_stamina(user_id,stamina,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO NOTHING",
            (user_id,MAX_STAMINA,now),
        )
        cur=await db.execute("SELECT stamina,updated_at FROM player_stamina WHERE user_id=?",(user_id,))
        row=await cur.fetchone()
        elapsed=max(0,now-row["updated_at"])
        gained=min(MAX_STAMINA-row["stamina"],elapsed//REGEN_SECONDS)
        stamina=row["stamina"]+gained
        updated_at=row["updated_at"]+gained*REGEN_SECONDS if gained else row["updated_at"]
        if stamina>=MAX_STAMINA:
            updated_at=now
        if gained or updated_at!=row["updated_at"]:
            await db.execute(
                "UPDATE player_stamina SET stamina=?,updated_at=? WHERE user_id=?",
                (stamina,updated_at,user_id),
            )
        await _commit_atomic(db,nested,"get_stamina",commit)
        elapsed_since_tick=max(0,now-updated_at)
        return {"stamina":stamina,"max_stamina":MAX_STAMINA,
                "next_regen_seconds":0 if stamina>=MAX_STAMINA else REGEN_SECONDS-(elapsed_since_tick%REGEN_SECONDS)}
    except Exception:
        await _rollback_atomic(db,nested,"get_stamina")
        raise


async def consume_stamina(db, user_id, amount, now=None, commit=True):
    _valid_user(user_id)
    if not isinstance(amount,int) or isinstance(amount,bool) or amount<=0 or amount>MAX_STAMINA:
        raise StaminaError("Invalid stamina cost.")
    now=_validate_now(now)
    nested=await _begin_atomic(db,"consume_stamina")
    try:
        state=await get_stamina(db,user_id,now)
        if state["stamina"]<amount:
            raise StaminaError(f"Not enough stamina. Need {amount}; you have {state['stamina']}.")
        cur=await db.execute(
            "UPDATE player_stamina SET stamina=stamina-? WHERE user_id=? AND stamina>=?",
            (amount,user_id,amount),
        )
        if cur.rowcount!=1:
            raise StaminaError("Stamina changed before exploring. Please try again.")
        state=await get_stamina(db,user_id,now)
        await _commit_atomic(db,nested,"consume_stamina",commit)
        return state
    except Exception:
        await _rollback_atomic(db,nested,"consume_stamina")
        raise


async def restore_stamina(db, user_id, amount, now=None, commit=True):
    _valid_user(user_id)
    if not isinstance(amount,int) or isinstance(amount,bool) or amount<=0 or amount>MAX_STAMINA:
        raise StaminaError("Invalid stamina restore amount.")
    now=_validate_now(now)
    nested=await _begin_atomic(db,"restore_stamina")
    try:
        await get_stamina(db,user_id,now)
        cur=await db.execute(
            "UPDATE player_stamina SET stamina=CASE WHEN stamina+? > ? THEN ? ELSE stamina+? END,updated_at=? WHERE user_id=?",
            (amount,MAX_STAMINA,MAX_STAMINA,amount,now,user_id),
        )
        if cur.rowcount!=1:
            raise StaminaError("Stamina could not be restored.")
        state=await get_stamina(db,user_id,now)
        await _commit_atomic(db,nested,"restore_stamina",commit)
        return state
    except Exception:
        await _rollback_atomic(db,nested,"restore_stamina")
        raise
