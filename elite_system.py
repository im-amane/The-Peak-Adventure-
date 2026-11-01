"""Elite monster encounter rules shared by Telegram and Mini App battles."""
ELITE_SPAWN_CHANCE = 8
ELITE_HP_MULTIPLIER = 1.7
ELITE_ATTACK_MULTIPLIER = 1.35
ELITE_DEFENSE_MULTIPLIER = 1.25
ELITE_SPEED_BONUS = 5
ELITE_REWARD_MULTIPLIER = 1.5


def is_elite_spawn(is_boss, roll):
    """Bosses already have phase mechanics; elite variants apply to regular monsters."""
    if type(is_boss) is not bool:
        raise ValueError("is_boss must be a boolean")
    if type(roll) is not int or not 1 <= roll <= 100:
        raise ValueError("roll must be an integer from 1 to 100")
    return not is_boss and roll <= ELITE_SPAWN_CHANCE


def scale_elite_monster(monster):
    """Return a scaled copy so the immutable base catalogue is never modified."""
    if not isinstance(monster, dict) or not {"hp", "attack_power", "defense", "speed"}.issubset(monster):
        raise ValueError("monster must contain hp, attack_power, defense and speed")
    scaled = dict(monster)
    scaled["hp"] = max(1, int(monster["hp"] * ELITE_HP_MULTIPLIER))
    scaled["attack_power"] = max(1, int(monster["attack_power"] * ELITE_ATTACK_MULTIPLIER))
    scaled["defense"] = max(0, int(monster["defense"] * ELITE_DEFENSE_MULTIPLIER))
    scaled["speed"] = min(100, monster["speed"] + ELITE_SPEED_BONUS)
    return scaled
