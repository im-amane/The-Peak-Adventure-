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


def validate_rarity_configuration() -> None:
    """Reject incomplete or overlapping rarity definitions before shop validation."""
    if not RARITY_ORDER or len(set(RARITY_ORDER)) != len(RARITY_ORDER):
        raise ValueError("Rarity order must contain unique tiers.")
    expected = set(RARITY_ORDER)
    if set(RARITY_LABELS) != expected or set(RARITY_COIN_BANDS) != expected:
        raise ValueError("Rarity labels and coin bands must cover every ordered tier.")
    previous_high = 0
    for rarity in RARITY_ORDER:
        label = RARITY_LABELS[rarity]
        band = RARITY_COIN_BANDS[rarity]
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Rarity {rarity} has no display label.")
        if (not isinstance(band, tuple) or len(band) != 2
                or any(type(value) is not int for value in band)):
            raise ValueError(f"Rarity {rarity} has an invalid coin band.")
        low, high = band
        if low <= previous_high or high < low:
            raise ValueError("Rarity coin bands must be positive, ordered and non-overlapping.")
        previous_high = high


def get_item_rarity(item_id: str) -> str:
    """Return the display marker for a known shop item."""
    rarity = SHOP_ITEM_RARITY.get(item_id)
    if rarity is None:
        raise ValueError("Unknown shop item rarity.")
    return f"{RARITY_LABELS[rarity]} {rarity.title()}"


def validate_shop_catalog(items: dict) -> None:
    """Fail fast when shop IDs, prices, levels or rarity tiers drift apart."""
    validate_rarity_configuration()
    if not isinstance(items, dict) or set(items) != set(SHOP_ITEM_RARITY):
        raise ValueError("Shop item IDs and rarity catalogue must match exactly.")
    for item_id, item in items.items():
        if not isinstance(item, dict):
            raise ValueError(f"Invalid shop item: {item_id}")
        rarity = SHOP_ITEM_RARITY[item_id]
        if rarity not in RARITY_COIN_BANDS:
            raise ValueError(f"Unknown rarity for shop item: {item_id}")
        cost, level, bonus = item.get("cost"), item.get("level"), item.get("bonus")
        item_type = item.get("type")
        if item_type not in {"weapon", "armor", "potion"}:
            raise ValueError(f"Shop item {item_id} has an invalid equipment type.")
        if any(type(value) is not int for value in (cost, level, bonus)):
            raise ValueError(f"Shop item {item_id} has non-integer economy values.")
        if cost <= 0 or level < 1 or bonus < 0:
            raise ValueError(f"Shop item {item_id} has invalid economy values.")
        low, high = RARITY_COIN_BANDS[rarity]
        if not low <= cost <= high:
            raise ValueError(f"Shop item {item_id} price does not fit its {rarity} tier.")

    # Equipment progression must trade more coins for a meaningful, predictable
    # stat increase. A tier cannot regress in unlock level, rarity, price or
    # power, and cost per stat point cannot jump by more than 2x at one upgrade.
    for slot in ("weapon", "armor"):
        upgrades = sorted(
            (
                (item["level"], RARITY_ORDER.index(SHOP_ITEM_RARITY[item_id]),
                 item["cost"], item["bonus"], item_id)
                for item_id, item in items.items()
                if item["type"] == slot
            ),
            key=lambda entry: entry[0],
        )
        if len(upgrades) < 2:
            raise ValueError(f"Shop catalog needs at least two {slot} upgrades.")
        previous = None
        for level, rarity_rank, cost, bonus, item_id in upgrades:
            if bonus <= 0:
                raise ValueError(f"Shop item {item_id} must provide a positive {slot} bonus.")
            if previous is not None:
                prev_level, prev_rarity, prev_cost, prev_bonus, prev_id = previous
                if level <= prev_level or rarity_rank < prev_rarity:
                    raise ValueError(f"{slot.title()} unlock levels and rarity tiers must progress forward.")
                if cost <= prev_cost or bonus <= prev_bonus:
                    raise ValueError(f"{slot.title()} upgrade cost and bonus must increase.")
                if cost * prev_bonus > prev_cost * bonus * 2:
                    raise ValueError(f"{slot.title()} upgrade {item_id} is over-priced for its stat gain.")
            previous = (level, rarity_rank, cost, bonus, item_id)
