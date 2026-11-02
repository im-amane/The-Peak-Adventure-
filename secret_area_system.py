"""Boss-gated hidden areas and one-time discovery rewards."""

from world_system import WORLD_NAMES, world_min_level


class SecretAreaError(ValueError):
    pass


SECRET_AREAS = (
    ("whispering_cavern", "Whispering Cavern", "A crystal cave where the first guardian hid the names of the lost."),
    ("buried_palace", "Buried Palace", "A sandstone palace buried beneath the desert, sealed by the Sun Dial."),
    ("stormglass_observatory", "Stormglass Observatory", "A shattered tower that records every storm and every forgotten name."),
    ("hollow_crypt", "Hollow Crypt", "A royal tomb where the Hollow King's final promise still echoes."),
    ("ember_vault", "Ember Vault", "A vault beneath the abyss, warmed by a flame that refuses to die."),
    ("frostfang_sanctum", "Frostfang Sanctum", "A sanctuary frozen around the last footprints of a lost child."),
    ("rift_hollow", "Rift Hollow", "A hidden chamber between worlds, filled with broken portal keys."),
    ("celestial_archive", "Celestial Archive", "An observatory of memory-stars that preserve the world's oldest stories."),
    ("hourglass_chamber", "Hourglass Chamber", "A room outside time where the same final hour has been replayed for centuries."),
    ("alpha_origin", "The Alpha's Origin", "A quiet place where the Alpha God was once only a small, lonely light."),
)


def _is_postgres(db):
    return getattr(db, "dialect", "sqlite") == "postgres"


async def init_secret_area_tables(db):
    nested = db.in_transaction
    if nested:
        await db.execute("SAVEPOINT init_secret_area_tables")
    else:
        await db.execute("BEGIN IMMEDIATE")
    try:
        timestamp_type = "TIMESTAMPTZ" if _is_postgres(db) else "TEXT"
        await db.execute(f"""CREATE TABLE IF NOT EXISTS player_secret_areas(
          user_id BIGINT NOT NULL,
          world_id INTEGER NOT NULL CHECK(world_id BETWEEN 1 AND 10),
          area_id TEXT NOT NULL,
          discovered_at {timestamp_type} NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(user_id,world_id)
        )""")
        if nested:
            await db.execute("RELEASE SAVEPOINT init_secret_area_tables")
        else:
            await db.commit()
    except Exception:
        if nested:
            await db.execute("ROLLBACK TO SAVEPOINT init_secret_area_tables")
            await db.execute("RELEASE SAVEPOINT init_secret_area_tables")
        else:
            await db.rollback()
        raise


async def get_secret_area_state(db, user_id, player_level, world_id):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise SecretAreaError("Invalid player account.")
    if not isinstance(player_level, int) or isinstance(player_level, bool) or not 1 <= player_level <= 100:
        raise SecretAreaError("Invalid player level.")
    try:
        minimum = world_min_level(world_id)
    except ValueError as exc:
        raise SecretAreaError("Invalid world.") from exc
    if player_level < minimum:
        raise SecretAreaError("This hidden area belongs to a world you have not unlocked.")
    area_id, name, description = SECRET_AREAS[world_id - 1]
    boss_level = world_id * 10
    cur = await db.execute(
        "SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?",
        (user_id, boss_level),
    )
    boss_defeated = await cur.fetchone() is not None
    cur = await db.execute(
        """SELECT COALESCE(SUM(defeats),0) AS total
           FROM player_monster_mastery WHERE user_id=? AND monster_level BETWEEN ? AND ?""",
        (user_id, minimum, boss_level),
    )
    total_defeats = (await cur.fetchone())["total"]
    cur = await db.execute(
        "SELECT 1 FROM player_secret_areas WHERE user_id=? AND world_id=?",
        (user_id, world_id),
    )
    discovered = await cur.fetchone() is not None
    return {
        "world_id": world_id,
        "area_id": area_id,
        "name": name,
        "description": description,
        "boss_defeated": boss_defeated,
        "defeats": total_defeats,
        "target": 5,
        "unlocked": boss_defeated and total_defeats >= 5,
        "discovered": discovered,
    }


async def discover_secret_area(db, user_id, player_level, world_id):
    nested = db.in_transaction
    try:
        if nested:
            await db.execute("SAVEPOINT discover_secret_area")
        else:
            await db.execute("BEGIN IMMEDIATE")
        state = await get_secret_area_state(db, user_id, player_level, world_id)
        if state["discovered"]:
            raise SecretAreaError("You have already discovered this hidden area.")
        if not state["unlocked"]:
            raise SecretAreaError(
                f"Defeat the World {world_id} boss and win 5 battles in this world "
                f"to reveal the hidden area ({state['defeats']}/5 wins)."
            )
        cur = await db.execute(
            """INSERT INTO player_secret_areas(user_id,world_id,area_id) VALUES(?,?,?)
               ON CONFLICT(user_id,world_id) DO NOTHING""",
            (user_id, world_id, state["area_id"]),
        )
        if cur.rowcount != 1:
            raise SecretAreaError("This hidden area has already been discovered.")
        coins = 300 + world_id * 50
        potions = 2
        cur = await db.execute(
            "UPDATE players SET coins=coins+?,potions=potions+? WHERE user_id=?",
            (coins, potions, user_id),
        )
        if cur.rowcount != 1:
            raise SecretAreaError("Player account not found.")
        if nested:
            await db.execute("RELEASE SAVEPOINT discover_secret_area")
        else:
            await db.commit()
        return {**state, "discovered": True, "coins": coins, "potions": potions}
    except Exception:
        if nested:
            await db.execute("ROLLBACK TO SAVEPOINT discover_secret_area")
            await db.execute("RELEASE SAVEPOINT discover_secret_area")
        else:
            await db.rollback()
        raise
