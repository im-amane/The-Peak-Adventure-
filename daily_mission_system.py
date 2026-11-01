"""Daily rotating objectives with persistent progress and one-time rewards."""
from datetime import datetime, timezone
import time

DAILY_MISSIONS = (
    {"id": "daily_hunter", "title": "Wilds Patrol", "kind": "wins", "target": 3,
     "coins": 75, "potions": 1, "description": "Win 3 monster battles today."},
    {"id": "daily_artisan", "title": "Field Artisan", "kind": "crafts", "target": 1,
     "coins": 100, "potions": 1, "description": "Craft 1 piece of equipment today."},
    {"id": "daily_scout", "title": "Landmark Scout", "kind": "landmarks", "target": 1,
     "coins": 80, "potions": 1, "description": "Discover 1 world landmark today."},
)
MISSION_BY_ID = {mission["id"]: mission for mission in DAILY_MISSIONS}


class DailyMissionError(ValueError):
    pass


def current_day_key(now=None):
    stamp = datetime.fromtimestamp(time.time() if now is None else now, timezone.utc)
    return stamp.strftime("%Y-%m-%d")


async def init_daily_mission_tables(db):
    await db.execute("""CREATE TABLE IF NOT EXISTS player_daily_missions(
      user_id INTEGER NOT NULL,day_key TEXT NOT NULL,mission_id TEXT NOT NULL,
      progress INTEGER NOT NULL DEFAULT 0 CHECK(progress>=0),
      claimed INTEGER NOT NULL DEFAULT 0 CHECK(claimed IN (0,1)),
      PRIMARY KEY(user_id,day_key,mission_id)
    )""")
    await db.commit()


async def _ensure_day(db, user_id, day_key):
    await db.executemany(
        "INSERT OR IGNORE INTO player_daily_missions(user_id,day_key,mission_id) VALUES(?,?,?)",
        [(user_id, day_key, mission["id"]) for mission in DAILY_MISSIONS],
    )


async def record_daily_progress(db, user_id, kind, amount=1, now=None):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise DailyMissionError("Invalid player account.")
    if kind not in {"wins", "crafts", "landmarks"}:
        raise DailyMissionError("Unknown daily mission progress type.")
    if not isinstance(amount, int) or isinstance(amount, bool) or not 1 <= amount <= 100:
        raise DailyMissionError("Invalid daily progress amount.")
    day_key = current_day_key(now)
    await _ensure_day(db, user_id, day_key)
    for mission in DAILY_MISSIONS:
        if mission["kind"] == kind:
            await db.execute(
                "UPDATE player_daily_missions SET progress=MIN(?,progress+?) WHERE user_id=? AND day_key=? AND mission_id=?",
                (mission["target"], amount, user_id, day_key, mission["id"]),
            )
    await db.commit()


async def get_daily_missions(db, user_id, now=None):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise DailyMissionError("Invalid player account.")
    day_key = current_day_key(now)
    await _ensure_day(db, user_id, day_key)
    cur = await db.execute(
        "SELECT mission_id,progress,claimed FROM player_daily_missions WHERE user_id=? AND day_key=?",
        (user_id, day_key),
    )
    rows = {row["mission_id"]: row for row in await cur.fetchall()}
    await db.commit()
    result = []
    for mission in DAILY_MISSIONS:
        row = rows[mission["id"]]
        result.append({
            **mission,
            "progress": row["progress"],
            "completed": row["progress"] >= mission["target"],
            "claimed": bool(row["claimed"]),
        })
    return result


async def claim_daily_mission(db, user_id, mission_id, now=None):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise DailyMissionError("Invalid player account.")
    if not isinstance(mission_id, str) or mission_id not in MISSION_BY_ID:
        raise DailyMissionError("Unknown daily mission.")
    day_key = current_day_key(now)
    mission = MISSION_BY_ID[mission_id]
    try:
        await db.execute("BEGIN IMMEDIATE")
        await _ensure_day(db, user_id, day_key)
        cur = await db.execute(
            "SELECT progress,claimed FROM player_daily_missions WHERE user_id=? AND day_key=? AND mission_id=?",
            (user_id, day_key, mission_id),
        )
        row = await cur.fetchone()
        if row["progress"] < mission["target"]:
            raise DailyMissionError("Complete this daily mission before claiming its reward.")
        if row["claimed"]:
            raise DailyMissionError("This daily mission reward has already been claimed.")
        cur = await db.execute("SELECT 1 FROM players WHERE user_id=?", (user_id,))
        if not await cur.fetchone():
            raise DailyMissionError("Player account not found.")
        await db.execute(
            "UPDATE player_daily_missions SET claimed=1 WHERE user_id=? AND day_key=? AND mission_id=? AND claimed=0",
            (user_id, day_key, mission_id),
        )
        await db.execute(
            "UPDATE players SET coins=coins+?,potions=potions+? WHERE user_id=?",
            (mission["coins"], mission["potions"], user_id),
        )
        await db.commit()
        return mission
    except Exception:
        await db.rollback()
        raise
