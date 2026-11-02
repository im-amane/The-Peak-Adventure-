"""Persistent multi-room dungeons tied to the ten unlocked worlds."""
import aiosqlite

DUNGEONS=[
 {"id":i+1,"world":i+1,"name":name,"rooms":[(i*10+3,"Scout"),(i*10+6,"Guardian"),((i+1)*10,"World Boss")],
  "reward_coins":150+(i*50),"reward_potions":2}
 for i,name in enumerate(("Rootbound Catacombs","Sunken Sun Vault","Stormglass Labyrinth","Hollow King Crypt",
 "Ember Furnace","Frostfang Deep","Primordial Maw","Celestial Archive","Clockwork Sepulcher","Origin Sanctum"))
]


class DungeonError(ValueError):
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


def _validate_user_id(user_id):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:
        raise DungeonError("Invalid player account.")


async def init_dungeon_tables(db):
    """Initialize dungeon storage without committing a caller-owned transaction."""
    nested = await _begin_transaction(db, "init_dungeon_tables")
    try:
        await db.execute("""CREATE TABLE IF NOT EXISTS dungeon_runs(
          user_id INTEGER PRIMARY KEY,dungeon_id INTEGER NOT NULL,room INTEGER NOT NULL DEFAULT 1,
          status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','abandoned')),
          started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS dungeon_rewards(
          user_id INTEGER NOT NULL,dungeon_id INTEGER NOT NULL,claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(user_id,dungeon_id)
        )""")
        await _commit_transaction(db, nested, "init_dungeon_tables")
    except Exception:
        await _rollback_transaction(db, nested, "init_dungeon_tables")
        raise


def available_dungeons(player_level):
    if not isinstance(player_level,int) or isinstance(player_level,bool) or not 1<=player_level<=100:
        raise DungeonError("Player level must be between 1 and 100.")
    return [{"id":d["id"],"world":d["world"],"name":d["name"],"unlocked":player_level>=((d["world"]-1)*10+1),
      "min_level":(d["world"]-1)*10+1} for d in DUNGEONS]


async def enter_dungeon(db,user_id,player_level,dungeon_id):
    _validate_user_id(user_id)
    if not isinstance(player_level,int) or isinstance(player_level,bool) or not 1<=player_level<=100:
        raise DungeonError("Invalid player level.")
    if not isinstance(dungeon_id,int) or isinstance(dungeon_id,bool) or not 1<=dungeon_id<=10:
        raise DungeonError("Dungeon ID must be between 1 and 10.")
    dungeon=DUNGEONS[dungeon_id-1]
    if player_level<((dungeon["world"]-1)*10+1):
        raise DungeonError(f"This dungeon unlocks at level {(dungeon['world']-1)*10+1}.")
    nested=await _begin_transaction(db,"enter_dungeon")
    try:
        cur=await db.execute("SELECT dungeon_id,status FROM dungeon_runs WHERE user_id=?",(user_id,))
        run=await cur.fetchone()
        if run and run["status"]=="active":
            raise DungeonError("Finish or abandon your active dungeon first.")
        if run and run["status"]=="completed":
            raise DungeonError("Claim your completed dungeon reward before starting another run.")
        cur=await db.execute("SELECT 1 FROM dungeon_rewards WHERE user_id=? AND dungeon_id=?",(user_id,dungeon_id))
        if await cur.fetchone():
            raise DungeonError("You have already claimed this dungeon reward.")
        await db.execute(
            """INSERT INTO dungeon_runs(user_id,dungeon_id,room,status)
               VALUES(?,?,1,'active')
               ON CONFLICT(user_id) DO UPDATE SET dungeon_id=excluded.dungeon_id,
               room=1,status='active',started_at=CURRENT_TIMESTAMP,completed_at=NULL""",
            (user_id,dungeon_id),
        )
        await _commit_transaction(db,nested,"enter_dungeon")
    except Exception:
        await _rollback_transaction(db,nested,"enter_dungeon")
        raise
    return await get_dungeon_state(db,user_id)


async def get_dungeon_state(db,user_id):
    _validate_user_id(user_id)
    cur=await db.execute("SELECT * FROM dungeon_runs WHERE user_id=?",(user_id,))
    run=await cur.fetchone()
    if not run:return None
    if not isinstance(run["dungeon_id"],int) or not 1<=run["dungeon_id"]<=len(DUNGEONS):
        raise DungeonError("Stored dungeon run is invalid.")
    if not isinstance(run["room"],int) or not 1<=run["room"]<=3:
        raise DungeonError("Stored dungeon room is invalid.")
    dungeon=DUNGEONS[run["dungeon_id"]-1]
    room=dungeon["rooms"][run["room"]-1]
    return {"dungeon_id":dungeon["id"],"name":dungeon["name"],"room":run["room"],"room_count":3,
      "target_level":room[0],"room_type":room[1],"status":run["status"],
      "reward_coins":dungeon["reward_coins"],"reward_potions":dungeon["reward_potions"]}


