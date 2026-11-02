"""Per-player monster mastery and evolved encounter variants."""
EVOLUTION_DEFEATS_REQUIRED = 5
EVOLVED_HP_MULTIPLIER = 1.5
EVOLVED_ATTACK_MULTIPLIER = 1.3
EVOLVED_DEFENSE_MULTIPLIER = 1.2
EVOLVED_SPEED_BONUS = 3


class EvolutionError(ValueError):
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


async def init_evolution_tables(db):
    await db.execute("""CREATE TABLE IF NOT EXISTS player_monster_mastery(
      user_id INTEGER NOT NULL,
      monster_level INTEGER NOT NULL CHECK(monster_level BETWEEN 1 AND 100),
      defeats INTEGER NOT NULL DEFAULT 0 CHECK(defeats >= 0),
      evolved_at TIMESTAMPTZ,
      PRIMARY KEY(user_id,monster_level)
    )""")


async def record_monster_defeat(db, user_id, monster_level):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise EvolutionError("Invalid player account.")
    if not isinstance(monster_level, int) or isinstance(monster_level, bool) or not 1 <= monster_level <= 100:
        raise EvolutionError("Invalid monster level.")

    savepoint = "record_monster_defeat"
    nested = await _begin_transaction(db, savepoint)
    try:
        await db.execute(
            """INSERT INTO player_monster_mastery(user_id,monster_level,defeats)
               VALUES(?,?,1)
               ON CONFLICT(user_id,monster_level) DO UPDATE SET defeats=defeats+1""",
            (user_id, monster_level),
        )
        await db.execute(
            """UPDATE player_monster_mastery SET evolved_at=COALESCE(evolved_at,CURRENT_TIMESTAMP)
               WHERE user_id=? AND monster_level=? AND defeats>=?""",
            (user_id, monster_level, EVOLUTION_DEFEATS_REQUIRED),
        )
        cur = await db.execute(
            "SELECT defeats,evolved_at FROM player_monster_mastery WHERE user_id=? AND monster_level=?",
            (user_id, monster_level),
        )
        row = await cur.fetchone()
        if row is None:
            raise EvolutionError("Monster mastery could not be recorded.")
        await _commit_transaction(db, nested, savepoint)
        return {"defeats": row["defeats"], "evolved": row["evolved_at"] is not None}
    except Exception:
        await _rollback_transaction(db, nested, savepoint)
        raise


async def get_evolution_state(db, user_id, monster_level):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise EvolutionError("Invalid player account.")
    if not isinstance(monster_level, int) or isinstance(monster_level, bool) or not 1 <= monster_level <= 100:
        raise EvolutionError("Invalid monster level.")
    cur = await db.execute(
        "SELECT defeats,evolved_at FROM player_monster_mastery WHERE user_id=? AND monster_level=?",
        (user_id, monster_level),
    )
    row = await cur.fetchone()
    defeats = row["defeats"] if row else 0
    evolved = bool(row and row["evolved_at"])
    return {"defeats": defeats, "required": EVOLUTION_DEFEATS_REQUIRED, "evolved": evolved}


def scale_evolved_monster(monster):
    """Create a stronger evolved form without mutating the base monster catalogue."""
    if not isinstance(monster, dict) or not {"name", "hp", "attack_power", "defense", "speed"}.issubset(monster):
        raise ValueError("monster must contain name, hp, attack_power, defense and speed")
    evolved = dict(monster)
    evolved["name"] = "Ascended " + str(monster["name"])
    evolved["hp"] = max(1, int(monster["hp"] * EVOLVED_HP_MULTIPLIER))
    evolved["attack_power"] = max(1, int(monster["attack_power"] * EVOLVED_ATTACK_MULTIPLIER))
    evolved["defense"] = max(0, int(monster["defense"] * EVOLVED_DEFENSE_MULTIPLIER))
    evolved["speed"] = min(100, monster["speed"] + EVOLVED_SPEED_BONUS)
    evolved["unique_power"] = str(monster.get("unique_power", "")) + " · Evolved Form"
    evolved["special_move"] = str(monster.get("special_move", "")) + " · Ascended"
    return evolved


def is_evolved_spawn(mastered, roll):
    """A mastered species has a 25% chance to appear in its evolved form."""
    if not isinstance(roll, int) or isinstance(roll, bool) or not 1 <= roll <= 100:
        raise ValueError("roll must be an integer from 1 to 100")
    return bool(mastered) and roll <= 25
