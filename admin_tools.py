"""Small, testable administrative operations for The Peak Adventure."""
import aiosqlite
from functools import wraps


class AdminError(ValueError):
    pass


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
    """Keep admin mutations atomic and preserve caller-owned transactions."""
    @wraps(function)
    async def wrapped(db,*args,**kwargs):
        savepoint="admin_"+function.__name__
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
async def init_admin_tables(db: aiosqlite.Connection):
    await db.execute("""CREATE TABLE IF NOT EXISTS admin_audit_log(
      log_id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id INTEGER NOT NULL,
      action TEXT NOT NULL,target_id INTEGER,details TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")


@_transactional
async def record_admin_action(db,actor_id,action,target_id=None,details=""):
    if not isinstance(actor_id,int) or isinstance(actor_id,bool) or actor_id<=0:
        raise AdminError("Invalid administrator ID.")
    if not isinstance(action,str) or not action.strip():
        raise AdminError("Invalid administrative action.")
    if target_id is not None and (not isinstance(target_id,int) or isinstance(target_id,bool) or target_id<=0):
        raise AdminError("Invalid administrative target.")
    if not isinstance(details,str):
        raise AdminError("Invalid administrative details.")
    cur=await db.execute("INSERT INTO admin_audit_log(actor_id,action,target_id,details) VALUES(?,?,?,?)",
      (actor_id,action.strip()[:64],target_id," ".join(details.split())[:500]))
    if cur.rowcount != 1:
        raise AdminError("Administrative action could not be recorded.")


@_transactional
async def adjust_player_coins(db: aiosqlite.Connection, user_id: int, delta: int, actor_id: int | None = None) -> int:
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        raise AdminError("Invalid player ID.")
    if not isinstance(delta,int) or isinstance(delta,bool) or delta==0 or abs(delta)>100000:
        raise AdminError("Coin adjustment must be between -100000 and 100000, excluding zero.")
    if actor_id is not None and (not isinstance(actor_id,int) or isinstance(actor_id,bool) or actor_id<=0):
        raise AdminError("Invalid administrator ID.")
    cur=await db.execute("SELECT coins FROM players WHERE user_id=?",(user_id,))
    player=await cur.fetchone()
    if not player:
        raise AdminError("Player account not found.")
    new_balance=player["coins"]+delta
    if new_balance<0:
        raise AdminError("Adjustment would make the player's coin balance negative.")
    cur=await db.execute(
        "UPDATE players SET coins=? WHERE user_id=? AND coins=?",
        (new_balance,user_id,player["coins"]),
    )
    if cur.rowcount != 1:
        raise AdminError("Player coin balance changed; retry the adjustment.")
    if actor_id is not None:
        await record_admin_action(db,actor_id,"coin_adjustment",user_id,"delta="+str(delta))
    cur=await db.execute("SELECT coins FROM players WHERE user_id=?",(user_id,))
    row=await cur.fetchone()
    if not row:
        raise AdminError("Player account disappeared during coin adjustment.")
    return row["coins"]


async def recent_admin_actions(db,limit=20):
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=100:
        raise AdminError("Invalid audit log limit.")
    cur=await db.execute("SELECT log_id,actor_id,action,target_id,details,created_at FROM admin_audit_log ORDER BY log_id DESC LIMIT ?",(limit,))
    return await cur.fetchall()


def parse_admin_ids(raw: str) -> set[int]:
    result=set()
    for part in (raw or "").split(","):
        value=part.strip()
        if value.isdecimal() and int(value)>0:
            result.add(int(value))
    return result


async def dashboard_stats(db: aiosqlite.Connection) -> dict:
    queries={
        "players":"SELECT COUNT(*) AS n FROM players",
        "active_battles":"SELECT COUNT(*) AS n FROM battles",
        "guilds":"SELECT COUNT(*) AS n FROM guilds",
        "registered_groups":"SELECT COUNT(*) AS n FROM group_profiles",
        "active_duels":"SELECT COUNT(*) AS n FROM duels WHERE status='active'",
        "security_events_24h":"SELECT COUNT(*) AS n FROM security_events WHERE created_at >= datetime('now','-24 hours')",
        "stars_received":"SELECT COALESCE(SUM(stars),0) AS n FROM premium_transactions",
        "premium_gems_issued":"SELECT COALESCE(SUM(gems),0) AS n FROM premium_transactions",
    }
    result={}
    optional_tables={"security_events_24h":"security_events","stars_received":"premium_transactions","premium_gems_issued":"premium_transactions"}
    for key,query in queries.items():
        if key in optional_tables:
            cur=await db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(optional_tables[key],))
            if not await cur.fetchone():
                result[key]=0
                continue
        cur=await db.execute(query)
        result[key]=(await cur.fetchone())["n"]
    return result


async def export_player_data(db: aiosqlite.Connection, user_id: int) -> dict:
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        raise AdminError("Invalid player ID.")
    tables={
        "profile":("SELECT * FROM players WHERE user_id=?",(user_id,)),
        "active_battle":("SELECT * FROM battles WHERE user_id=?",(user_id,)),
        "quests":("SELECT * FROM quest_progress WHERE user_id=?",(user_id,)),
        "achievements":("SELECT * FROM achievement_progress WHERE user_id=?",(user_id,)),
        "monster_discoveries":("SELECT * FROM monster_discoveries WHERE user_id=?",(user_id,)),
        "boss_defeats":("SELECT * FROM boss_defeats WHERE user_id=?",(user_id,)),
        "duels":("SELECT * FROM duels WHERE challenger_id=? OR opponent_id=?",(user_id,user_id)),
        "appearance":("SELECT * FROM character_appearance WHERE user_id=?",(user_id,)),
        "settings":("SELECT * FROM player_settings WHERE user_id=?",(user_id,)),
        "friends":("SELECT * FROM friend_requests WHERE user_low=? OR user_high=?",(user_id,user_id)),
        "materials":("SELECT * FROM player_materials WHERE user_id=?",(user_id,)),
        "crafted_items":("SELECT * FROM crafted_items WHERE user_id=?",(user_id,)),
        "world_progress":("SELECT * FROM player_worlds WHERE user_id=?",(user_id,)),
        "presence":("SELECT * FROM player_presence WHERE user_id=?",(user_id,)),
        "world_discoveries":("SELECT * FROM world_discoveries WHERE user_id=?",(user_id,)),
        "daily_missions":("SELECT * FROM player_daily_missions WHERE user_id=? ORDER BY day_key DESC",(user_id,)),
        "weekly_quests":("SELECT * FROM player_weekly_quests WHERE user_id=? ORDER BY week_key DESC",(user_id,)),
        "monster_mastery":("SELECT * FROM player_monster_mastery WHERE user_id=? ORDER BY monster_level",(user_id,)),
        "secret_areas":("SELECT * FROM player_secret_areas WHERE user_id=? ORDER BY world_id",(user_id,)),
        "roaming_event_participation":("SELECT * FROM roaming_event_participants WHERE user_id=? ORDER BY event_id DESC",(user_id,)),
        "stamina":("SELECT * FROM player_stamina WHERE user_id=?",(user_id,)),
        "mana":("SELECT * FROM player_mana WHERE user_id=?",(user_id,)),
        "story_progress":("SELECT * FROM player_story WHERE user_id=?",(user_id,)),
        "story_flags":("SELECT * FROM story_flags WHERE user_id=?",(user_id,)),
        "story_rewards":("SELECT * FROM story_reward_claims WHERE user_id=?",(user_id,)),
        "dungeon_runs":("SELECT * FROM dungeon_runs WHERE user_id=?",(user_id,)),
        "dungeon_rewards":("SELECT * FROM dungeon_rewards WHERE user_id=?",(user_id,)),
        "security_events":("SELECT event_type,severity,details,created_at FROM security_events WHERE user_id=? ORDER BY event_id DESC",(user_id,)),
        "premium_wallet":("SELECT balance,updated_at FROM premium_wallets WHERE user_id=?",(user_id,)),
        "premium_transactions":("SELECT package_id,stars,gems,created_at FROM premium_transactions WHERE user_id=? ORDER BY transaction_id DESC",(user_id,)),
        "premium_purchases":("SELECT item_id,gems_spent,created_at FROM premium_shop_purchases WHERE user_id=? ORDER BY purchase_id DESC",(user_id,)),
        "xp_boost":("SELECT remaining_wins FROM player_xp_boosts WHERE user_id=?",(user_id,)),
    }
    optional_tables = {
        "security_events":"security_events",
        "premium_wallet":"premium_wallets",
        "premium_transactions":"premium_transactions",
        "premium_purchases":"premium_shop_purchases",
        "xp_boost":"player_xp_boosts",
        "daily_missions":"player_daily_missions",
        "weekly_quests":"player_weekly_quests",
        "monster_mastery":"player_monster_mastery",
        "secret_areas":"player_secret_areas",
        "roaming_event_participation":"roaming_event_participants",
        "stamina":"player_stamina",
        "mana":"player_mana",
    }
    result={"export_version":1,"player_id":user_id,"data":{}}
    for key,(query,params) in tables.items():
        if key in optional_tables:
            cur=await db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(optional_tables[key],))
            if not await cur.fetchone():
                result["data"][key]=[]
                continue
        cur=await db.execute(query,params)
        rows=await cur.fetchall()
        result["data"][key]=[dict(row) for row in rows]
    if not result["data"]["profile"]:
        raise AdminError("Player account not found.")
    return result
