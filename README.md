# The Peak Adventure 🎮

A Telegram turn-based dark-fantasy RPG with a Phaser 3 Mini App. This project replaces the original music-bot starter code.

## Current features
- Telegram player profiles with four permanent hero classes: Knight, Mage, Archer and Berserker
- 100-level monster catalogue, 10 boss milestones and the original power curve
- 100 distinct monster names, signature moves, unique-power labels and connected story entries
- Monster combat traits: regeneration, fury, speed, armor and drain
- Turn-based combat with attack, class skill, potions and escape
- Elemental matchups, weapon attack bonuses and armor defence bonuses
- Equipment shop with level-gated weapons, armor and potions
- Persistent story quests and achievements with one-time rewards
- Daily rewards with a UTC 24-hour claim cooldown
- One-time boss clears, player XP/levels, coins, HP and leaderboard
- Phaser 3 Mini App with ten world biomes, custom-drawn 2D scenery, keyboard/touch movement and in-app battle controls
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
- `/leaderboard` - Top adventurers
- `/help` - Show commands

## Tests
Run locally:

```bash
python -m compileall -q .
python -m unittest discover -s tests -v
```

The repository includes a GitHub Actions workflow configured to run these checks on pushes and pull requests to `main`.

## Remaining development
The Mini App currently provides custom-drawn world scenes, hero movement and turn-based battles inside the Mini App. Polished frame-by-frame hand-drawn sprite sheets, larger explorable maps with collision and NPCs, multiplayer parties/PvP/guilds/trading, deeper story cinematics, sound, deployment hardening and live Telegram testing remain to be completed.

The default SQLite database is stored in `peak_adventure.db`. Use a persistent disk on hosts with ephemeral filesystems, or move to PostgreSQL before a larger public launch.

Never commit your real `.env` or bot token.
