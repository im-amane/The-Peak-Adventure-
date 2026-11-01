"""Abuse telemetry for suspicious game actions; never auto-bans players."""
import aiosqlite

EVENT_TYPES = {
    "invalid_battle_action",
    "invalid_monster_request",
    "invalid_social_action",
    "invalid_dungeon_action",
    "invalid_world_action",
    "invalid_reward_claim",
    "repeated_rate_limit",
}


class SecurityEventError(ValueError):
    pass


async def init_security_tables(db):
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
    await db.commit()


async def record_security_event(db, user_id, event_type, details="", severity=1):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise SecurityEventError("Invalid player account.")
    if event_type not in EVENT_TYPES:
        raise SecurityEventError("Unknown security event type.")
    if not isinstance(severity, int) or isinstance(severity, bool) or not 1 <= severity <= 5:
        raise SecurityEventError("Security severity must be between 1 and 5.")
    clean = " ".join(str(details or "").split())[:240]
    await db.execute(
        "INSERT INTO security_events(user_id,event_type,severity,details) VALUES(?,?,?,?)",
        (user_id, event_type, severity, clean),
    )
    await db.commit()


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
