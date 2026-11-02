"""Abuse telemetry for suspicious game actions; never auto-bans players."""
import aiosqlite

MAX_SECURITY_EVENTS = 50_000
RETENTION_DAYS = 30
CLEANUP_INTERVAL = 250

EVENT_TYPES = {
    "invalid_battle_action",
    "invalid_monster_request",
    "invalid_social_action",
    "invalid_dungeon_action",
    "invalid_world_action",
    "invalid_story_action",
    "invalid_reward_claim",
    "invalid_premium_payment",
    "repeated_rate_limit",
}


class SecurityEventError(ValueError):
    pass


async def _begin_transaction(db, savepoint):
    nested = db.in_transaction
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    else:
        await db.execute("BEGIN IMMEDIATE")
    return nested


async def _finish_transaction(db, savepoint, nested):
    if nested:
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.commit()


async def _rollback_transaction(db, savepoint, nested):
    if nested:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.rollback()


async def init_security_tables(db):
    savepoint = "init_security_tables"
    nested = await _begin_transaction(db, savepoint)
    try:
        await db.execute("""CREATE TABLE IF NOT EXISTS security_events(
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          event_type TEXT NOT NULL,
          severity INTEGER NOT NULL DEFAULT 1 CHECK(severity BETWEEN 1 AND 5),
          details TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_security_user_time ON security_events(user_id,created_at DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_security_time ON security_events(created_at DESC)")
        await _finish_transaction(db, savepoint, nested)
    except Exception:
        await _rollback_transaction(db, savepoint, nested)
        raise


async def record_security_event(db, user_id, event_type, details="", severity=1):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise SecurityEventError("Invalid player account.")
    if not isinstance(event_type, str) or event_type not in EVENT_TYPES:
        raise SecurityEventError("Unknown security event type.")
    if not isinstance(severity, int) or isinstance(severity, bool) or not 1 <= severity <= 5:
        raise SecurityEventError("Security severity must be between 1 and 5.")
    clean = " ".join(str(details or "").split())[:240]
    savepoint = "record_security_event"
    nested = await _begin_transaction(db, savepoint)
    try:
        cur = await db.execute(
            "INSERT INTO security_events(user_id,event_type,severity,details) VALUES(?,?,?,?)",
            (user_id, event_type, severity, clean),
        )
        if int(cur.lastrowid) % CLEANUP_INTERVAL == 0:
            await db.execute(
                "DELETE FROM security_events WHERE created_at < datetime('now', ?)",
                (f"-{RETENTION_DAYS} days",),
            )
            await db.execute(
                """DELETE FROM security_events
                   WHERE event_id <= (
                     SELECT event_id FROM security_events
                     ORDER BY event_id DESC LIMIT 1 OFFSET ?
                   )""",
                (MAX_SECURITY_EVENTS,),
            )
        await _finish_transaction(db, savepoint, nested)
    except Exception:
        await _rollback_transaction(db, savepoint, nested)
        raise


async def get_suspicious_players(db, window_minutes=1440, limit=20):
    if not isinstance(window_minutes, int) or isinstance(window_minutes, bool) or not 1 <= window_minutes <= 10080:
        raise SecurityEventError("Security window must be between 1 and 10080 minutes.")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise SecurityEventError("Security result limit must be between 1 and 50.")
    cur = await db.execute(
        """SELECT user_id,COUNT(*) AS event_count,MAX(severity) AS max_severity,
                  SUM(severity) AS risk_score,MAX(created_at) AS last_seen
           FROM security_events
           WHERE created_at >= datetime('now', ?)
           GROUP BY user_id
           ORDER BY risk_score DESC,event_count DESC,last_seen DESC
           LIMIT ?""",
        (f"-{window_minutes} minutes", limit),
    )
    return await cur.fetchall()


async def get_security_events(db, user_id, limit=20):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise SecurityEventError("Invalid player account.")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise SecurityEventError("Security event limit must be between 1 and 100.")
    cur = await db.execute(
        """SELECT event_id,event_type,severity,details,created_at
           FROM security_events WHERE user_id=? ORDER BY event_id DESC LIMIT ?""",
        (user_id, limit),
    )
    return await cur.fetchall()
