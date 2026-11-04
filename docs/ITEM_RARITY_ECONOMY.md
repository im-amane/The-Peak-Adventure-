# Item rarity and coin economy guardrails

The equipment shop now has five named rarity tiers: Common, Uncommon, Rare, Epic and Legendary. The currently sold catalogue uses Common through Epic; Legendary remains reserved for future high-end content. Rarity is descriptive progression metadata and does not itself change combat stats.

## Current shop price bands

| Tier | Coin range | Current shop items |
|---|---:|---|
| Common | 1–100 | Iron Sword, Leather Armor, Health Potion |
| Uncommon | 101–300 | Steel Sword, Iron Armor |
| Rare | 301–750 | Flame Sword, Frostguard Armor |
| Epic | 751–5,000 | Dragon Slayer, Celestial Armor |
| Legendary | 5,001–10,000,000 | Reserved |

The startup validator rejects unknown/missing item IDs, booleans masquerading as integers, invalid levels/stats, and prices outside their assigned tier. The bot displays rarity in shop listings and purchase receipts. Crafting recipes and dropped materials also carry rarity metadata, with progression tiers from common iron ore through epic star dust.

These are guardrails, not a claim that the economy is fully balanced. They do not account for player coin-generation rates, auction prices, quest rewards, elite/evolved multipliers, premium currency, or real-player behavior. Do not change live prices or enable new exchanges based only on these bands. Use gameplay telemetry and controlled playtests before final balance approval.
