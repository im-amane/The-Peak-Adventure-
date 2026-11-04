"""Unlockable regions and safe fast travel for The Peak Adventure."""
from game_rules import nearby_monster_levels

WORLD_NAMES=(
 "Whispering Meadow","Ashen Desert","Stormglass Highlands","Hollow Kingdom",
 "Ember Abyss","Frostfang Peaks","Primordial Rift","Celestial Ruins",
 "Eternal Hour","Origin Realm",
)


WORLD_LANDMARKS=(
 ("Whispering Tree","An ancient tree whispers names of heroes who have not been born."),
 ("Buried Sun Dial","A brass dial points toward a sun that vanished beneath the desert."),
 ("Stormglass Spire","A crystal tower stores the thunder of the first storm."),
 ("Hollow Throne","The throne remembers the king who sacrificed his shadow."),
 ("Furnace Heart","A sealed furnace still beats like a sleeping dragon."),
 ("Frostbound Observatory","An astronomer froze time to keep one star from falling."),
 ("Rift Wound","A scar in the earth leaks memories from another world."),
 ("Celestial Archive","A library records every choice the world refused to make."),
 ("Clockmaker Shrine","A broken clock counts down to a day that already happened."),
 ("Origin Gate","The first doorway waits for the final seal to break.")
)

class WorldError(ValueError):
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


def world_min_level(world_id):
    if not isinstance(world_id,int) or isinstance(world_id,bool) or not 1<=world_id<=10:
        raise WorldError("World must be between 1 and 10.")
    return (world_id-1)*10+1


def unlocked_world_count(player_level):
    if not isinstance(player_level,int) or isinstance(player_level,bool) or not 1<=player_level<=100:
        raise WorldError("Player level must be between 1 and 100.")
    return min(10,(player_level-1)//10+1)


async def _require_player(db, user_id):
    cur = await db.execute("SELECT 1 FROM players WHERE user_id=?", (user_id,))
    if await cur.fetchone() is None:
        raise WorldError("Player account not found.")


async def init_world_tables(db):
    """Initialize world storage without committing a caller-owned transaction."""
    nested = await _begin_transaction(db, "init_world_tables")
    try:
        await db.execute("""CREATE TABLE IF NOT EXISTS player_worlds(
          user_id BIGINT PRIMARY KEY,current_world INTEGER NOT NULL DEFAULT 1 CHECK(current_world BETWEEN 1 AND 10),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS world_discoveries(
          user_id BIGINT NOT NULL,world_id INTEGER NOT NULL,discovered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(user_id,world_id)
        )""")
        await _commit_transaction(db, nested, "init_world_tables")
    except Exception:
        await _rollback_transaction(db, nested, "init_world_tables")
        raise


async def get_current_world(db,user_id,player_level):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        raise WorldError("Invalid player account.")
    maximum=unlocked_world_count(player_level)
    nested=await _begin_transaction(db,"get_current_world")
    try:
        await _require_player(db, user_id)
        cur=await db.execute("SELECT current_world FROM player_worlds WHERE user_id=?",(user_id,))
        row=await cur.fetchone()
        current=min(maximum,row["current_world"]) if row else 1
        await db.execute("""INSERT INTO player_worlds(user_id,current_world) VALUES(?,?)
          ON CONFLICT(user_id) DO UPDATE SET current_world=excluded.current_world""",(user_id,current))
        await _commit_transaction(db,nested,"get_current_world")
        return current
    except Exception:
        await _rollback_transaction(db,nested,"get_current_world")
        raise


async def travel_to_world(db,user_id,player_level,world_id):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        raise WorldError("Invalid player account.")
    if not isinstance(world_id,int) or isinstance(world_id,bool) or not 1<=world_id<=10:
        raise WorldError("World must be between 1 and 10.")
    maximum=unlocked_world_count(player_level)
    if world_id>maximum:
        required=world_min_level(world_id)
        raise WorldError(f"{WORLD_NAMES[world_id-1]} unlocks at player level {required}.")
    nested=await _begin_transaction(db,"travel_to_world")
    try:
        await _require_player(db, user_id)
        await db.execute("""INSERT INTO player_worlds(user_id,current_world) VALUES(?,?)
          ON CONFLICT(user_id) DO UPDATE SET current_world=excluded.current_world,updated_at=CURRENT_TIMESTAMP""",
          (user_id,world_id))
        await _commit_transaction(db,nested,"travel_to_world")
        return {"world_id":world_id,"name":WORLD_NAMES[world_id-1],"min_level":world_min_level(world_id)}
    except Exception:
        await _rollback_transaction(db,nested,"travel_to_world")
        raise


async def get_world_choices(db,user_id,player_level):
    current=await get_current_world(db,user_id,player_level)
    maximum=unlocked_world_count(player_level)
    return [{"id":i+1,"name":name,"min_level":world_min_level(i+1),
      "unlocked":i+1<=maximum,"current":i+1==current} for i,name in enumerate(WORLD_NAMES)]


def world_encounter_levels(player_level,world_id,boss_defeated=False):
    if not isinstance(player_level,int) or isinstance(player_level,bool) or not 1<=player_level<=100:
        raise WorldError("Player level must be between 1 and 100.")
    if type(boss_defeated) is not bool:
        raise WorldError("Boss completion state must be boolean.")
    world_min=world_min_level(world_id)
    world_max=world_id*10
    effective=min(world_max,max(world_min,player_level))
    candidates=nearby_monster_levels(effective,boss_defeated if effective==world_max else False)
    filtered=tuple(level for level in candidates if world_min<=level<=world_max)
    return filtered or (world_min,)


async def get_world_landmark(db,user_id,world_id):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        raise WorldError("Invalid player account.")
    if not isinstance(world_id,int) or isinstance(world_id,bool) or not 1<=world_id<=10:
        raise WorldError("Invalid world.")
    cur=await db.execute("SELECT 1 FROM world_discoveries WHERE user_id=? AND world_id=?",(user_id,world_id))
    found=await cur.fetchone()
    return {"world_id":world_id,"name":WORLD_NAMES[world_id-1],"landmark":WORLD_LANDMARKS[world_id-1][0],
      "description":WORLD_LANDMARKS[world_id-1][1],"discovered":found is not None}


async def discover_world_landmark(db,user_id,player_level,world_id):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        raise WorldError("Invalid player account.")
    world_min_level(world_id)
    if world_id>unlocked_world_count(player_level):
        raise WorldError("This landmark is beyond your unlocked worlds.")
    nested=await _begin_transaction(db,"discover_world_landmark")
    try:
        cur=await db.execute(
            """INSERT INTO world_discoveries(user_id,world_id) VALUES(?,?)
               ON CONFLICT(user_id,world_id) DO NOTHING""",
            (user_id,world_id),
        )
        if cur.rowcount!=1:
            raise WorldError("You have already discovered this landmark.")
        reward=100+world_id*25
        potions=1 if world_id%2 else 2
        cur=await db.execute(
            "UPDATE players SET coins=coins+?,potions=potions+? WHERE user_id=?",
            (reward,potions,user_id),
        )
        if cur.rowcount!=1:
            raise WorldError("Player account not found.")
        await _commit_transaction(db,nested,"discover_world_landmark")
        return {"landmark":WORLD_LANDMARKS[world_id-1][0],"coins":reward,"potions":potions}
    except Exception:
        await _rollback_transaction(db,nested,"discover_world_landmark")
        raise
