# The Peak Adventure 🎮

A Telegram turn-based dark-fantasy RPG bot. This project replaces the original music-bot starter code.

## Current bot features
- Telegram player profiles with four permanent hero classes: Knight, Mage, Archer and Berserker
- 100-level monster catalogue, 10 boss milestones and the original power curve
- 100 distinct monster names, signature moves, unique-power labels and connected story entries
- Monster combat traits: regeneration, fury, speed, armor and drain
- Turn-based combat with attack, class skill, potions and escape
- Elemental matchups, weapon attack bonuses and armor defence bonuses
- Equipment shop with level-gated weapons, armor and potions
- Persistent story quests with one-time rewards
- Daily rewards with a UTC 24-hour claim cooldown
- One-time boss clears, player XP/levels, coins, HP and leaderboard
- SQLite persistence and automated catalogue/game-rule tests

## Tech stack
- Python 3.11+
- aiogram 3
- aiosqlite / SQLite
- python-dotenv
- JSON game data

## Setup
1. Create a Telegram bot with @BotFather.
2. Copy `.env.example` to `.env` and set your real `BOT_TOKEN`.
3. Install Python 3.11+.
4. Install dependencies and start the bot:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

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
- `/daily` - Claim the daily reward
- `/leaderboard` - Top adventurers
- `/help` - Show commands

## Tests
Run locally:

```bash
python -m compileall -q .
python -m unittest discover -s tests -v
```

GitHub Actions runs these checks on pushes and pull requests to `main`.

## Not yet implemented
The bot is not yet the full graphical 2D game. The Phaser 3 Telegram Mini App, real-time map movement, hand-drawn-style character/monster sprite sheets, multiplayer parties/PvP/guilds/trading, expanded quest chapters, sound/animation assets, deployment configuration and live Telegram testing remain future phases.

Never commit your real `.env` or bot token.
