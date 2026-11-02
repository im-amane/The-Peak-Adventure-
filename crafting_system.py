"""Material drops and deterministic equipment crafting."""
import random

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

async def init_crafting_tables(db):
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS player_materials(
      user_id INTEGER NOT NULL,material_id TEXT NOT NULL,quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),
      PRIMARY KEY(user_id,material_id)
    );
    CREATE TABLE IF NOT EXISTS crafted_items(
      user_id INTEGER NOT NULL,recipe_id TEXT NOT NULL,crafted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id,recipe_id)
    );
    """)
    await db.commit()

async def get_materials(db,user_id):
    if type(user_id) is not int or user_id <= 0:
        raise CraftingError("Invalid player account.")
    cur=await db.execute("SELECT material_id,quantity FROM player_materials WHERE user_id=? ORDER BY material_id",(user_id,))
    rows=await cur.fetchall()
    return {row["material_id"]:row["quantity"] for row in rows}

async def award_material_drop(db,user_id,monster,rng=None):
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
      ON CONFLICT(user_id,material_id) DO UPDATE SET quantity=quantity+excluded.quantity""",
      (user_id,material,amount))
    await db.commit()
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
    await db.execute(f"SAVEPOINT {savepoint}")
    try:
        player=await db.execute("SELECT 1 FROM players WHERE user_id=?",(user_id,))
        if await player.fetchone() is None:
            raise CraftingError("Player account not found.")
        if player_level<recipe["level"]:
            raise CraftingError("This recipe requires player level "+str(recipe["level"])+".")

        existing=await db.execute(
            "SELECT 1 FROM crafted_items WHERE user_id=? AND recipe_id=?",
            (user_id,recipe_id),
        )
        if await existing.fetchone():
            raise CraftingError("You have already crafted this unique recipe.")

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
                """UPDATE players SET weapon=?,weapon_attack=MAX(weapon_attack,?)
                   WHERE user_id=?""",
                (recipe["name"],recipe["attack"],user_id),
            )
        else:
            equipped=await db.execute(
                """UPDATE players SET armor=?,armor_defense=MAX(armor_defense,?)
                   WHERE user_id=?""",
                (recipe["name"],recipe["defense"],user_id),
            )
        if equipped.rowcount!=1:
            raise CraftingError("Player account not found.")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        return recipe
    except CraftingError:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise
    except Exception as exc:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise CraftingError("Crafting failed safely. No materials were consumed.") from exc

async def list_recipes(player_level):
    if type(player_level) is not int or not 1 <= player_level <= 100:
        raise CraftingError("Invalid player level.")
    return [{"id":key,**value,"unlocked":player_level>=value["level"]} for key,value in RECIPES.items()]
