"""Pure game rules shared by the bot and its automated tests."""

MAX_LEVEL = 100
BOSS_LEVELS = frozenset(range(10, MAX_LEVEL + 1, 10))


def xp_required(level: int) -> int:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level must be between 1 and 100")
    return level * 100


def expected_monster_power(level: int) -> int:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level must be between 1 and 100")
    power = 100.0
    for current in range(2, level + 1):
        power *= 1.5 if current in BOSS_LEVELS else 1.1
    return round(power)


def validate_monster_catalogue(monsters: list[dict]) -> None:
    if len(monsters) != MAX_LEVEL:
        raise ValueError(f"Expected {MAX_LEVEL} monsters, found {len(monsters)}")

    levels = [monster.get("level") for monster in monsters]
    if levels != list(range(1, MAX_LEVEL + 1)):
        raise ValueError("Monster levels must be ordered and cover 1 through 100")

    names = [str(monster.get("name", "")).strip().casefold() for monster in monsters]
    if any(not name for name in names) or len(set(names)) != MAX_LEVEL:
        raise ValueError("Every monster must have a non-empty, unique name")

    required = {
        "name", "level", "boss", "rank", "power", "attack_power", "defense",
        "speed", "hp", "element", "special_move", "unique_power",
        "advantage", "disadvantage", "weakness", "story", "trait_effect",
    }
    special_moves = [monster.get("special_move") for monster in monsters]
    unique_powers = [monster.get("unique_power") for monster in monsters]
    stories = [monster.get("story") for monster in monsters]
    if len(set(special_moves)) != MAX_LEVEL or len(set(unique_powers)) != MAX_LEVEL or len(set(stories)) != MAX_LEVEL:
        raise ValueError("Monster moves, unique powers, and story entries must be unique")

    valid_traits = {"regenerate", "fury", "swift", "armored", "drain"}
    for monster in monsters:
        missing = required.difference(monster)
        if missing:
            raise ValueError(f"Monster {monster.get('level')} missing fields: {sorted(missing)}")
        level = monster["level"]
        if not isinstance(monster["power"], int) or monster["power"] != expected_monster_power(level):
            raise ValueError(f"Monster level {level} has incorrect power progression")
        if not isinstance(monster["hp"], int) or monster["hp"] <= 0:
            raise ValueError(f"Monster level {level} must have positive HP")
        if monster["trait_effect"] not in valid_traits:
            raise ValueError(f"Monster level {level} has an unknown combat trait")
        should_be_boss = level in BOSS_LEVELS
        if bool(monster["boss"]) != should_be_boss:
            raise ValueError(f"Monster level {level} has incorrect boss designation")
        if should_be_boss and monster["rank"] != "BOSS":
            raise ValueError(f"Boss level {level} must use BOSS rank")
