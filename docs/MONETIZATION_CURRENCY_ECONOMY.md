# The Peak Adventure — Monetization & Currency Economy Proposal

**Status:** Design proposal only. This document records the agreed direction from the 2026-11-02 planning conversation. It is not yet the live game configuration. Do not enable or expose new prices until economy balancing, Telegram Stars checkout tests, and owner approval are complete.

## 1. Currency hierarchy

| Currency | Role | Main sources | Main uses |
|---|---|---|---|
| Coin | Common/basic | Monsters, quests, gameplay rewards | Basic equipment, common shop purchases, basic upgrades |
| Crystal | Rare gameplay currency | Bosses, rare quests, events, achievements | Rare equipment, advanced upgrades, special crafting |
| Gem | Premium currency | Telegram Stars purchases, pass rewards, occasional events | Premium shop, convenience items, cosmetics, optional exchanges |

Proposed internal reference ratios for balancing:
- 1 Gem = 10 Crystals
- 1 Crystal = 100 Coins
- Therefore 1 Gem = 1,000 Coins

These are balancing reference ratios, not a promise that every shop will offer unlimited direct exchange at these rates. Coin and Crystal exchange offers should have limits and be reviewed against progression rewards to prevent inflation.

## 2. Gem packages (proposed)

| Package | Stars | Base Gems | Bonus Gems | Total Gems |
|---|---:|---:|---:|---:|
| Starter | 50 | 100 | 0 | 100 |
| Adventurer | 100 | 200 | 20 | 220 |
| Warrior | 250 | 500 | 100 | 600 |
| Hero | 500 | 1,000 | 300 | 1,300 |
| Legendary | 1,000 | 2,000 | 800 | 2,800 |
| Ultimate | 2,000 | 5,000 | 2,000 | 7,000 |

Telegram Stars are the in-Telegram payment currency for digital goods in the bot/Mini App. The prices above are proposed package amounts, not activated prices.

## 3. Coin exchange (proposed)

| Coins received | Gem cost |
|---:|---:|
| 5,000 | 5 |
| 15,000 | 15 |
| 40,000 | 40 |
| 100,000 | 100 |
| 250,000 | 250 |
| 600,000 | 600 |

Use daily/weekly limits and test these values against monster, quest, dungeon, auction and other coin sources before enabling.

## 4. Crystal exchange (proposed)

| Crystals received | Gem cost |
|---:|---:|
| 10 | 1 |
| 50 | 5 |
| 150 | 15 |
| 400 | 40 |
| 1,000 | 100 |
| 2,500 | 250 |

Use weekly limits and test these values against boss, quest, event, crafting and upgrade progression before enabling.

## 5. Royal Adventure Pass (proposed)

- Price: 150 Telegram Stars
- Duration: 30 days
- No automatic renewal; player must purchase again.
- Gems on purchase: 100
- Daily reward: 10 Gems and 1,000 Coins per claim, for up to 30 claims.
- Total Gem value if all daily claims are collected: 400 Gems including purchase grant.
- Total Coins if all daily claims are collected: 30,000.
- Additional pass grant: 20 Crystals.
- Includes one exclusive Royal skin, badge, profile frame, Royal Shop access and special monthly missions.
- Daily rewards require a claim. Unclaimed daily rewards expire with the pass unless a later design decision changes this.

Suggested milestone calendar (milestone rewards are additional to the daily reward unless the final economy review changes this):
- Day 7: 25 Gems + 5 Crystals
- Day 14: 40 Gems + Rare Chest
- Day 21: 50 Gems + 5 Crystals
- Day 30: 100 Gems + exclusive reward

**Balancing note:** The milestone calendar currently overlaps with the 400-Gem pass total if treated as additional. Before implementation, decide whether milestone Gems are included in the 400-Gem total or added on top. Do not double-count them.

## 6. Item purchase and upgrade rules

### Purchases
- Common weapons, armor and potions: Coins.
- Rare/Epic equipment: Crystals, optionally with Coins.
- Legendary equipment: Crystals + Coins + rare materials.
- Character/weapon cosmetics, visual effects and cosmetic pets: Gems.
- Optional convenience items (e.g. inventory expansion or limited boosts): Gems, with caps and cooldowns where appropriate.

### Upgrades and crafting
- Basic weapon/armor upgrades: Coins + crafting materials.
- Advanced accessories/special equipment: Coins + Crystals + materials.
- Legendary upgrades: Coins + Crystals + rare materials.
- Pet evolution: Coins + Crystals + evolution materials.
- Gems should not directly increase combat stats or be required for ordinary progression. Avoid pay-to-win advantages.

## 7. Shop navigation proposal

- Gem Shop: Stars packages and Gem balance.
- Membership: Royal Adventure Pass.
- Coin Exchange: Gem-to-Coin packs with limits.
- Crystal Exchange: Gem-to-Crystal packs with limits.
- Equipment Shop: Coin/Crystal purchases.
- Upgrade Station: Coin + material + Crystal costs.
- Cosmetic Shop: Gem purchases.
- Purchase History: transaction and reward history.

## 8. Revenue calculation assumptions (estimates only)

The earlier planning discussion used an approximate Indian player-facing rate of ₹2.05 per Star and an illustrative developer reward of $0.013 per Star. Neither should be hard-coded as a guaranteed INR amount. Player Star purchase prices vary by purchase channel/region/tax, and developer rewards/payout value can vary with Telegram's current rules, exchange rates, TON conversion and fees. Use actual checkout amounts and actual account payout records for financial reporting.

## 9. Implementation and safety checklist

- Keep Telegram Stars as the payment method for digital goods sold inside the Telegram bot/Mini App, subject to current Telegram rules.
- Validate XTR, invoice payload, player ownership, exact Stars amount and successful-payment update.
- Credit Gems only after verified successful payment.
- Enforce unique Telegram charge IDs and idempotent crediting.
- Record refunds/chargebacks and define a safe refund policy.
- Store pass start/end timestamps, claim counts, daily claim idempotency and transaction history.
- Do not auto-renew the pass.
- Never grant rewards from client-provided values; all purchase and reward logic must be server-authoritative.
- Add admin visibility for Stars transactions, Gem liabilities, pass sales and refunds.
- Test economy inflation and exploit resistance before activating Coin/Crystal exchange.
- Do not claim this proposal is implemented merely because it is documented.

## 10. Current repository reality

The repository already contains a Telegram Stars premium wallet/payment ledger and a small Gem shop in premium_system.py. The current implementation is narrower than this proposal: the package catalogue currently has three configurable packages (Spark/Crest/Crown), and the current Gem shop has stamina, potion and XP-boost items. The 30-day pass, proposed expanded package ladder, Coin/Crystal exchange shops and cosmetics are not confirmed as implemented. Treat the current code as the source of truth for live behavior until those features are built and tested.
