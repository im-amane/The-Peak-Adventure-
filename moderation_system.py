"""Global player sanctions and ban-state lookup."""
import time
from functools import wraps


class ModerationError(ValueError):
    pass


def _valid_timestamp(value):
    return isinstance(value,int) and not isinstance(value,bool) and value>=0


async def _begin_atomic(db,savepoint):
    nested=db.in_transaction
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    else:
        await db.execute("BEGIN IMMEDIATE")
    return nested


async def _commit_atomic(db,nested,savepoint):
    if nested:
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.commit()


async def _rollback_atomic(db,nested,savepoint):
    if nested:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.rollback()


def _transactional(function):
    """Keep moderation changes atomic and preserve caller-owned transactions."""
    @wraps(function)
    async def wrapped(db,*args,**kwargs):
        savepoint="moderation_"+function.__name__
        nested=await _begin_atomic(db,savepoint)
        try:
            result=await function(db,*args,**kwargs)
            await _commit_atomic(db,nested,savepoint)
            return result
        except Exception:
            await _rollback_atomic(db,nested,savepoint)
            raise
    return wrapped


@_transactional
async def init_moderation_tables(db):
    statements=(
        """CREATE TABLE IF NOT EXISTS player_bans(
          user_id INTEGER PRIMARY KEY,
          actor_id BIGINT NOT NULL,
          reason TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_player_bans_active ON player_bans(active,user_id)",
    )
    for statement in statements:
        await db.execute(statement)


@_transactional
async def ban_player(db, actor_id, user_id, reason, now=None):
    for value,label in ((actor_id,"administrator"),(user_id,"player")):
        if not isinstance(value,int) or isinstance(value,bool) or value<=0:
            raise ModerationError(f"Invalid {label} ID.")
    if not isinstance(reason,str):
        raise ModerationError("Ban reason must be text.")
    clean=" ".join(reason.split())
    if not 5<=len(clean)<=300:
        raise ModerationError("Ban reason must be between 5 and 300 characters.")
    stamp=int(time.time()) if now is None else now
    if not _valid_timestamp(stamp):
        raise ModerationError("Invalid moderation timestamp.")
    cur=await db.execute("SELECT 1 FROM players WHERE user_id=?",(user_id,))
    if not await cur.fetchone():
        raise ModerationError("Player account not found.")
    cur=await db.execute("""INSERT INTO player_bans(user_id,actor_id,reason,active,created_at,updated_at)
      VALUES(?,?,?,1,?,?) ON CONFLICT(user_id) DO UPDATE SET actor_id=excluded.actor_id,
      reason=excluded.reason,active=1,updated_at=excluded.updated_at""",
      (user_id,actor_id,clean,stamp,stamp))
    if cur.rowcount != 1:
        raise ModerationError("Player ban could not be recorded.")
    return True


@_transactional
async def unban_player(db, actor_id, user_id, now=None):
    for value,label in ((actor_id,"administrator"),(user_id,"player")):
        if not isinstance(value,int) or isinstance(value,bool) or value<=0:
            raise ModerationError(f"Invalid {label} ID.")
    stamp=int(time.time()) if now is None else now
    if not _valid_timestamp(stamp):
        raise ModerationError("Invalid moderation timestamp.")
    cur=await db.execute(
        "UPDATE player_bans SET active=0,actor_id=?,updated_at=? WHERE user_id=? AND active=1",
        (actor_id,stamp,user_id),
    )
    if cur.rowcount!=1:
        raise ModerationError("No active ban exists for that player.")
    return True


async def get_active_ban(db,user_id):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        return None
    cur=await db.execute("SELECT reason,actor_id,created_at FROM player_bans WHERE user_id=? AND active=1",(user_id,))
    return await cur.fetchone()
