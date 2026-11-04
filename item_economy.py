"""Shared rarity labels and guardrails for the coin equipment shop."""

RARITY_ORDER = ("common", "uncommon", "rare", "epic", "legendary")
RARITY_LABELS = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟠",
}
SHOP_ITEM_RARITY = {
    "iron_sword": "common",
    "steel_sword": "uncommon",
    "flame_sword": "rare",
    "dragon_slayer": "epic",
    "leather_armor": "common",
    "iron_armor": "uncommon",
    "frostguard_armor": "rare",
    "celestial_armor": "epic",
    "health_potion": "common",
}
RARITY_COIN_BANDS = {
    "common": (1, 100),
    "uncommon": (101, 300),
    "rare": (301, 750),
    "epic": (751, 5_000),
    "legendary": (5_001, 10_000_000),
}


def get_item_rarity(item_id: str) -> str:
    """Return the display marker for a known shop item."""
    rarity = SHOP_ITEM_RARITY.get(item_id)
    if rarity is None:
        raise ValueError("Unknown shop item rarity.")
    return f"{RARITY_LABELS[rarity]} {rarity.title()}"


def validate_shop_catalog(items: dict) -> None:
    """Fail fast when shop IDs, prices, levels or rarity tiers drift apart."""
    if not isinstance(items, dict) or set(items) != set(SHOP_ITEM_RARITY):
        raise ValueError("Shop item IDs and rarity catalogue must match exactly.")
    for item_id, item in items.items():
        if not isinstance(item, dict):
            raise ValueError(f"Invalid shop item: {item_id}")
        rarity = SHOP_ITEM_RARITY[item_id]
        if rarity not in RARITY_COIN_BANDS:
            raise ValueError(f"Unknown rarity for shop item: {item_id}")
        cost, level, bonus = item.get("cost"), item.get("level"), item.get("bonus")
        if any(type(value) is not int for value in (cost, level, bonus)):
            raise ValueError(f"Shop item {item_id} has non-integer economy values.")
        if cost <= 0 or level < 1 or bonus < 0:
            raise ValueError(f"Shop item {item_id} has invalid economy values.")
        low, high = RARITY_COIN_BANDS[rarity]
        if not low <= cost <= high:
            raise ValueError(f"Shop item {item_id} price does not fit its {rarity} tier.")
