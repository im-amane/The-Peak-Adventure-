# The Peak Adventure 🎮

A Telegram turn-based dark-fantasy RPG with a Phaser 3 Mini App. The game is maintained in this dedicated repository, separate from the original music-bot repository.

**Project status:** 168 of 172 tracked implementation items are complete (98%); 2 are partial and 2 are pending. This is an implementation checklist, not a production-launch certification. See [the canonical feature manifest](project_manifest.json) for exact status; [the project structure](PROJECT_STRUCTURE.md) describes repository layout.

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

**Database and launch status:** SQLite is used by the controlled Railway prototype. PostgreSQL support, scheduled logical backups, optional S3-compatible off-site export, and CI restore tests are implemented. Production certification still requires full migration coverage, a real off-site restore drill, process separation, and live Telegram/device/load testing. Setting `DATABASE_URL` explicitly selects PostgreSQL; failures do not silently fall back to SQLite.
- python-dotenv
- Phaser 3 (loaded by the Mini App)

## Setup
1. Create a Telegram bot with @BotFather.
2. Copy `.env.example` to `.env`.
3. Set `BOT_TOKEN`, `WEBAPP_URL`, and `ADMIN_IDS`. Add co-owner Telegram user IDs to `CO_OWNER_IDS`; co-owners receive the same `/admin`, moderation, operations-metrics, and ban-bypass permissions as IDs in `ADMIN_IDS`. The repository default includes the configured co-owner ID `8891272628`. `WEBAPP_URL` should be the Cloudflare Worker URL once the Python backend is deployed. For local SQLite development, leave `DATABASE_URL` unset and use `DATABASE_PATH`; PostgreSQL is selected only when `DATABASE_URL` is explicitly configured.
4. Install Python 3.11+.
5. Install dependencies and start the combined bot + web server:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The server listens on `0.0.0.0:$PORT` when `PORT` is supplied, otherwise `WEB_PORT` (default 8080). Railway injects `PORT` automatically. Configure your hosting provider to route HTTPS traffic to that port. The bot's private-chat menu displays the 2D Mini App button when `WEBAPP_URL` is set.

On Windows, activate with `.venv\\Scripts\\activate`.

## Cloudflare edge gateway

The repository includes a Cloudflare Worker in `cloudflare/worker.mjs`. Cloudflare serves the Mini App's `webapp/` assets globally, while the Worker forwards only the game's known API routes to the Python/Aiohttp origin. It preserves Telegram Mini App authentication headers, rejects unsupported methods and oversized bodies, strips cookies and arbitrary authorization headers, disables caching for authenticated API responses, and enables Worker observability. The Worker does not replace the Python game server or its SQLite database.

When changing `webapp/index.html`, `webapp/style.css`, or `webapp/game.js`, run `python scripts/sync_cloudflare_assets.py` to refresh the Worker fallback copies. CI checks that these embedded copies match the canonical Mini App files.

1. Install Wrangler: `npm install --save-dev wrangler`.
2. Authenticate: `npx wrangler login`.
3. After the Railway backend is deployed and its HTTPS domain is generated, set that exact origin as the Worker secret: `npx wrangler secret put BACKEND_ORIGIN` (origin only, without a path). Do not configure a placeholder domain.
4. Deploy from the repository root: `npx wrangler deploy`.
5. Set the Railway service's `WEBAPP_URL` to the Worker `workers.dev` URL, and register that hostname with BotFather as the Mini App domain.

Do not put `BOT_TOKEN` in the Worker. It remains only in the Python host's secret environment. The Cloudflare account now has the `thepeakadventure.workers.dev` subdomain and the `peak-adventure-edge` Worker is deployed. Public Mini App URL: `https://peak-adventure-edge.thepeakadventure.workers.dev`. Set `BACKEND_ORIGIN` to the deployed Python/Aiohttp HTTPS origin before gameplay API calls can work.

## Controlled prototype launch

The first playable prototype uses the single-instance Railway configuration and SQLite persistent volume documented in [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md). This is a temporary, controlled test deployment only; it does not remove the PostgreSQL, external-backup, and process-separation blockers below. Telegram Stars remain disabled.

