# The Peak Adventure: Project Structure & Progress

Repository: https://github.com/im-amane/The-Peak-Adventure-

This document is generated from `project_manifest.json`. The manifest is the single source of truth for feature status; do not edit checklist counts independently.

## Product overview

The Peak Adventure is a Telegram-first, turn-based dark-fantasy RPG with a Phaser 3 Mini App. The Python/Aiohttp service owns game rules, player state and persistence. A Cloudflare Worker serves the web client and forwards the allowlisted game API to the backend.

## Repository layout

```text
The-Peak-Adventure-/
├── main.py                         # Telegram bot, HTTP API and app integration
├── *_system.py                     # Game domains and persistence services
├── postgres_adapter.py             # SQLite/PostgreSQL compatibility layer
├── runtime_monitor.py               # Runtime metrics and alert conditions
├── monsters.json                    # 100-monster catalogue and lore
├── webapp/                           # Phaser Mini App source and browser tests
├── cloudflare/                       # Edge Worker and Worker tests
├── tests/                            # Python unit, integration and PostgreSQL tests
├── scripts/                          # Asset sync, migration and launch checks
├── docs/                             # Runbooks, audits and product references
├── .github/workflows/tests.yml       # Python, PostgreSQL, JS and Worker CI
├── project_manifest.json             # Canonical feature checklist
├── PROJECT_STRUCTURE.md              # This generated progress view
└── README.md                         # Setup, operation and player commands
```

## Feature checklist

Status: [x] complete, [~] partial, [ ] pending.

### 01. Telegram Bot System
- [x] Bot startup and command routing
- [x] /start registration and game menu
- [x] /help command list
- [x] /profile and /class
- [x] /explore and /map
- [x] /inventory and /shop
- [x] /quests and reward claims
- [x] /achievements and reward claims
- [x] /daily rewards
- [x] /leaderboard and PvP rankings
- [x] Inline callback battle controls
- [x] Bot error handling and operational logging
- [x] Admin command panel
- [x] Broadcast and announcement system

### 02. Personal Player System
- [x] Player registration and Telegram identity
- [x] Persistent SQLite player profile
- [x] Four hero classes: Knight, Mage, Archer, Berserker
- [x] Level and XP progression
- [x] HP, coins and potion tracking
- [x] Equipment and inventory basics
- [x] Story quest progress and one-time rewards
- [x] Achievements and one-time rewards
- [x] Daily reward cooldown
- [x] Bestiary discovery
- [x] Player settings and preferences
- [x] Account recovery and data export

### 03. Character Design System
- [x] Four class identities in game data
- [x] Character stats and class passives
- [~] Playable custom character sprite sheets
- [x] Race selection
- [x] Character appearance editor
- [x] Hair, face and body customization
- [x] Armor and outfit visuals
- [x] Weapon appearance visuals
- [~] Idle, walk and run frame animations
- [x] Attack, skill, hit and death animations
- [x] Level-up and cosmetic effects

### 04. 2D Game Engine
- [x] Phaser 3 integration
- [x] 2D world rendering and biome palettes
- [x] Camera follow and scrolling world
- [x] Keyboard movement
- [x] Mobile touch movement
- [x] Obstacle collision
- [x] NPC collision and interaction
- [x] Multiple monster map targets
- [x] Server-validated encounter selection
- [x] Turn-based combat rules
- [x] Boss three-phase combat
- [x] Class passives and dodge rules
- [x] Elemental, weapon and armor combat modifiers
- [x] Monster AI with tactical decision-making
- [x] Advanced physics and pathfinding
- [x] Particle and spell effects
- [x] Sound and music engine

### 05. World and Map System
- [x] Ten biome/world themes
- [x] Level-based world/region selection
- [x] Camera scrolling and map bounds
- [x] Basic obstacles and collision
- [x] Wanderer NPC
- [x] Ten region-specific NPC dialogue lines
- [x] Multiple monster encounter locations
- [x] Large multi-zone maps
- [x] Portals and landmarks
- [x] Dungeons and secret areas
- [x] World unlock and fast travel
- [x] Weather and day/night cycle

### 06. Monster and Boss System
- [x] 100 monster records and ordered levels
- [x] Ten boss milestones at levels 10–100
- [x] Monster power progression rules
- [x] Monster traits and combat effects
- [x] Special move and unique-power data fields
- [x] Advantage, disadvantage and weakness fields
- [x] Monster encounter level validation
- [x] Boss HP phase thresholds at 60% and 25%
- [x] Boss phase damage scaling
- [x] Monster discovery/bestiary basics
- [x] 100 individually authored and lore-consistent stories
- [x] Monster evolution and variants
- [x] Elite and roaming events

### 07. Multiplayer System
- [x] Group-context player duel challenge
- [x] Duel accept and decline
- [x] Turn-based PvP actions
- [x] Surrender and PvP ranking
- [x] Friend requests and friend list
- [x] Online presence
- [x] Party creation and invitations
- [x] Co-op exploration
- [x] Co-op PvE battles
- [x] Team boss raids
- [x] Matchmaking and anti-abuse limits
- [x] Party membership management and leader handoff