async def advance_dungeon(db,user_id,monster_level):
    _validate_user_id(user_id)
    if not isinstance(monster_level,int) or isinstance(monster_level,bool) or not 1<=monster_level<=100:
        raise DungeonError("Invalid monster level.")
    nested=await _begin_transaction(db,"advance_dungeon")
    try:
        cur=await db.execute("SELECT dungeon_id,room,status FROM dungeon_runs WHERE user_id=?",(user_id,))
        run=await cur.fetchone()
        if not run or run["status"]!="active":
            await _commit_transaction(db,nested,"advance_dungeon")
            return None
        if not isinstance(run["dungeon_id"],int) or not 1<=run["dungeon_id"]<=len(DUNGEONS):
            raise DungeonError("Stored dungeon run is invalid.")
        if not isinstance(run["room"],int) or not 1<=run["room"]<=3:
            raise DungeonError("Stored dungeon room is invalid.")
        dungeon=DUNGEONS[run["dungeon_id"]-1]
        target_level=dungeon["rooms"][run["room"]-1][0]
        if monster_level<target_level:
            await _commit_transaction(db,nested,"advance_dungeon")
            return None
        if run["room"]<3:
            cur=await db.execute(
                "UPDATE dungeon_runs SET room=room+1 WHERE user_id=? AND status='active' AND room=?",
                (user_id,run["room"]),
            )
        else:
            cur=await db.execute(
                "UPDATE dungeon_runs SET status='completed',completed_at=CURRENT_TIMESTAMP WHERE user_id=? AND status='active' AND room=3",
                (user_id,),
            )
        if cur.rowcount!=1:
            raise DungeonError("Dungeon state changed; retry the encounter.")
        await _commit_transaction(db,nested,"advance_dungeon")
    except Exception:
        await _rollback_transaction(db,nested,"advance_dungeon")
        raise
    return await get_dungeon_state(db,user_id)


async def claim_dungeon_reward(db,user_id):
    _validate_user_id(user_id)
    nested=await _begin_transaction(db,"claim_dungeon_reward")
    try:
        cur=await db.execute("SELECT dungeon_id,room,status FROM dungeon_runs WHERE user_id=?",(user_id,))
        run=await cur.fetchone()
        if not run or run["status"]!="completed" or run["room"]!=3:
            raise DungeonError("Complete all three dungeon rooms before claiming rewards.")
        if not isinstance(run["dungeon_id"],int) or not 1<=run["dungeon_id"]<=len(DUNGEONS):
            raise DungeonError("Stored dungeon run is invalid.")
        dungeon=DUNGEONS[run["dungeon_id"]-1]
        await db.execute(
            "INSERT INTO dungeon_rewards(user_id,dungeon_id) VALUES(?,?)",
            (user_id,run["dungeon_id"]),
        )
        cur=await db.execute(
            "UPDATE players SET coins=coins+?,potions=potions+? WHERE user_id=?",
            (dungeon["reward_coins"],dungeon["reward_potions"],user_id),
        )
        if cur.rowcount!=1:
            raise DungeonError("Player account not found.")
        await _commit_transaction(db,nested,"claim_dungeon_reward")
        return dungeon["reward_coins"],dungeon["reward_potions"]
    except aiosqlite.IntegrityError as exc:
        await _rollback_transaction(db,nested,"claim_dungeon_reward")
        raise DungeonError("This dungeon reward has already been claimed.") from exc
    except Exception:
        await _rollback_transaction(db,nested,"claim_dungeon_reward")
        raise


async def abandon_dungeon(db,user_id):
    _validate_user_id(user_id)
    nested=await _begin_transaction(db,"abandon_dungeon")
    try:
        cur=await db.execute("UPDATE dungeon_runs SET status='abandoned' WHERE user_id=? AND status='active'",(user_id,))
        if cur.rowcount==0:
            raise DungeonError("You do not have an active dungeon.")
        await _commit_transaction(db,nested,"abandon_dungeon")
    except Exception:
        await _rollback_transaction(db,nested,"abandon_dungeon")
        raise
