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
    if not isinstance(monsters, list) or len(monsters) != MAX_LEVEL:
        count = len(monsters) if isinstance(monsters, list) else "non-list"
        raise ValueError(f"Expected a list of {MAX_LEVEL} monsters, found {count}")

    levels = [monster.get("level") if isinstance(monster, dict) else None for monster in monsters]
    if levels != list(range(1, MAX_LEVEL + 1)):
        raise ValueError("Monster levels must be ordered and cover 1 through 100")

    required = {
        "name", "level", "boss", "rank", "power", "attack_power", "defense",
        "speed", "hp", "element", "special_move", "unique_power",
        "advantage", "disadvantage", "weakness", "story", "trait_effect",
    }
    text_fields = {
        "name", "rank", "element", "special_move", "unique_power",
        "advantage", "disadvantage", "weakness", "story", "trait_effect",
    }
    numeric_fields = {"power", "attack_power", "defense", "speed", "hp"}
    unique_fields = ("name", "special_move", "unique_power", "story")
    valid_traits = {"regenerate", "fury", "swift", "armored", "drain", "poison", "shield", "reflect", "lifesteal", "berserk"}

    for monster in monsters:
        level = monster.get("level", "unknown")
        missing = required.difference(monster)
        if missing:
            raise ValueError(f"Monster {level} missing fields: {sorted(missing)}")

        for field in text_fields:
            value = monster[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Monster level {level} has an empty or invalid {field}")

        if type(monster["level"]) is not int or not 1 <= monster["level"] <= MAX_LEVEL:
            raise ValueError(f"Monster level {level} must be an integer from 1 to 100")
        if type(monster["boss"]) is not bool:
            raise ValueError(f"Monster level {level} boss flag must be boolean")

        for field in numeric_fields:
            value = monster[field]
            if type(value) is not int:
                raise ValueError(f"Monster level {level} {field} must be an integer")
            minimum = 1 if field in {"power", "hp"} else 0
            if value < minimum:
                raise ValueError(f"Monster level {level} {field} must be at least {minimum}")

        if monster["power"] != expected_monster_power(level):
            raise ValueError(f"Monster level {level} has incorrect power progression")
        if monster["trait_effect"] not in valid_traits:
            raise ValueError(f"Monster level {level} has an unknown combat trait")

        should_be_boss = level in BOSS_LEVELS
        if monster["boss"] != should_be_boss:
            raise ValueError(f"Monster level {level} has incorrect boss designation")
        if should_be_boss and monster["rank"] != "BOSS":
            raise ValueError(f"Boss level {level} must use BOSS rank")
        if not should_be_boss and monster["rank"] == "BOSS":
            raise ValueError(f"Non-boss level {level} cannot use BOSS rank")

    for field in unique_fields:
        values = [monster[field].strip().casefold() for monster in monsters]
        if len(set(values)) != MAX_LEVEL:
            raise ValueError(f"Every monster must have a unique {field}")

 
def calculate_enemy_damage(
    attack_power: int,
    player_level: int,
    armor_defense: int,
    class_defense: int,
    monster_speed: int,
    random_bonus: int,
    *,
    fury: bool = False,
    special: bool = False,
) -> int:
    """Return monster damage after player mitigation and monster modifiers."""
    damage = max(
        3,
        attack_power - player_level * 2 - armor_defense - class_defense
        + monster_speed // 12 + random_bonus,
    )
    if fury:
        damage = int(damage * 1.25)
    if special:
        damage = int(damage * 1.5)
    return damage

 
def skill_cooldown_for_class(hero_class: str) -> int:
    """Return the stored cooldown; same-turn tick means Mage recovers sooner."""
    return 3 if hero_class == "Mage" else 4


def class_evades(class_speed: int, roll: int) -> bool:
    """Resolve a class speed dodge roll where speed is the percentage chance."""
    if not 0 <= class_speed <= 100 or not 1 <= roll <= 100:
        raise ValueError("speed must be 0..100 and roll must be 1..100")
    return roll <= class_speed
