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
- aiosqlite / SQLite
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

1. Install Wrangler: `npm install --save-dev wrangler`.
2. Authenticate: `npx wrangler login`.
3. Set the deployed Python service URL as the Worker secret: `npx wrangler secret put BACKEND_ORIGIN` (enter the HTTPS Render/VPS origin, without a path).
4. Deploy from the repository root: `npx wrangler deploy`.
5. Set Render's `WEBAPP_URL` to the Worker `workers.dev` URL, and register that hostname with BotFather as the Mini App domain.

Do not put `BOT_TOKEN` in the Worker. It remains only in the Python host's secret environment. The Cloudflare account now has the `thepeakadventure.workers.dev` subdomain and the `peak-adventure-edge` Worker is deployed. Public Mini App URL: `https://peak-adventure-edge.thepeakadventure.workers.dev`. Set `BACKEND_ORIGIN` to the deployed Python/Aiohttp HTTPS origin before gameplay API calls can work.

## Deploy with Render
1. Push this repository to GitHub and create a new Blueprint in Render.
2. Select this repository so Render reads `render.yaml`.
3. Set `BOT_TOKEN` to the token from @BotFather.
4. Set `ADMIN_IDS` to comma-separated Telegram user IDs allowed to use `/admin`.
5. Set `WEBAPP_URL` to `https://peak-adventure-edge.thepeakadventure.workers.dev`.
6. Set the Cloudflare Worker secret `BACKEND_ORIGIN` to the Render HTTPS origin, without a path.
7. Register `thepeakadventure.workers.dev` as the Mini App domain with BotFather.
8. Deploy. The blueprint includes a persistent disk mounted at `/data` so the SQLite player database survives restarts.

The included Render blueprint uses a paid Starter web service and a persistent disk. For a VPS, build the included Dockerfile and pass the same environment variables. Keep `BOT_TOKEN` private.


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
- `/daily` - Claim the daily reward
- `/settings` - Set notification preferences and profile visibility
- `/deleteaccount` - Request permanent player-data deletion with an explicit confirmation step
- `/export` - Download your player data as JSON
- `/group register|info|members|missions|claim|raid|ban|unban|top` - Telegram group progression and raids
- `/admin stats|player|coins|announce` - Restricted bot administration
- `/friend request|accept|decline|list|remove` - Friend requests and friend list (request by replying to a player in a group)
- `/duel` - Challenge a player by replying to their message in a group
- `/pvprank` - PvP rankings
- `/party create|invite|accept|decline|info|leave|disband` - Four-player party management
- `/friend request|accept|decline|list|remove` - Friend system (request by replying to a player in a group)
- `/guild create|join|leave|info|top|disband` - Guild management
- `/guild invite|accept|decline` - Guild invitations
- `/guild role player_id officer|member` - Leader-controlled guild roles
- `/guild announce MESSAGE` - Guild announcement broadcast
- `/guild missions|claim ID` - Daily guild missions and XP
- `/guild raid start|status|attack` - Shared guild boss raids
- `/guild war challenge|accept|decline|status` - Best-of-five guild wars scored by PvP duels
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
node --test cloudflare/worker.test.mjs
```

The repository includes a GitHub Actions workflow configured to compile Python, import the bot module and run the automated test suite on pushes and pull requests to `main`.

## Remaining development
The Mini App now includes obstacle collision, a solid NPC with ten region-specific dialogue lines, multiple level-appropriate monster encounters and selectable battle targets. Remaining work includes larger multi-zone maps with portals and landmarks, polished frame-by-frame sprite sheets, richer NPC quests and branching dialogue, deeper story cinematics, sound, co-op exploration/battles and team boss raids, guild invites, equipment trading, deployment hardening, balance testing and live Telegram testing. The 100-monster narrative catalogue also needs a dedicated editorial pass so each entry feels individually authored rather than template-like.

The default SQLite database is stored in `peak_adventure.db`. Use a persistent disk on hosts with ephemeral filesystems, or move to PostgreSQL before a larger public launch.

Never commit your real `.env` or bot token.
