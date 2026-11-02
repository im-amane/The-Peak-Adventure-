# The Peak Adventure 🎮

A Telegram turn-based dark-fantasy RPG with a Phaser 3 Mini App. The game is maintained in this dedicated repository, separate from the original music-bot repository.

## Current features
- Telegram player profiles with four permanent hero classes: Knight, Mage, Archer and Berserker
- 100-level monster catalogue, 10 boss milestones and the original power curve
- 100 distinct monster names, signature moves, unique-power labels and connected story entries
- Ten monster combat traits: regeneration, fury, speed, armor, drain, poison, shield, reflection, lifesteal and berserk
- Turn-based combat with attack, class skill, potions and escape
- Three-phase boss encounters with escalating damage at 60% and 25% HP
- Class passives: Knight defence, Mage's faster skill recovery and speed-based evasion
- Elemental matchups, weapon attack bonuses and armor defence bonuses
- Equipment shop with level-gated weapons, armor and potions
- Persistent story quests and achievements with one-time rewards
- Daily rewards with a rolling 24-hour claim cooldown
- One-time boss clears, player XP/levels, coins, HP and leaderboards
- Group PvP duels with accept/decline, turn-based attacks, surrender and PvP rankings
- Guild creation, membership, 20-player capacity, guild XP/levels and guild rankings
- Four-player parties with leader-only invitations, accept/decline controls, roster view, leave, disband and automatic leadership handoff
- Persistent friend requests, friend list, removal, duplicate-request protection and pending-request anti-spam limits
- Player trading for coins and health potions with dual confirmation
- Phaser 3 Mini App with ten world biomes, custom-drawn 2D scenery, camera-follow scrolling, keyboard/touch movement, obstacle collision and a solid Wanderer NPC
- Multiple level-appropriate monster locations that can be selected directly on the map, with server-side encounter validation
- Per-world NPC dialogue and in-app boss phase display
- Telegram initData HMAC authentication for the Mini App API
- SQLite persistence and automated catalogue/authentication tests

## Tech stack
- Python 3.11+
- aiogram 3
- aiohttp
- aiosqlite / SQLite for local development and current prototype persistence

**Heroku deployment is not ready yet:** the current runtime uses SQLite. Heroku dyno filesystems are ephemeral, so production player data must move to a shared persistent database such as Heroku Postgres before deployment.
- python-dotenv
- Phaser 3 (loaded by the Mini App)

## Setup
1. Create a Telegram bot with @BotFather.
2. Copy `.env.example` to `.env`.
3. Set `BOT_TOKEN`, `WEBAPP_URL`, and `ADMIN_IDS`. `WEBAPP_URL` should be the Cloudflare Worker URL once the Python backend is deployed.
4. Install Python 3.11+.
5. Install dependencies and start the combined bot + web server:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The server listens on `0.0.0.0:$PORT` when `PORT` is supplied, otherwise `WEB_PORT` (default 8080). Configure your hosting provider to route HTTPS traffic to that port. The bot's private-chat menu displays the 2D Mini App button when `WEBAPP_URL` is set.

On Windows, activate with `.venv\\Scripts\\activate`.

## Cloudflare edge gateway

The repository includes a Cloudflare Worker in `cloudflare/worker.mjs`. Cloudflare serves the Mini App's `webapp/` assets globally, while the Worker forwards only the game's known API routes to the Python/Aiohttp origin. It preserves Telegram Mini App authentication headers, rejects unsupported methods and oversized bodies, strips cookies and arbitrary authorization headers, disables caching for authenticated API responses, and enables Worker observability. The Worker does not replace the Python game server or its SQLite database.

When changing `webapp/index.html`, `webapp/style.css`, or `webapp/game.js`, run `python scripts/sync_cloudflare_assets.py` to refresh the Worker fallback copies. CI checks that these embedded copies match the canonical Mini App files.

1. Install Wrangler: `npm install --save-dev wrangler`.
2. Authenticate: `npx wrangler login`.
3. After the Heroku backend is approved and deployed, set its HTTPS origin as the Worker secret: `npx wrangler secret put BACKEND_ORIGIN` (origin only, without a path). Do not configure this against an unverified or temporary backend.
4. Deploy from the repository root: `npx wrangler deploy`.
5. Set Render's `WEBAPP_URL` to the Worker `workers.dev` URL, and register that hostname with BotFather as the Mini App domain.

