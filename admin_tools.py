"""Small, testable administrative operations for The Peak Adventure."""
import aiosqlite


class AdminError(ValueError):
    pass


async def init_admin_tables(db: aiosqlite.Connection):
    await db.execute("""CREATE TABLE IF NOT EXISTS admin_audit_log(
      log_id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id INTEGER NOT NULL,
      action TEXT NOT NULL,target_id INTEGER,details TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    await db.commit()


async def record_admin_action(db,actor_id,action,target_id=None,details=""):
    if not isinstance(actor_id,int) or isinstance(actor_id,bool) or actor_id<=0:
        raise AdminError("Invalid administrator ID.")
    await db.execute("INSERT INTO admin_audit_log(actor_id,action,target_id,details) VALUES(?,?,?,?)",
      (actor_id,str(action)[:64],target_id," ".join(str(details or "").split())[:500]))
    await db.commit()


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


async def adjust_player_coins(db: aiosqlite.Connection, user_id: int, delta: int, actor_id: int | None = None) -> int:
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        raise AdminError("Invalid player ID.")
    if not isinstance(delta,int) or isinstance(delta,bool) or delta==0 or abs(delta)>100000:
        raise AdminError("Coin adjustment must be between -100000 and 100000, excluding zero.")
    cur=await db.execute(
        "UPDATE players SET coins=coins+? WHERE user_id=? AND coins+?>=0",
        (delta,user_id,delta)
    )
    if cur.rowcount==0:
        cur=await db.execute("SELECT 1 FROM players WHERE user_id=?",(user_id,))
        if not await cur.fetchone(): raise AdminError("Player account not found.")
        raise AdminError("Adjustment would make the player's coin balance negative.")
    await db.commit()
    if actor_id is not None:
        await record_admin_action(db,actor_id,"coin_adjustment",user_id,"delta="+str(delta))
    cur=await db.execute("SELECT coins FROM players WHERE user_id=?",(user_id,))
    return (await cur.fetchone())["coins"]


async def dashboard_stats(db: aiosqlite.Connection) -> dict:
    queries={
        "players":"SELECT COUNT(*) AS n FROM players",
        "active_battles":"SELECT COUNT(*) AS n FROM battles",
        "guilds":"SELECT COUNT(*) AS n FROM guilds",
        "registered_groups":"SELECT COUNT(*) AS n FROM group_profiles",
        "active_duels":"SELECT COUNT(*) AS n FROM duels WHERE status='active'",
    }
    result={}
    for key,query in queries.items():
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
        "dungeon_runs":("SELECT * FROM dungeon_runs WHERE user_id=?",(user_id,)),
        "dungeon_rewards":("SELECT * FROM dungeon_rewards WHERE user_id=?",(user_id,)),
    }
    result={"export_version":1,"player_id":user_id,"data":{}}
    for key,(query,params) in tables.items():
        cur=await db.execute(query,params)
        rows=await cur.fetchall()
        result["data"][key]=[dict(row) for row in rows]
    if not result["data"]["profile"]:
        raise AdminError("Player account not found.")
    return result
