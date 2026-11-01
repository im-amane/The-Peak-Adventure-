"""Validated persistent character appearance settings."""
import aiosqlite


OPTIONS = {
    "race": {"Human", "Elf", "Dwarf", "Orc"},
    "skin": {"fair", "warm", "tan", "deep"},
    "hair": {"short", "long", "braided", "shaved"},
    "outfit": {"traveler", "knight", "mage", "ranger"},
    "face": {"soft", "angular", "scarred"},
    "body": {"slim", "balanced", "broad"},
}
DEFAULTS = {
    "race": "Human",
    "skin": "warm",
    "hair": "short",
    "outfit": "traveler",
    "face": "soft",
    "body": "balanced",
}


class AppearanceError(ValueError):
    pass


async def init_character_tables(db: aiosqlite.Connection):
    await db.execute("""CREATE TABLE IF NOT EXISTS character_appearance(
      user_id INTEGER PRIMARY KEY,
      race TEXT NOT NULL DEFAULT 'Human',
      skin TEXT NOT NULL DEFAULT 'warm',
      hair TEXT NOT NULL DEFAULT 'short',
      outfit TEXT NOT NULL DEFAULT 'traveler',
      face TEXT NOT NULL DEFAULT 'soft',
      body TEXT NOT NULL DEFAULT 'balanced',
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    cur = await db.execute("PRAGMA table_info(character_appearance)")
    columns = {row[1] for row in await cur.fetchall()}
    if "face" not in columns:
        await db.execute("ALTER TABLE character_appearance ADD COLUMN face TEXT NOT NULL DEFAULT 'soft'")
    if "body" not in columns:
        await db.execute("ALTER TABLE character_appearance ADD COLUMN body TEXT NOT NULL DEFAULT 'balanced'")
    await db.commit()


def validate_appearance(payload):
    if not isinstance(payload, dict):
        raise AppearanceError("Appearance settings must be an object.")
    if set(payload) - set(OPTIONS):
        raise AppearanceError("Unknown character appearance setting.")
    clean = {}
    for key, allowed in OPTIONS.items():
        value = payload.get(key, DEFAULTS[key])
        if not isinstance(value, str) or value not in allowed:
            raise AppearanceError(f"Invalid {key} selection.")
        clean[key] = value
    return clean


async def get_appearance(db, user_id):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise AppearanceError("Invalid player account.")
    cur = await db.execute(
        "SELECT race,skin,hair,outfit,face,body FROM character_appearance WHERE user_id=?",
        (user_id,),
    )
    row = await cur.fetchone()
    return dict(row) if row else dict(DEFAULTS)


async def save_appearance(db, user_id, payload):
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise AppearanceError("Invalid player account.")
    clean = validate_appearance(payload)
    await db.execute(
        """INSERT INTO character_appearance(user_id,race,skin,hair,outfit,face,body)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET
             race=excluded.race,skin=excluded.skin,hair=excluded.hair,
             outfit=excluded.outfit,face=excluded.face,body=excluded.body,
             updated_at=CURRENT_TIMESTAMP""",
        (
            user_id, clean["race"], clean["skin"], clean["hair"],
            clean["outfit"], clean["face"], clean["body"],
        ),
    )
    await db.commit()
    return clean