Do not put `BOT_TOKEN` in the Worker. It remains only in the Python host's secret environment. The Cloudflare account now has the `thepeakadventure.workers.dev` subdomain and the `peak-adventure-edge` Worker is deployed. Public Mini App URL: `https://peak-adventure-edge.thepeakadventure.workers.dev`. Set `BACKEND_ORIGIN` to the deployed Python/Aiohttp HTTPS origin before gameplay API calls can work.

## Heroku deployment readiness

**Target platform: Heroku. Deployment has not been performed.** The repository's `Procfile` already declares `web: python main.py`, and the HTTP server reads Heroku's `PORT` environment variable. However, the current game database is SQLite and the backup loop writes local snapshot files.

Heroku dynos have ephemeral, isolated filesystems. A SQLite database or backup written to a dyno's local disk is not durable across restarts/deploys and is not shared between dynos. Do not deploy a live player database in this configuration.

Before a safe Heroku deployment:
1. Implement and test a PostgreSQL-backed persistence layer and schema migrations. Setting `DATABASE_URL` alone does not convert the current SQLite-specific SQL and transaction handling.
2. Move verified backups to durable external storage or use a verified database backup/restore workflow.
3. Keep the combined bot-polling + HTTP process to a single dyno until polling is separated into a dedicated worker and cross-process concurrency is validated.
4. Configure `BOT_TOKEN`, `ADMIN_IDS`, and `WEBAPP_URL` as Heroku config vars. Keep Telegram Stars disabled.
5. After the backend is deployed and verified, set the Cloudflare Worker secret `BACKEND_ORIGIN` to the Heroku HTTPS origin and set `WEBAPP_URL` to the Worker URL.
6. Complete restart/persistence, real Telegram Mini App, backup/restore, concurrency and load checks before public launch.

The existing `render.yaml` is retained as a legacy deployment artifact; Heroku is the selected target. No Heroku app, database, dyno or paid resource has been provisioned. See [docs/HEROKU_DEPLOYMENT_READINESS.md](docs/HEROKU_DEPLOYMENT_READINESS.md) for the detailed blockers and release checklist.

Keep `BOT_TOKEN` private. Never deploy production or provision paid resources without explicit authorization.


## Commands
- `/start` - Create your hero and open the game menu
- `/profile` - Hero stats, class and equipment
- `/class` - View hero class details
- `/explore` - Find a monster and battle
- `/inventory` - View potions, coins and equipped gear
- `/shop` - Buy weapons, armor and potions
- `/heal` - Restore HP at camp
- `/map` - View the current region
- `/travel` - View unlocked worlds and fast travel with `/travel 3`
- `/story` - Read the ten-chapter branching Chronicle
- `/story chapter ID` - Read a chapter and its NPC dialogue
- `/story choose CHAPTER choice_id` - Choose a story branch
- `/story claim CHAPTER` - Claim chapter rewards
- `/landmarks` - View discovered and undiscovered world landmarks
- `/discover` - Discover your current world landmark and claim its one-time reward
- `/materials` - View collected crafting resources
- `/craft` - View recipes or craft equipment with `/craft iron_sword`
- `/dungeons` - View level-unlocked dungeons
- `/dungeon enter|status|abandon|claim` - Explore three-room dungeons
- `/monster <level>` - Inspect a monster
- `/bestiary` - View discovered monsters
- `/quests` - View story quests and claimable rewards
- `/claimquest <quest_id>` - Claim a completed quest
- `/achievements` - View achievements
- `/claimachievement <achievement_id>` - Claim an achievement
- `/daily` - Claim the daily login reward
- `/premium` - View Peak Gems and Telegram Stars packages (disabled until owner enables them)
- `/premium shop` - Browse gem items; `/premium buy ITEM_ID` - Buy stamina crystals, potion bundles or XP charms
- `/missions` - View daily objectives and claim completed rewards with `/missions claim MISSION_ID`
- `/weekly` - View weekly objectives and claim with `/weekly claim QUEST_ID`
- `/stamina` and `/mana` - View combat resources
- `/settings` - Set notification preferences and profile visibility
- `/deleteaccount` - Request permanent player-data deletion with an explicit confirmation step
- `/export` - Download your player data as JSON
- `/group register|info|members|missions|claim|raid|ban|unban|top` - Telegram group progression and raids
- `/admin stats|player|coins|announce|security` - Restricted bot administration, audit log and suspicious-activity review
- `/friend request|accept|decline|list|remove` - Friend requests and friend list (request by replying to a player in a group)
- `/duel` - Challenge a player by replying to their message in a group
- `/pvprank` - PvP rankings
- `/party create|invite|accept|decline|info|leave|disband` - Four-player party management
- `/party explore` - Start a shared world encounter (leader pays stamina)
- `/party battle start|status|attack` - Run a shared party boss encounter
- `/players username` - Search public and friend-visible player profiles
- `/friend request|accept|decline|list|remove` - Friend system (request by replying to a player in a group)
- `/guild create|join|leave|info|top|disband` - Guild management
- `/guild invite|accept|decline` - Guild invitations
- `/guild role player_id officer|member` - Leader-controlled guild roles
- `/guild announce MESSAGE` - Guild announcement broadcast
- `/guild missions|claim ID` - Daily guild missions and XP
- `/guild raid start|status|attack` - Shared guild boss raids
- `/guild war challenge|accept|decline|status` - Best-of-five guild wars scored by PvP duels
- `/guild chat message` and `/guild history` - Persistent guild member chat
- `/trade` - Start a trade by replying to a player in a group
- `/offer trade_id coins potions` - Set your offer
- `/confirmtrade trade_id` - Confirm the current trade
- `/canceltrade trade_id` - Cancel a trade
- `/leaderboard` - Top adventurers
- `/help` - Show commands