### 08. Telegram Group Chat Features
- [x] Duel challenge through group reply
- [x] PvP rankings command
- [x] Player trade initiation through group reply
- [x] Group registration and verification
- [x] Group profile and settings
- [x] Group owner/admin permissions
- [x] Group member roster
- [x] Group XP and level
- [x] Group missions and rewards
- [x] Group boss/raid commands
- [x] Group leaderboard and events
- [x] Group-specific moderation controls

### 09. Guild System
- [x] Guild create/join/leave/info/top/disband commands
- [x] Guild membership capacity (20)
- [x] Guild XP and levels
- [x] Guild rankings
- [x] Guild roles and permissions
- [x] Guild invitations
- [x] Guild chat and announcements
- [x] Guild missions and rewards
- [x] Guild wars
- [x] Guild boss raids

### 10. Telegram Mini App
- [x] Phaser 3 Mini App shell
- [x] Telegram initData HMAC validation
- [x] Player HUD
- [x] 2D world and scrolling camera
- [x] Keyboard and touch controls
- [x] Monster target selection
- [x] Battle HUD and boss phase display
- [x] Skill cooldown and potion availability UI
- [x] Safe API response handling and request guard
- [x] Character customization screen
- [x] Dedicated inventory/equipment/quest screens
- [x] Friends, party, guild and trading screens
- [x] Polished responsive visual design and accessibility audit
- [x] Privacy and notification settings screen

### 11. Economy and Trading
- [x] Coins and potion economy
- [x] Equipment shop
- [x] Level-gated weapons and armor
- [x] Player coin/potion trade offer
- [x] Dual trade confirmation
- [x] Trade cancellation
- [x] Equipment/item trading
- [x] Auction house and market listings
- [x] Crafting and materials
- [~] Item rarity and economy balancing
- [x] Premium currency and payments

### 12. Quest and Story System
- [x] Persistent story quest progress
- [x] One-time quest rewards
- [x] Achievements and claims
- [x] Daily reward loop
- [x] NPC region dialogue
- [x] Quest journal and detailed story UI
- [x] Branching NPC dialogue
- [~] Cinematic story chapters
- [x] World and group quest chains
- [x] 100-monster story editorial rewrite

### 13. Admin, Security and Operations
- [x] Telegram Mini App initData validation
- [x] Duplicate/malformed auth field rejection
- [x] SQLite persistence
- [x] Environment-based secrets configuration
- [x] Basic application logging
- [x] Admin dashboard and role permissions
- [~] Anti-cheat and economy abuse detection
- [x] Rate limiting and abuse protection audit
- [x] SQLite backup and restore automation
- [x] Privacy controls and data deletion workflow
- [x] Production monitoring and alerting
- [~] Durable PostgreSQL backup and restore automation

### 14. Testing and Deployment
- [x] Unit test files for game rules
- [x] Authentication test coverage
- [x] GitHub Actions test workflow
- [x] Automated tests executed successfully
- [x] Python compile/import verification
- [~] Mini App browser/device QA
- [ ] Live Telegram bot test
- [x] Multiplayer concurrency testing
- [~] Security and load testing
- [x] Render/Docker deployment configuration
- [~] Production hosting and HTTPS launch
- [ ] Persistent production database verification


## Progress summary

| Status | Items |
|---|---:|
| Complete | 161 |
| Partial | 9 |
| Pending | 2 |
| **Total** | **172** |

Implementation checklist completion: **93%** (161/172). Partial and pending items are not counted as complete. This is implementation tracking, not production certification.

## Verification policy

A feature is marked complete only when its implementation and required automated regression coverage exist. Browser/device QA, live Telegram behavior, production hosting and real off-site recovery remain separate launch gates.

## CI coverage

The GitHub Actions workflow runs:
- Python compilation and bot import checks.
- The complete Python unit/integration suite.
- PostgreSQL adapter, matchmaking concurrency, Mini App HTTP and backup integration suites against PostgreSQL 16.
- Cloudflare asset parity and JavaScript syntax checks.
- Mini App pathfinding, movement, character, monster animation and Worker tests.

Latest verified PR validation: PR #201's `test` and `postgres-adapter` jobs both completed successfully. This validates those CI suites, not a live production deployment.

## Remaining launch gates

- **PARTIAL** Character Design System: Playable custom character sprite sheets
- **PARTIAL** Character Design System: Idle, walk and run frame animations
- **PARTIAL** Economy and Trading: Item rarity and economy balancing
- **PARTIAL** Quest and Story System: Cinematic story chapters
- **PARTIAL** Admin, Security and Operations: Anti-cheat and economy abuse detection
- **PARTIAL** Admin, Security and Operations: Durable PostgreSQL backup and restore automation
- **PARTIAL** Testing and Deployment: Mini App browser/device QA
- **PENDING** Testing and Deployment: Live Telegram bot test
- **PARTIAL** Testing and Deployment: Security and load testing
- **PARTIAL** Testing and Deployment: Production hosting and HTTPS launch
- **PENDING** Testing and Deployment: Persistent production database verification

## Safe change policy

- Update feature state in `project_manifest.json` first, then regenerate this document.
- Prefer extending an existing domain module and its existing test suite over creating near-duplicate files.
- Delete files only after confirming they are unused and their behavior/tests have been consolidated.
- Do not claim live Telegram, Android WebView, production database, security/load or off-site restore validation without evidence.
- Never commit secrets or deploy/provision paid production resources without explicit authorization.
