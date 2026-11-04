"""Deterministic coin reward math and shop affordability audit helpers."""

BOSS_LEVELS = frozenset(range(10, 101, 10))


def calculate_battle_coin_reward(
    monster_level: int,
    *,
    is_boss: bool = False,
    is_elite: bool = False,
    is_evolved: bool = False,
) -> int:
    """Return the exact coin payout used by a successful PvE battle."""
    if type(monster_level) is not int or not 1 <= monster_level <= 100:
        raise ValueError("monster_level must be an integer from 1 to 100")
    if any(type(flag) is not bool for flag in (is_boss, is_elite, is_evolved)):
        raise ValueError("battle reward modifiers must be booleans")
    reward = 15 + monster_level * 7
    if is_boss:
        reward += monster_level * 25
    if is_elite:
        reward = int(reward * 1.5)
    if is_evolved:
        reward = int(reward * 1.5)
    return reward


def wins_to_afford(cost: int, coins_per_win: int) -> int:
    """Return the minimum whole number of equal-reward victories needed."""
    if type(cost) is not int or cost < 0:
        raise ValueError("cost must be a non-negative integer")
    if type(coins_per_win) is not int or coins_per_win <= 0:
        raise ValueError("coins_per_win must be a positive integer")
    return (cost + coins_per_win - 1) // coins_per_win


def audit_shop_affordability(shop_items: dict) -> list[dict]:
    """Estimate clean (non-elite, non-evolved) wins needed at each item's unlock level."""
    if not isinstance(shop_items, dict):
        raise ValueError("shop_items must be a dictionary")
    report = []
    for item_id, item in shop_items.items():
        if not isinstance(item_id, str) or not item_id or not isinstance(item, dict):
            raise ValueError("invalid shop item entry")
        level, cost = item.get("level"), item.get("cost")
        if type(level) is not int or not 1 <= level <= 100:
            raise ValueError(f"{item_id} has an invalid unlock level")
        if type(cost) is not int or cost <= 0:
            raise ValueError(f"{item_id} has an invalid coin cost")
        reward = calculate_battle_coin_reward(level, is_boss=level in BOSS_LEVELS)
        report.append({
            "item_id": item_id,
            "unlock_level": level,
            "cost": cost,
            "coins_per_win": reward,
            "wins_to_afford": wins_to_afford(cost, reward),
        })
    return report
