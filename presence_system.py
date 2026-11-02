"""Privacy-conscious recent activity presence."""


def _is_postgres(db):
    return getattr(db, "dialect", "sqlite") == "postgres"


async def _begin_atomic(db, savepoint: str) -> bool:
    nested = db.in_transaction
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    return nested


async def _commit_atomic(db, nested: bool, savepoint: str):
    if nested:
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.commit()


async def _rollback_atomic(db, nested: bool, savepoint: str):
    if nested:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.rollback()


async def init_presence_tables(db):
    """Initialize presence storage without committing a caller-owned transaction."""
    nested = await _begin_atomic(db, "init_presence_tables")
    try:
        if _is_postgres(db):
            await db.execute("""CREATE TABLE IF NOT EXISTS player_presence(
              user_id BIGINT PRIMARY KEY,last_seen TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
        else:
            await db.execute("""CREATE TABLE IF NOT EXISTS player_presence(
              user_id BIGINT PRIMARY KEY,last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_player_presence_seen ON player_presence(last_seen)")
        await _commit_atomic(db, nested, "init_presence_tables")
    except Exception:
        await _rollback_atomic(db, nested, "init_presence_tables")
        raise


async def touch_presence(db, user_id: int):
    """Update last-seen state while preserving any transaction owned by the caller."""
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        return
    nested = await _begin_atomic(db, "touch_presence")
    try:
        await db.execute("""INSERT INTO player_presence(user_id,last_seen) VALUES(?,CURRENT_TIMESTAMP)
          ON CONFLICT(user_id) DO UPDATE SET last_seen=CURRENT_TIMESTAMP""", (user_id,))
        await _commit_atomic(db, nested, "touch_presence")
    except Exception:
        await _rollback_atomic(db, nested, "touch_presence")
        raise


async def count_online_players(db, window_minutes: int = 5):
    if not isinstance(window_minutes, int) or isinstance(window_minutes, bool) or not 1 <= window_minutes <= 60:
        raise ValueError("Presence window must be between 1 and 60 minutes.")
    cutoff = (
        "CURRENT_TIMESTAMP - (? * INTERVAL '1 minute')"
        if _is_postgres(db)
        else "datetime('now', ?)"
    )
    window = (window_minutes,) if _is_postgres(db) else (f"-{window_minutes} minutes",)
    cur = await db.execute(
        f"SELECT COUNT(*) AS total FROM player_presence WHERE last_seen >= {cutoff}",
        window,
    )
    return (await cur.fetchone())["total"]


async def list_online_friends(db, user_id: int, window_minutes: int = 5):
    if not isinstance(window_minutes, int) or isinstance(window_minutes, bool) or not 1 <= window_minutes <= 60:
        raise ValueError("Presence window must be between 1 and 60 minutes.")
    cutoff = (
        "CURRENT_TIMESTAMP - (? * INTERVAL '1 minute')"
        if _is_postgres(db)
        else "datetime('now', ?)"
    )
    window = (window_minutes,) if _is_postgres(db) else (f"-{window_minutes} minutes",)
    cur = await db.execute(f"""SELECT p.user_id,p.username,p.level,pr.last_seen FROM friend_requests f
      JOIN players p ON p.user_id=CASE WHEN f.user_low=? THEN f.user_high ELSE f.user_low END
      JOIN player_presence pr ON pr.user_id=p.user_id
      LEFT JOIN player_settings s ON s.user_id=p.user_id
      WHERE f.status='accepted' AND (f.user_low=? OR f.user_high=?)
      AND pr.last_seen >= {cutoff}
      AND COALESCE(s.profile_visibility,'public')!='private'
      ORDER BY pr.last_seen DESC""", (user_id, user_id, user_id, *window))
    return await cur.fetchall()
