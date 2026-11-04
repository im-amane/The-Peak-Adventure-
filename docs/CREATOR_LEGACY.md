# Amane Fujimiya Creator Legacy

## Permanent attribution

- Game: The Peak Adventure
- Credit: Created & Developed by **Amane Fujimiya**
- Creator ID: **@im_amane**
- Signature: “Every world begins with an imagination. This one began with mine.”

## In-game entry points

- `/credits`: concise official creator credit.
- `/legacy`: opens the creator-lore tribute, **The Forgotten Creator**.

## Secret chronicle

**Mission name:** The Forgotten Creator  
**Mysterious NPC:** The First Architect  
**Lore location:** The Lost Archives, beyond the Origin Realm  
**Creator identity revealed:** Amane Fujimiya (@im_amane)

The First Architect asks who imagined the world before the heroes, monsters and first battle. The final page reveals the creator's name. The lore references the Creator's Emblem, Forgotten Creator title and Amane's Legacy.

## Ownership and integrity rules

1. The creator credit is public and permanent.
2. The creator-only title and emblem are reserved for the project author. They must never be granted through a normal player quest, trade, auction, admin reward, or client-side request.
3. Do not trust a client-provided username or Telegram display name as proof of creator ownership. Any future creator-only badge implementation must use a server-side allowlist based on the author's verified Telegram numeric user ID, stored as a deployment secret/configuration value, not the public handle.
4. Never hard-code a bot token or private Telegram user ID into source control.
5. The current `/legacy` command is a narrative tribute only. It does not grant inventory items, achievements, XP, currency, or alter the existing ten-chapter campaign. A future interactive quest should be added as a separately tested feature with a migration-safe reward ledger.

## Future presentation

- Main menu / credits panel: “Created & Developed by Amane Fujimiya · @im_amane”.
- Creator NPC: The First Architect.
- Reserved profile title: Forgotten Creator.
- Reserved profile emblem: Creator's Emblem.
- Permanent legacy achievement: Amane's Legacy.

These presentation items are specified here; only the bot commands above are implemented in this change.