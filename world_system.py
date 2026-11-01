"""Unlockable regions and safe fast travel for The Peak Adventure."""
from game_rules import nearby_monster_levels

WORLD_NAMES=(
 "Whispering Meadow","Ashen Desert","Stormglass Highlands","Hollow Kingdom",
 "Ember Abyss","Frostfang Peaks","Primordial Rift","Celestial Ruins",
 "Eternal Hour","Origin Realm",
)

class WorldError(ValueError):
    pass

def world_min_level(world_id):
    if not isinstance(world_id,int) or isinstance(world_id,bool) or not 1<=world_id<=10:
        raise WorldError("World must be between 1 and 10.")
    return (world_id-1)*10+1

def unlocked_world_count(player_level):
    if not isinstance(player_level,int) or isinstance(player_level,bool) or not 1<=player_level<=100:
        raise WorldError("Player level must be between 1 and 100.")
    return min(10,(player_level-1)//10+1)

async def init_world_tables(db):
    await db.execute("""CREATE TABLE IF NOT EXISTS player_worlds(
      user_id INTEGER PRIMARY KEY,current_world INTEGER NOT NULL DEFAULT 1 CHECK(current_world BETWEEN 1 AND 10),
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    await db.commit()

async def get_current_world(db,user_id,player_level):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        raise WorldError("Invalid player account.")
    maximum=unlocked_world_count(player_level)
    cur=await db.execute("SELECT current_world FROM player_worlds WHERE user_id=?",(user_id,))
    row=await cur.fetchone()
    current=min(maximum,row["current_world"]) if row else 1
    await db.execute("""INSERT INTO player_worlds(user_id,current_world) VALUES(?,?)
      ON CONFLICT(user_id) DO UPDATE SET current_world=excluded.current_world""",(user_id,current))
    await db.commit()
    return current

async def travel_to_world(db,user_id,player_level,world_id):
    if not isinstance(world_id,int) or isinstance(world_id,bool) or not 1<=world_id<=10:
        raise WorldError("World must be between 1 and 10.")
    maximum=unlocked_world_count(player_level)
    if world_id>maximum:
        required=world_min_level(world_id)
        raise WorldError(f"{WORLD_NAMES[world_id-1]} unlocks at player level {required}.")
    await db.execute("""INSERT INTO player_worlds(user_id,current_world) VALUES(?,?)
      ON CONFLICT(user_id) DO UPDATE SET current_world=excluded.current_world,updated_at=CURRENT_TIMESTAMP""",
      (user_id,world_id))
    await db.commit()
    return {"world_id":world_id,"name":WORLD_NAMES[world_id-1],"min_level":world_min_level(world_id)}

async def get_world_choices(db,user_id,player_level):
    current=await get_current_world(db,user_id,player_level)
    maximum=unlocked_world_count(player_level)
    return [{"id":i+1,"name":name,"min_level":world_min_level(i+1),
      "unlocked":i+1<=maximum,"current":i+1==current} for i,name in enumerate(WORLD_NAMES)]

def world_encounter_levels(player_level,world_id,boss_defeated=False):
    if not isinstance(player_level,int) or isinstance(player_level,bool) or not 1<=player_level<=100:
        raise WorldError("Player level must be between 1 and 100.")
    world_min=world_min_level(world_id)
    world_max=world_id*10
    effective=min(world_max,max(world_min,player_level))
    candidates=nearby_monster_levels(effective,boss_defeated if effective==world_max else False)
    filtered=tuple(level for level in candidates if world_min<=level<=world_max)
    return filtered or (world_min,)