## Tests
Run locally:

```bash
python -m compileall -q .
python -c "import main"
python -m unittest discover -s tests -v
node --check webapp/game.js
node --test cloudflare/worker.test.mjs
```

The repository includes a GitHub Actions workflow configured to compile Python, import the bot module and run the automated test suite on pushes and pull requests to `main`.

## Remaining development and launch readiness
Implemented in the repository: ten world biomes, level-gated travel with walk-up portals and landmarks, A-star tap-to-move navigation around obstacles, three-room dungeons, boss-gated hidden areas, daily and weekly missions, party co-op encounters, guild chat/raids/wars, player search, equipment auctions, monster evolution and elite encounters, face/body/hair/outfit customization with class-based weapon and armor visuals, suspicious-activity telemetry with admin review, procedural attack/skill/hit/death and level-up/respawn effects, ambient music with saved sound preferences, and the authenticated Mini App HUD. The Peak Gems wallet, Telegram Stars invoices, idempotent payment crediting, gem shop consumables and XP boosts are implemented.

Work still needed before calling the game production-ready:
- Expand portal-linked biomes into larger connected zones with secret areas and richer traversal.
- Replace procedural character presentation with polished sprite sheets and complete idle/run/death/level-up animations; class-based weapon visuals and basic procedural movement/combat effects are already present.
- Finish balance and economy testing across all classes, monster traits, evolved/elite variants, crafting, auctions, premium purchases and multiplayer rewards.
- Run browser and real-device QA, including Android Telegram Mini App testing, reconnects, and concurrent multiplayer sessions.
- Configure the production Python backend origin and persistent database, then verify the complete Telegram → Cloudflare Worker → backend flow.
- Complete live Telegram bot, production backup-restore, security and load testing.
- Give the 100-monster narrative catalogue a final editorial pass so every entry feels individually authored.

Telegram Stars purchases are disabled by default. Enable them only after setting package prices and completing live payment testing with ENABLE_TELEGRAM_STARS=true. The in-game gem shop can still spend gems already in a player wallet.

