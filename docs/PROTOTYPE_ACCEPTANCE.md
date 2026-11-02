# Prototype Acceptance Scope

## Goal

Deliver the first complete, playable version of The Peak Adventure. The prototype is a functional gameplay slice, not a production launch and not a visual-polish milestone.

## Required player journey

1. A player opens the Telegram bot with `/start`, registers, and selects one of the four hero classes.
2. The player opens the Telegram Mini App and sees the authenticated hero profile and current world.
3. The player explores the world, moves with keyboard or touch controls, interacts with the world, and selects a valid monster encounter.
4. The server validates the encounter and resolves combat. The client must never decide damage, XP, coins, drops, or other rewards.
5. Victory and defeat update the player's persistent state correctly. XP, level, coins, inventory, HP, mana, stamina, and battle state must remain consistent.
6. The player can inspect inventory, equip or buy basic gear, use potions, and progress through quests and rewards.
7. The player can unlock and travel to the next available region and encounter its monsters and bosses.
8. The player can close and reopen the bot/Mini App without losing saved progress.

## Prototype acceptance gates

- All automated CI checks pass: Python compile/import, the full unittest suite, Mini App JavaScript syntax, pathfinding tests, Worker tests, and Cloudflare asset parity.
- The Telegram bot can complete registration, class selection, profile, exploration, battle, reward, inventory, and quest flows with a real test bot.
- The Mini App can authenticate through Telegram initData, load player state, explore, start an encounter, and complete a battle on a real mobile Telegram client.
- A restart preserves player progress and the configured database path is on persistent storage for any shared test environment.
- Failed or duplicate reward, trade, battle, and multiplayer actions cannot create currency/items or consume rewards twice.
- A backup can be verified and restored in a test environment.
- Known prototype limitations are documented; no feature is described as live-tested until it has actually been exercised.

## Included in the first prototype

- Four hero classes and persistent player progression.
- The existing monster catalogue, normal battles, boss encounters, rewards, equipment, inventory, and consumables.
- World exploration, region unlocks, landmarks, dungeons, and core story/quest progression.
- Telegram bot commands and the current authenticated Phaser Mini App.
- Existing friend, party, guild, group, PvP, and trading flows where already implemented.
- Core server-side validation, transaction safety, idempotent reward claims, and abuse limits.

## Deferred until after the prototype

- Custom production-grade sprite sheets and complete idle/run animation sets.
- Larger connected multi-zone maps and richer traversal.
- Full friends/party/guild/trading screens inside the Mini App when equivalent Telegram flows already exist.
- Cinematic story presentation, final narrative editing, extra visual effects, and advanced animation polish.
- Full accessibility and cross-device visual polish.
- Production hosting, public launch, large-scale load certification, and paid premium/payment activation.

## Safety and scope constraints

- Keep Telegram Stars purchases disabled unless the owner explicitly authorizes live payment testing.
- Do not provision paid hosting or deploy production resources without explicit authorization.
- Keep PR #9 open and unmerged until the owner makes the merge decision.
- Prototype completion and production readiness are separate statuses. Passing CI alone does not prove live Telegram, mobile-browser, persistence, concurrency, or load readiness.