## Controlled Railway deployment

[`.railway/railway.ts`](.railway/railway.ts) defines the Railway project, the GitHub `main` service, a single Singapore replica, a 1 GB persistent `/data` volume, environment defaults, and `/healthz` health checks. Apply it explicitly with the Railway CLI after reviewing `railway config plan`; see [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md). Add `BOT_TOKEN` and `ADMIN_IDS` as Railway service variables. This is a controlled prototype, not a public-production certification.

Before a broader launch, complete versioned schema migrations and full PostgreSQL compatibility validation, separate Telegram polling from the HTTP process, perform a real off-site backup download/restore drill, and finish live Telegram, Android WebView, concurrency, security and load testing. Keep exactly one replica while this process uses SQLite and Telegram long polling.

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
- `/stamina` - View stamina and exploration energy regeneration
- `/settings` - Set notification preferences and profile visibility
- `/mana` - View mana, skill cost and regeneration
- `/online` - View active adventurers and online friends
- `/report PLAYER_ID reason` - Submit a player report for administrator review
- `/auction` - Browse active listings; `/auction sell weapon|armor STARTING_BID [HOURS]`, `/auction cancel LISTING_ID`, `/auction stash`, `/auction equip STASH_ID`
- `/bid LISTING_ID AMOUNT` - Place a bid in the auction house
- `/deleteaccount` - Request permanent player-data deletion with an explicit confirmation step
- `/export` - Download your player data as JSON
- `/group register|info|members|missions|claim|raid|ban|unban|top` - Telegram group progression and raids
- `/group event` - View the active shared group monster and its damage leaderboard
- `/fight` - Attack the active shared monster from inside a registered group
- `/admin stats|player|coins|announce|security` - Restricted bot administration, audit log and suspicious-activity review
- `/friend request|accept|decline|list|remove` - Friend requests and friend list (request by replying to a player in a group)
- `/duel` - Challenge a player by replying to their message in a group
- `/pvprank` - PvP rankings
- `/party create|invite|accept|decline|info|leave|disband` - Four-player party management
- `/party explore` - Start a shared world encounter (leader pays stamina)
- `/party battle start|status|attack` - Run a shared party boss encounter
- `/players username` - Search public and friend-visible player profiles
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
Implemented in the repository: ten world biomes, level-gated travel with walk-up portals and landmarks, A-star tap-to-move navigation around obstacles, three-room dungeons, boss-gated hidden areas, daily and weekly missions, party co-op encounters, guild chat/raids/wars, player search, equipment auctions, monster evolution and elite encounters, face/body/hair/outfit customization, class- and appearance-specific 96-frame character sprite sheets with eight-direction idle/walk/run animation, class-based weapon and armor visuals, suspicious-activity telemetry with admin review, procedural attack/skill/hit/death and level-up/respawn effects, ambient music with saved sound preferences, and the authenticated Mini App HUD. Shop rarity tiers and a five-clean-win affordability guard are validated at startup. PostgreSQL logical backup, rotation, checksum verification and guarded restore automation are integrated with the database scheduler. The Peak Gems wallet, Telegram Stars invoices, idempotent payment crediting, gem shop consumables and XP boosts are implemented.

Work still needed before calling the game production-ready:
- Expand portal-linked biomes into larger connected zones with secret areas and richer traversal.
- Finish broader economy balance testing across class matchups, monster traits, evolved/elite variants, crafting, auctions, premium purchases and multiplayer rewards; shop rarity and unlock-level affordability guardrails are already automated.
- Complete physical-device QA on Android/iOS Telegram WebViews, including reconnects and concurrent multiplayer sessions. A responsive mobile Chromium smoke test now runs in CI.
- Configure and verify the production Python backend origin, HTTPS endpoint and persistent PostgreSQL database, then test the full Telegram → Cloudflare Worker → backend flow.
- Run the live Telegram bot smoke test with the production bot token and an authorized test chat.
- Rehearse production off-site backup/restore and run controlled production-like traffic tests; automated PostgreSQL restore and concurrent rate-limit regression tests already run in CI.

