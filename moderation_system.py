"""Global player sanctions and ban-state lookup."""
import time


class ModerationError(ValueError):
    pass


async def init_moderation_tables(db):
    await db.execute("""CREATE TABLE IF NOT EXISTS player_bans(
      user_id INTEGER PRIMARY KEY,
      actor_id INTEGER NOT NULL,
      reason TEXT NOT NULL,
      active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    )""")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_player_bans_active ON player_bans(active,user_id)")
    await db.commit()


async def ban_player(db, actor_id, user_id, reason, now=None):
    for value,label in ((actor_id,"administrator"),(user_id,"player")):
        if not isinstance(value,int) or isinstance(value,bool) or value<=0:
            raise ModerationError(f"Invalid {label} ID.")
    clean=" ".join(str(reason or "").split())
    if not 5<=len(clean)<=300:
        raise ModerationError("Ban reason must be between 5 and 300 characters.")
    cur=await db.execute("SELECT 1 FROM players WHERE user_id=?",(user_id,))
    if not await cur.fetchone():
        raise ModerationError("Player account not found.")
    stamp=int(time.time() if now is None else now)
    await db.execute("""INSERT INTO player_bans(user_id,actor_id,reason,active,created_at,updated_at)
      VALUES(?,?,?,1,?,?) ON CONFLICT(user_id) DO UPDATE SET actor_id=excluded.actor_id,
      reason=excluded.reason,active=1,updated_at=excluded.updated_at""",
      (user_id,actor_id,clean,stamp,stamp))
    await db.commit()
    return True


async def unban_player(db, actor_id, user_id, now=None):
    for value,label in ((actor_id,"administrator"),(user_id,"player")):
        if not isinstance(value,int) or isinstance(value,bool) or value<=0:
            raise ModerationError(f"Invalid {label} ID.")
    cur=await db.execute(
        "UPDATE player_bans SET active=0,actor_id=?,updated_at=? WHERE user_id=? AND active=1",
        (actor_id,int(time.time() if now is None else now),user_id),
    )
    if cur.rowcount!=1:
        raise ModerationError("No active ban exists for that player.")
    await db.commit()
    return True


async def get_active_ban(db,user_id):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        return None
    cur=await db.execute("SELECT reason,actor_id,created_at FROM player_bans WHERE user_id=? AND active=1",(user_id,))
    return await cur.fetchone()
