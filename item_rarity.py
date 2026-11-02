"""Shared rarity tiers and economy metadata for equipment and crafting drops."""

RARITY_TIERS = {
    "common": {"label": "Common", "rank": 1, "price_multiplier": 1.0},
    "uncommon": {"label": "Uncommon", "rank": 2, "price_multiplier": 1.25},
    "rare": {"label": "Rare", "rank": 3, "price_multiplier": 1.6},
    "epic": {"label": "Epic", "rank": 4, "price_multiplier": 2.2},
    "legendary": {"label": "Legendary", "rank": 5, "price_multiplier": 3.0},
}

RARITY_ORDER = tuple(RARITY_TIERS)


def rarity_label(rarity: str) -> str:
    """Return a display label for a known rarity tier."""
    if not isinstance(rarity, str) or rarity not in RARITY_TIERS:
        raise ValueError("Unknown item rarity.")
    return RARITY_TIERS[rarity]["label"]


def rarity_rank(rarity: str) -> int:
    """Return the ordered rarity rank, from common to legendary."""
    if not isinstance(rarity, str) or rarity not in RARITY_TIERS:
        raise ValueError("Unknown item rarity.")
    return RARITY_TIERS[rarity]["rank"]


def rarity_price_multiplier(rarity: str) -> float:
    """Return the balancing multiplier associated with a rarity tier."""
    if not isinstance(rarity, str) or rarity not in RARITY_TIERS:
        raise ValueError("Unknown item rarity.")
    return RARITY_TIERS[rarity]["price_multiplier"]