Telegram Stars purchases are disabled by default. Enable them only after setting package prices and completing live payment testing with ENABLE_TELEGRAM_STARS=true. The in-game gem shop can still spend gems already in a player wallet.

The PR #204 regression run completed successfully: both the standard `test` job and the PostgreSQL 16 `postgres-adapter` job passed. The workflow also checks Python compilation/imports, JavaScript syntax, Cloudflare embedded-asset parity, Mini App tests, Worker tests and PostgreSQL backup/restore integration. The new PR adds a mobile Chromium smoke job for touch controls and generated sprite sheets. Automated checks do not replace physical Android/iOS WebView, live Telegram, production database or production off-site restore validation. See `docs/PROTOTYPE_ACCEPTANCE.md` for the first playable prototype scope and acceptance gates.

The current hosting configuration is the single-instance Railway prototype defined in `.railway/railway.ts`, with a persistent `/data` volume and `/healthz` health check. No production launch or live end-to-end Telegram verification has been certified. Review the Railway infrastructure plan and any charges before applying it.

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


## Living Telegram group chat events

Registered Telegram groups can trigger ambient monster encounters from ordinary chat activity:
- The bot counts normal human text and media messages; commands, bot messages and Telegram service updates are ignored.
- A random target of 150–200 messages and a random 10–20 minute cooldown must both be reached before a monster appears. The next eligible chat message performs the check.
- Each group has one shared monster with shared HP. Use `/group event` to inspect its health and damage leaderboard, and `/fight` to attack.
- Attacks have a 10-second per-player cooldown. A monster expires after 20 minutes if it survives.
- Contributors earn coins on victory, with a bonus for the top damage contributor; the group also receives group XP.
- The event state and damage contributions persist in the configured database.

**Telegram setup requirement:** disable the bot's Group Privacy Mode in @BotFather so Telegram delivers ordinary group messages to the bot. The feature only counts activity in groups registered with `/group register`.

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
- Malformed battle, world, dungeon, story, social and premium-shop requests are recorded in a bounded-detail security event log.
- Administrators can review aggregated suspicious activity with `/admin security` or inspect a player with `/admin security PLAYER_ID`.
- Security telemetry is reviewed for investigation and does not automatically ban players.


## Telegram Stars premium currency
- Premium wallet balances and Stars transactions are stored in SQLite. Gems can be spent on stamina crystals, potion bundles and three-win XP charms.
- Telegram charge IDs are unique, so duplicate successful-payment updates cannot credit gems twice.
- Payment handling validates invoice owner, package, currency and Stars amount before crediting.
- Purchases are disabled by default. The owner must set `ENABLE_TELEGRAM_STARS=true` and confirm package prices in `.env` before exposing invoices.


## Database backup and recovery

The runtime backup scheduler selects the active database engine:
- SQLite uses the online snapshot utility and configured retention.
- PostgreSQL uses custom-format `pg_dump` archives, `pg_restore --list` verification, SHA-256 sidecars and configured retention.
- When `OFFSITE_BACKUP_BUCKET` is configured, each verified local backup is exported to the configured S3-compatible object store. Uploads include SHA-256 metadata and server-side encryption (AES256 by default, or KMS when configured).

Configure off-site export with `OFFSITE_BACKUP_BUCKET`, `OFFSITE_BACKUP_REGION`, `OFFSITE_BACKUP_PREFIX`, and optionally `OFFSITE_BACKUP_ENDPOINT_URL` / `OFFSITE_BACKUP_KMS_KEY_ID`. Supply credentials through the host's standard AWS/boto3 credential provider. Without a bucket, backups remain local and are not disaster recovery. Configure object-store access controls and lifecycle retention separately.

The guarded PostgreSQL utility also supports manual verification and restore:

```bash
python postgres_backup.py verify postgres_backups/<database>-<timestamp>.dump
python postgres_backup.py restore <backup.dump> --confirm-database <database-name>
```

Restore is destructive to the target database. Stop the application, take a fresh backup, and rehearse recovery against a disposable database before any production restore. CI tests dump and restore against temporary PostgreSQL databases; it does not connect to production or prove that a real cloud bucket can be recovered.
