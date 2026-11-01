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
- Player trading for coins and health potions with dual confirmation
- Phaser 3 Mini App with ten world biomes, custom-drawn 2D scenery, keyboard/touch movement, obstacle collision and a solid Wanderer NPC
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
3. Set `BOT_TOKEN` and `WEBAPP_URL`. The Mini App URL must be a public HTTPS address pointing to this server.
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

## Deploy with Render
1. Push this repository to GitHub and create a new Blueprint in Render.
2. Select this repository so Render reads `render.yaml`.
3. Set `BOT_TOKEN` to the token from @BotFather.
4. Set `WEBAPP_URL` to the public HTTPS URL Render assigns to the service (for example, `https://your-service.onrender.com`).
5. If Telegram asks for a Web App domain, set the service hostname with BotFather.
6. Deploy. The blueprint includes a persistent disk mounted at `/data` so the SQLite player database survives restarts.

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
- `/monster <level>` - Inspect a monster
- `/bestiary` - View discovered monsters
- `/quests` - View story quests and claimable rewards
- `/claimquest <quest_id>` - Claim a completed quest
- `/achievements` - View achievements
- `/claimachievement <achievement_id>` - Claim an achievement
- `/daily` - Claim the daily reward
- `/duel` - Challenge a player by replying to their message in a group
- `/pvprank` - PvP rankings
- `/guild create|join|leave|info|top|disband` - Guild management
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
```

The repository includes a GitHub Actions workflow configured to compile Python, import the bot module and run the automated test suite on pushes and pull requests to `main`.

## Remaining development
The Mini App now includes obstacle collision, a solid NPC with ten region-specific dialogue lines, multiple level-appropriate monster encounters and selectable battle targets. Remaining work includes larger scrolling maps, polished frame-by-frame sprite sheets, richer NPC quests and branching dialogue, deeper story cinematics, sound, co-op parties, guild invites, equipment trading, deployment hardening, balance testing and live Telegram testing. The 100-monster narrative catalogue also needs a dedicated editorial pass so each entry feels individually authored rather than template-like.

The default SQLite database is stored in `peak_adventure.db`. Use a persistent disk on hosts with ephemeral filesystems, or move to PostgreSQL before a larger public launch.

Never commit your real `.env` or bot token.