The latest verified GitHub Actions run (#1122) passed all 510 Python unit tests, 10 pathfinding tests and 35 Cloudflare Worker tests. CI also passed Python compile/import checks, JavaScript syntax checks and Cloudflare embedded-asset parity. See `docs/PROTOTYPE_ACCEPTANCE.md` for the first playable prototype scope and acceptance gates.
The project manifest currently tracks 152 items complete, 17 in progress, and 2 blocked on live bot credentials and production database hosting.

The Cloudflare Worker and Render deployment configuration are present, but a configured live Python backend and full production end-to-end launch have not been verified. The included Render blueprint provisions paid resources, so create it only after choosing and authorizing the hosting plan.

The default SQLite database is stored in `peak_adventure.db`. Use a persistent disk on hosts with ephemeral filesystems, or move to PostgreSQL before a larger public launch.

Never commit your real `.env` or bot token.

## Database backup and recovery

The bot creates a SQLite online backup immediately after startup and repeats it every 6 hours by default. Each snapshot is integrity-checked before publication, written atomically, and rotated to retain the newest 7 files. Configure `BACKUP_DIR`, `BACKUP_INTERVAL_SECONDS`, and `BACKUP_RETENTION` in the environment. Keep the backup directory on persistent storage and outside publicly served web assets.

For recovery, stop the bot process first. Verify a snapshot with `python db_backup.py verify backups/<snapshot>.sqlite3`, then restore it with `python db_backup.py restore backups/<snapshot>.sqlite3 --database peak_adventure.db` (use your configured database path). Restore refuses unreadable snapshots and atomically replaces the database only after integrity verification. Restart the bot after verifying the recovered player data.

## Mini App request protection

Authenticated Mini App API requests use a per-Telegram-player sliding-window limiter: up to 120 read requests and 40 write requests per minute. Excess requests receive HTTP 429 with a `Retry-After` header. The limiter uses authenticated Telegram IDs rather than trusting forwarded client-IP headers, and its in-memory key table is bounded. This is an application-level safeguard, not a replacement for a full Cloudflare WAF/rate-limit policy or multi-instance distributed limiting.



## Stamina
- Every player starts with 100 stamina.
- Exploring costs 10 stamina; stamina regenerates by 1 point every five minutes.
- Stamina persists in SQLite and is exposed to the Mini App state API.
- Use `/stamina` to inspect current stamina and regeneration timing.


## Weekly quests and player reports
- Four weekly objectives rotate on the ISO calendar week (UTC): monster victories, boss defeats, crafting and landmark discoveries.
- Weekly progress is saved per player and week; rewards can only be claimed once with `/weekly claim QUEST_ID`.
- Use `/weekly` to view objectives and progress.
- Players can submit a report with `/report PLAYER_ID reason`. Administrators can review reports with `/admin reports` and resolve them with `/admin resolve REPORT_ID reviewed|dismissed [note]`.


## Mana
- Players begin with 100 mana. Class skills cost 30 mana.
- Mana regenerates by 1 point per minute and restores 5 points after each completed combat turn.
- The Telegram command `/mana` shows current mana. The Mini App HUD displays both mana and stamina.


### Party exploration
- Party leaders can start a shared world encounter with `/party explore`.
- The encounter is selected from the leader's currently available world monsters.
- The leader spends 10 stamina; party members are notified and can attack with `/party battle attack`.
- Party members receive individual coin and XP rewards when the shared encounter is defeated.


## Daily missions
- `/missions` shows three UTC-resetting objectives for monster wins, crafting and landmark discovery.
- Claim each completed reward once with `/missions claim MISSION_ID`.
- Daily missions are separate from the `/daily` login reward and `/weekly` objectives.


## Player directory search
- Use `/players username` to find matching player accounts.
- Public profiles appear in search; friends-only profiles are visible only to accepted friends.
- Search results show the player ID and level. Friend requests can still be sent by replying to a player's message in a shared group.


## Roaming world events
- `/event` shows the shared active event for the player's current world.
- `/event attack` contributes damage, with a 30-second per-player cooldown.
- Players who contributed damage can claim a one-time reward with `/event claim EVENT_ID`.
- Events are shared by all players in a world and expire after one hour.


## Monster evolution
- Defeating the same monster five times unlocks its evolved form for that player.
- Mastery is tracked separately for each player and monster.
- Evolved forms have increased HP, attack, defence and speed; they appear in Telegram and Mini App encounters.


## Security and abuse monitoring
- Mini App gameplay remains server-authoritative; clients submit actions, never damage or rewards.
- Malformed battle, world, dungeon, story and social requests are recorded in a bounded-detail security event log.
- Administrators can review aggregated suspicious activity with `/admin security` or inspect a player with `/admin security PLAYER_ID`.
- Security telemetry is reviewed for investigation and does not automatically ban players.


## Telegram Stars premium currency
- Premium wallet balances and Stars transactions are stored in SQLite. Gems can be spent on stamina crystals, potion bundles and three-win XP charms.
- Telegram charge IDs are unique, so duplicate successful-payment updates cannot credit gems twice.
- Payment handling validates invoice owner, package, currency and Stars amount before crediting.
- Purchases are disabled by default. The owner must set `ENABLE_TELEGRAM_STARS=true` and confirm package prices in `.env` before exposing invoices.
