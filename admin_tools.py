"""Small, testable administrative operations for The Peak Adventure."""
import aiosqlite


class AdminError(ValueError):
    pass


def parse_admin_ids(raw: str) -> set[int]:
    result=set()
    for part in (raw or "").split(","):
        value=part.strip()
        if value.isdecimal() and int(value)>0:
            result.add(int(value))
    return result


async def adjust_player_coins(db: aiosqlite.Connection, user_id: int, delta: int) -> int:
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
    }
    result={"export_version":1,"player_id":user_id,"data":{}}
    for key,(query,params) in tables.items():
        cur=await db.execute(query,params)
        rows=await cur.fetchall()
        result["data"][key]=[dict(row) for row in rows]
    if not result["data"]["profile"]:
        raise AdminError("Player account not found.")
    return result
