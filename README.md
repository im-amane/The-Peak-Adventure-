# The Peak Adventure 🎮

Telegram turn-based fantasy RPG. This repository replaces the former music-bot starter project.

## Playable foundation
- Player profiles, XP, levels 1–100, HP, coins and victories
- Explore and encounter a 100-level monster roster
- Turn-based battles: attack, special skill, potion and escape
- Boss milestones at levels 10, 20, ... 100
- Inventory, healing, map, story overview and leaderboard
- SQLite persistence

## Stack
Python 3.11+, aiogram 3, aiosqlite/SQLite and JSON monster catalogue.

## Setup
1. Create a Telegram bot with @BotFather.
2. Copy .env.example to .env and set BOT_TOKEN.
3. Install Python 3.11+ and dependencies:

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python main.py

Windows activation: .venv\\Scripts\\activate.

## Commands
/start, /profile, /explore, /inventory, /heal, /map, /quests, /daily, /leaderboard, /help.

## Important
This is the first playable Telegram-bot foundation, not the final graphical 2D Mini App. Daily reward cooldown enforcement, persistent quest tracking, full narrative chapters, balanced boss phases, party battles, anti-cheat safeguards and automated tests are still future work. The Phaser 3 Mini App is a separate next phase.

Never commit your real .env or bot token.
