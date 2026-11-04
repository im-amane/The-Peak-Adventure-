"""Material drops and deterministic equipment crafting."""
import random
import time

from matchmaking_system import MAX_QUEUE_WAIT_SECONDS

MATERIALS={
 "iron_ore":"Iron Ore","ember_shard":"Ember Shard","frost_crystal":"Frost Crystal",
 "void_essence":"Void Essence","star_dust":"Star Dust"
}
RECIPES={
 "iron_sword":{"name":"Forged Iron Sword","slot":"weapon","level":5,"attack":12,"defense":0,
   "cost":{"iron_ore":3,"ember_shard":1}},
 "frost_armor":{"name":"Frostguard Armor","slot":"armor","level":15,"attack":0,"defense":14,
   "cost":{"iron_ore":2,"frost_crystal":3}},
 "rift_blade":{"name":"Riftforged Blade","slot":"weapon","level":50,"attack":38,"defense":0,
   "cost":{"void_essence":3,"star_dust":2,"ember_shard":2}},
 "celestial_mail":{"name":"Celestial Mail","slot":"armor","level":70,"attack":0,"defense":42,
   "cost":{"star_dust":4,"frost_crystal":3,"void_essence":2}},
}

class CraftingError(ValueError):
    pass


def _is_postgres(db):
    return getattr(db, "dialect", "sqlite") == "postgres"


async def _table_exists(db, table):
    if _is_postgres(db):
        cur = await db.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=current_schema() AND table_name=? AND table_type='BASE TABLE'",
            (table,),
        )
    else:
        cur = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
    return await cur.fetchone() is not None


async def _lock_crafting_mode(db, user_id):
    if _is_postgres(db):
        await db.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
            (f"peak-adventure-matchmaking-player:{user_id}",),
        )


async def _has_blocking_player_activity(db, user_id):
    checks = (
        ("battles", "SELECT 1 FROM battles WHERE user_id=? LIMIT 1", (user_id,)),
        ("duels", "SELECT 1 FROM duels WHERE status IN ('pending','active') AND (challenger_id=? OR opponent_id=?) LIMIT 1", (user_id,user_id)),
        ("trades", "SELECT 1 FROM trades WHERE status IN ('pending','open') AND (initiator_id=? OR partner_id=?) LIMIT 1", (user_id,user_id)),
        ("dungeon_runs", "SELECT 1 FROM dungeon_runs WHERE user_id=? AND status='active' LIMIT 1", (user_id,)),
    )
    if await _table_exists(db, "party_members") and await _table_exists(db, "party_battles"):
        cur = await db.execute(
            """SELECT 1 FROM party_members pm JOIN party_battles pb ON pb.party_id=pm.party_id
               WHERE pm.user_id=? AND pb.status='active' LIMIT 1""",
            (user_id,),
        )
        if await cur.fetchone():
            return True
    for table, sql, params in checks:
        if await _table_exists(db, table):
            cur = await db.execute(sql, params)
            if await cur.fetchone():
                return True
    if await _table_exists(db, "matchmaking_queue"):
        cur = await db.execute(
            """SELECT 1 FROM matchmaking_queue
               WHERE user_id=? AND (
                 status='matched' OR (status='queued' AND queued_at>=?)
               ) LIMIT 1""",
            (user_id, int(time.time()) - MAX_QUEUE_WAIT_SECONDS),
        )
        if await cur.fetchone():
            return True
    return False

async def init_crafting_tables(db):
    nested = db.in_transaction
    savepoint = "init_crafting_tables"
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    else:
        await db.execute("BEGIN IMMEDIATE")
    try:
        await db.execute("""CREATE TABLE IF NOT EXISTS player_materials(
          user_id BIGINT NOT NULL,material_id TEXT NOT NULL,quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),
          PRIMARY KEY(user_id,material_id)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS crafted_items(
          user_id BIGINT NOT NULL,recipe_id TEXT NOT NULL,crafted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(user_id,recipe_id)
        )""")
        if nested:
            await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        else:
            await db.commit()
    except Exception:
        if nested:
            await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        else:
            await db.rollback()
        raise

async def get_materials(db,user_id):
    if type(user_id) is not int or user_id <= 0:
        raise CraftingError("Invalid player account.")
    cur=await db.execute("SELECT material_id,quantity FROM player_materials WHERE user_id=? ORDER BY material_id",(user_id,))
    rows=await cur.fetchall()
    return {row["material_id"]:row["quantity"] for row in rows}

