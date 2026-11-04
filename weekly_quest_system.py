"""Weekly rotating objectives with persistent progress and one-time rewards."""
from datetime import datetime, timezone, timedelta
import time

WEEKLY_QUESTS = (
    {"id":"weekly_hunter","title":"Relentless Hunter","kind":"wins","target":15,"coins":300,"potions":2,"description":"Win 15 monster battles this week."},
    {"id":"weekly_bane","title":"Seal Breaker","kind":"bosses","target":2,"coins":500,"potions":3,"description":"Defeat 2 boss monsters this week."},
    {"id":"weekly_artisan","title":"Peak Artisan","kind":"crafts","target":3,"coins":350,"potions":2,"description":"Craft 3 pieces of equipment this week."},
    {"id":"weekly_explorer","title":"World Witness","kind":"landmarks","target":2,"coins":250,"potions":2,"description":"Discover 2 world landmarks this week."},
)
QUEST_BY_ID = {quest["id"]: quest for quest in WEEKLY_QUESTS}


class WeeklyQuestError(ValueError):
    pass


async def _begin_transaction(db, savepoint):
    nested = db.in_transaction
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    else:
        await db.execute("BEGIN IMMEDIATE")
    return nested


async def _commit_transaction(db, nested, savepoint):
    if nested:
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.commit()


async def _rollback_transaction(db, nested, savepoint):
    if nested:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.rollback()


def current_week_key(now=None):
    stamp = datetime.fromtimestamp(time.time() if now is None else now, timezone.utc)
    iso = stamp.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


async def init_weekly_tables(db):
    savepoint = "init_weekly_tables"
    nested = await _begin_transaction(db, savepoint)
    try:
        await db.execute("""CREATE TABLE IF NOT EXISTS player_weekly_quests(
      user_id BIGINT NOT NULL,week_key TEXT NOT NULL,quest_id TEXT NOT NULL,
      progress INTEGER NOT NULL DEFAULT 0 CHECK(progress>=0),
      claimed INTEGER NOT NULL DEFAULT 0 CHECK(claimed IN (0,1)),
      PRIMARY KEY(user_id,week_key,quest_id)
    )""")
        await _commit_transaction(db, nested, savepoint)
    except Exception:
        await _rollback_transaction(db, nested, savepoint)
        raise


async def _require_player(db, user_id):
    cur = await db.execute("SELECT 1 FROM players WHERE user_id=?", (user_id,))
    if await cur.fetchone() is None:
        raise WeeklyQuestError("Player account not found.")


async def _ensure_week(db, user_id, week_key):
    await db.executemany(
        "INSERT INTO player_weekly_quests(user_id,week_key,quest_id) VALUES(?,?,?) ON CONFLICT(user_id,week_key,quest_id) DO NOTHING",
        [(user_id, week_key, quest["id"]) for quest in WEEKLY_QUESTS],
    )


async def record_weekly_progress(db, user_id, kind, amount=1, now=None):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise WeeklyQuestError("Invalid player account.")
    if kind not in {"wins", "bosses", "crafts", "landmarks"}:
        raise WeeklyQuestError("Unknown weekly progress type.")
    if not isinstance(amount, int) or isinstance(amount, bool) or not 1 <= amount <= 100:
        raise WeeklyQuestError("Invalid weekly progress amount.")
    week_key = current_week_key(now)
    savepoint = "weekly_quest_progress"
    nested = await _begin_transaction(db, savepoint)
    try:
        await _require_player(db, user_id)
        await _ensure_week(db, user_id, week_key)
        for quest in WEEKLY_QUESTS:
            if quest["kind"] == kind:
                await db.execute(
                    "UPDATE player_weekly_quests SET progress=CASE WHEN progress+? > ? THEN ? ELSE progress+? END WHERE user_id=? AND week_key=? AND quest_id=?",
                    (amount, quest["target"], quest["target"], amount, user_id, week_key, quest["id"]),
                )
        await _commit_transaction(db, nested, savepoint)
    except Exception:
        await _rollback_transaction(db, nested, savepoint)
        raise

async def get_weekly_quests(db, user_id, now=None):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise WeeklyQuestError("Invalid player account.")
    stamp = int(time.time() if now is None else now)
    week_key = current_week_key(stamp)
    savepoint = "weekly_quest_read"
    nested = await _begin_transaction(db, savepoint)
    try:
        await _require_player(db, user_id)
        await _ensure_week(db, user_id, week_key)
        cur = await db.execute(
            "SELECT quest_id,progress,claimed FROM player_weekly_quests WHERE user_id=? AND week_key=?",
            (user_id, week_key),
        )
        rows = {row["quest_id"]: row for row in await cur.fetchall()}
        stamp_date = datetime.fromtimestamp(stamp, timezone.utc).date()
        next_monday = (stamp_date + timedelta(days=7 - stamp_date.weekday())).isoformat()
        reset_at = int(datetime.fromisoformat(next_monday).replace(tzinfo=timezone.utc).timestamp())
        result = [
            {
                **quest,
                "progress": rows[quest["id"]]["progress"],
                "completed": rows[quest["id"]]["progress"] >= quest["target"],
                "claimed": bool(rows[quest["id"]]["claimed"]),
                "week_key": week_key,
                "reset_at": reset_at,
            }
            for quest in WEEKLY_QUESTS
        ]
        await _commit_transaction(db, nested, savepoint)
        return result
    except Exception:
        await _rollback_transaction(db, nested, savepoint)
        raise

async def claim_weekly_reward(db, user_id, quest_id, now=None):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise WeeklyQuestError("Invalid player account.")
    if not isinstance(quest_id, str):
        raise WeeklyQuestError("Weekly quest not found.")
    quest = QUEST_BY_ID.get(quest_id)
    if not quest:
        raise WeeklyQuestError("Weekly quest not found.")
    week_key = current_week_key(now)
    savepoint = "weekly_quest_claim"
    nested = await _begin_transaction(db, savepoint)
    try:
        await _require_player(db, user_id)
        await _ensure_week(db, user_id, week_key)
        cur = await db.execute(
            "SELECT progress,claimed FROM player_weekly_quests WHERE user_id=? AND week_key=? AND quest_id=?",
            (user_id, week_key, quest_id),
        )
        row = await cur.fetchone()
        if not row or row["progress"] < quest["target"]:
            raise WeeklyQuestError("Complete this weekly objective before claiming its reward.")
        if row["claimed"]:
            raise WeeklyQuestError("You have already claimed this weekly reward.")
        cur = await db.execute(
            "UPDATE player_weekly_quests SET claimed=1 WHERE user_id=? AND week_key=? AND quest_id=? AND claimed=0",
            (user_id, week_key, quest_id),
        )
        if cur.rowcount != 1:
            raise WeeklyQuestError("You have already claimed this weekly reward.")
        cur = await db.execute(
            "UPDATE players SET coins=coins+?,potions=potions+? WHERE user_id=?",
            (quest["coins"], quest["potions"], user_id),
        )
        if cur.rowcount != 1:
            raise WeeklyQuestError("Player account not found.")
        await _commit_transaction(db, nested, savepoint)
        return {"coins": quest["coins"], "potions": quest["potions"], "title": quest["title"]}
    except Exception:
        await _rollback_transaction(db, nested, savepoint)
        raise