async def award_material_drop(db,user_id,monster,rng=None):
    if type(user_id) is not int or user_id <= 0:
        raise CraftingError("Invalid player account.")
    if not isinstance(monster, dict) or type(monster.get("level")) is not int or not 1 <= monster["level"] <= 100:
        raise CraftingError("Invalid monster drop source.")
    rng=rng or random
    chance=0.75 if monster.get("boss") else 0.45
    if rng.random()>chance:return None
    level=monster["level"]
    if level<20:
        material="iron_ore" if rng.random()<0.7 else "ember_shard"
    elif level<40:
        material="frost_crystal" if rng.random()<0.6 else "iron_ore"
    elif level<70:
        material="void_essence" if rng.random()<0.6 else "ember_shard"
    else:
        material="star_dust" if rng.random()<0.6 else "void_essence"
    amount=2 if monster.get("boss") else 1
    await db.execute("""INSERT INTO player_materials(user_id,material_id,quantity) VALUES(?,?,?)
      ON CONFLICT(user_id,material_id) DO UPDATE SET quantity=player_materials.quantity+excluded.quantity""",
      (user_id,material,amount))
    return {"id":material,"name":MATERIALS[material],"quantity":amount}

async def craft_item(db,user_id,player_level,recipe_id):
    if type(user_id) is not int or user_id <= 0:
        raise CraftingError("Invalid player account.")
    if type(player_level) is not int or not 1 <= player_level <= 100:
        raise CraftingError("Invalid player level.")
    if not isinstance(recipe_id,str) or recipe_id not in RECIPES:
        raise CraftingError("Recipe not found.")

    recipe=RECIPES[recipe_id]
    savepoint="craft_item_transaction"
    nested=db.in_transaction
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    else:
        await db.execute("BEGIN IMMEDIATE")
    try:
        await _lock_crafting_mode(db, user_id)
        if await _has_blocking_player_activity(db, user_id):
            raise CraftingError(
                "Finish your active battle, duel, trade, dungeon, PvP queue, or party battle before crafting equipment."
            )
        player=await db.execute(
            "SELECT weapon_attack,armor_defense FROM players WHERE user_id=?",
            (user_id,),
        )
        current_gear = await player.fetchone()
        if current_gear is None:
            raise CraftingError("Player account not found.")
        if player_level<recipe["level"]:
            raise CraftingError("This recipe requires player level "+str(recipe["level"])+".")
        # Preserve the one-time recipe error before checking upgrade strength:
        # a second craft must be reported as a duplicate, not as a weaker item.
        existing=await db.execute(
            "SELECT 1 FROM crafted_items WHERE user_id=? AND recipe_id=?",
            (user_id,recipe_id),
        )
        if await existing.fetchone():
            raise CraftingError("You have already crafted this unique recipe.")

        current_stat = current_gear["weapon_attack"] if recipe["slot"] == "weapon" else current_gear["armor_defense"]
        crafted_stat = recipe["attack"] if recipe["slot"] == "weapon" else recipe["defense"]
        if crafted_stat <= current_stat:
            raise CraftingError("Your equipped gear is already as strong or stronger. Crafting only equips real upgrades.")

        for material,quantity in recipe["cost"].items():
            debit=await db.execute(
                """UPDATE player_materials SET quantity=quantity-?
                   WHERE user_id=? AND material_id=? AND quantity>=?""",
                (quantity,user_id,material,quantity),
            )
            if debit.rowcount!=1:
                raise CraftingError(
                    "Missing materials: "+MATERIALS[material]+" x"+
                    str(quantity-(await get_materials(db,user_id)).get(material,0))
                )

        await db.execute(
            "INSERT INTO crafted_items(user_id,recipe_id) VALUES(?,?)",
            (user_id,recipe_id),
        )
        if recipe["slot"]=="weapon":
            equipped=await db.execute(
                "UPDATE players SET weapon=?,weapon_attack=? WHERE user_id=?",
                (recipe["name"],recipe["attack"],user_id),
            )
        else:
            equipped=await db.execute(
                "UPDATE players SET armor=?,armor_defense=? WHERE user_id=?",
                (recipe["name"],recipe["defense"],user_id),
            )
        if equipped.rowcount!=1:
            raise CraftingError("Player account not found.")
        if nested:
            await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        else:
            await db.commit()
        return recipe
    except CraftingError:
        if nested:
            await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        else:
            await db.rollback()
        raise
    except Exception as exc:
        if nested:
            await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        else:
            await db.rollback()
        raise CraftingError("Crafting failed safely. No materials were consumed.") from exc

async def list_recipes(player_level):
    if type(player_level) is not int or not 1 <= player_level <= 100:
        raise CraftingError("Invalid player level.")
    return [{"id":key,**value,"unlocked":player_level>=value["level"]} for key,value in RECIPES.items()]
