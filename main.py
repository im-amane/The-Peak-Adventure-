"""The Peak Adventure - Telegram turn-based RPG bot."""
import asyncio
from html import escape
import json
import logging
import os
import random
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv
from aiohttp import web
from aiogram.types import WebAppInfo

from game_rules import calculate_enemy_damage, choose_monster_tactic, class_evades, get_boss_phase, nearby_monster_levels, skill_cooldown_for_class, validate_monster_catalogue
from telegram_auth import validate_init_data
from friend_system import FriendError, init_friend_tables, list_friends, remove_friend, respond_to_friend_request, send_friend_request
from party_system import PartyError, create_party, disband_party, get_party_info, init_party_tables, invite_to_party, leave_party, respond_to_party_invite
from group_system import GroupError, attack_group_raid, award_group_xp, claim_group_mission, get_group_missions, get_group_profile, group_raid_status, init_group_tables, is_group_admin, is_group_banned, list_group_players, record_group_activity, record_group_player, register_group, set_group_admin, set_group_ban, start_group_raid, top_groups
from admin_tools import AdminError, adjust_player_coins, dashboard_stats, export_player_data, parse_admin_ids
from character_system import AppearanceError, get_appearance, init_character_tables, save_appearance

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))
DB_PATH = os.getenv("DATABASE_PATH", "peak_adventure.db")
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("PORT", os.getenv("WEB_PORT", "8080")))
WEB_DIR = Path(__file__).with_name("webapp")
MONSTERS = json.loads(Path(__file__).with_name("monsters.json").read_text(encoding="utf-8"))
validate_monster_catalogue(MONSTERS)
MONSTER_BY_LEVEL = {m["level"]: m for m in MONSTERS}
BOSS_LEVELS = {10, 20, 30, 40, 50, 60, 70, 80, 90, 100}
HERO_CLASSES = {
    "Knight": {"hp": 40, "attack": 8, "defense": 12, "speed": 0, "element": "Earth", "skill": "Shield Break"},
    "Mage": {"hp": 0, "attack": 18, "defense": 0, "speed": 3, "element": "Astral", "skill": "Arcane Nova"},
    "Archer": {"hp": 10, "attack": 12, "defense": 4, "speed": 10, "element": "Nature", "skill": "Piercing Volley"},
    "Berserker": {"hp": 25, "attack": 22, "defense": -3, "speed": 4, "element": "Fire", "skill": "Rage Cleave"},
}
SHOP_ITEMS = {
    "iron_sword": {"name": "Iron Sword", "type": "weapon", "cost": 40, "bonus": 8, "level": 2},
    "steel_sword": {"name": "Steel Sword", "type": "weapon", "cost": 150, "bonus": 20, "level": 5},
    "flame_sword": {"name": "Flame Sword", "type": "weapon", "cost": 450, "bonus": 45, "level": 15},
    "dragon_slayer": {"name": "Dragon Slayer", "type": "weapon", "cost": 1500, "bonus": 90, "level": 40},
    "leather_armor": {"name": "Leather Armor", "type": "armor", "cost": 30, "bonus": 5, "level": 2},
    "iron_armor": {"name": "Iron Armor", "type": "armor", "cost": 150, "bonus": 18, "level": 10},
    "frostguard_armor": {"name": "Frostguard Armor", "type": "armor", "cost": 500, "bonus": 35, "level": 25},
    "celestial_armor": {"name": "Celestial Armor", "type": "armor", "cost": 1400, "bonus": 60, "level": 60},
    "health_potion": {"name": "Health Potion", "type": "potion", "cost": 25, "bonus": 1, "level": 1},
}
QUESTS = [
    {"id": "first_steps", "title": "A Tiny Spark", "kind": "level", "target": 2, "coins": 40, "potions": 1, "description": "Reach hero level 2."},
    {"id": "first_hunt", "title": "First Blood", "kind": "wins", "target": 3, "coins": 60, "potions": 1, "description": "Win 3 monster battles."},
    {"id": "root_seal", "title": "Seal of Roots", "kind": "boss", "target": 10, "coins": 120, "potions": 2, "description": "Defeat the level 10 boss."},
    {"id": "desert_trail", "title": "Beyond the Dunes", "kind": "level", "target": 11, "coins": 100, "potions": 2, "description": "Reach hero level 11."},
    {"id": "ancient_seal", "title": "The Ancient Seal", "kind": "boss", "target": 20, "coins": 180, "potions": 2, "description": "Defeat the level 20 boss."},
    {"id": "storm_memory", "title": "Storm's Memory", "kind": "boss", "target": 30, "coins": 220, "potions": 2, "description": "Defeat the level 30 boss."},
    {"id": "hollow_kingdom", "title": "The Hollow Crown", "kind": "boss", "target": 40, "coins": 280, "potions": 3, "description": "Defeat the level 40 boss."},
    {"id": "ember_oath", "title": "Ember Oath", "kind": "boss", "target": 50, "coins": 350, "potions": 3, "description": "Defeat the level 50 boss."},
    {"id": "frostbound", "title": "Frostbound Promise", "kind": "boss", "target": 60, "coins": 420, "potions": 3, "description": "Defeat the level 60 boss."},
    {"id": "riftwalker", "title": "Riftwalker", "kind": "boss", "target": 70, "coins": 520, "potions": 3, "description": "Defeat the level 70 boss."},
    {"id": "celestial_truth", "title": "Celestial Truth", "kind": "boss", "target": 80, "coins": 650, "potions": 4, "description": "Defeat the level 80 boss."},
    {"id": "eternal_hour", "title": "The Eternal Hour", "kind": "boss", "target": 90, "coins": 800, "potions": 4, "description": "Defeat the level 90 boss."},
    {"id": "alpha_dream", "title": "The Alpha's Dream", "kind": "boss", "target": 100, "coins": 1200, "potions": 5, "description": "Defeat THE ALPHA GOD."},
]
ACHIEVEMENTS = [
    {"id": "first_blood", "title": "First Blood", "kind": "wins", "target": 1, "coins": 30, "potions": 0, "description": "Win your first battle."},
    {"id": "monster_hunter", "title": "Monster Hunter", "kind": "wins", "target": 10, "coins": 120, "potions": 1, "description": "Win 10 battles."},
    {"id": "boss_breaker", "title": "Boss Breaker", "kind": "bosses", "target": 1, "coins": 180, "potions": 1, "description": "Defeat your first boss."},
    {"id": "seal_keeper", "title": "Seal Keeper", "kind": "bosses", "target": 5, "coins": 500, "potions": 2, "description": "Defeat five bosses."},
    {"id": "halfway_hero", "title": "Halfway Hero", "kind": "level", "target": 50, "coins": 600, "potions": 2, "description": "Reach level 50."},
    {"id": "mythic_voyager", "title": "Mythic Voyager", "kind": "level", "target": 80, "coins": 1000, "potions": 3, "description": "Reach level 80."},
    {"id": "alpha_slayer", "title": "Alpha Slayer", "kind": "alpha", "target": 1, "coins": 2500, "potions": 5, "description": "Defeat THE ALPHA GOD."},
    {"id": "master_armorer", "title": "Master Armorer", "kind": "gear", "target": 1, "coins": 700, "potions": 2, "description": "Equip the strongest weapon and armor."},
]

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("peak-adventure")
dp = Dispatcher()
db: aiosqlite.Connection | None = None
db_lock = asyncio.Lock()
player_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


class DatabaseLockMiddleware:
    async def __call__(self, handler, event, data):
        async with db_lock:
            return await handler(event, data)


dp.update.outer_middleware(DatabaseLockMiddleware())


async def init_db():
    global db
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS players (
      user_id INTEGER PRIMARY KEY, username TEXT, level INTEGER NOT NULL DEFAULT 1,
      xp INTEGER NOT NULL DEFAULT 0, coins INTEGER NOT NULL DEFAULT 0,
      hp INTEGER NOT NULL DEFAULT 120, max_hp INTEGER NOT NULL DEFAULT 120,
      potions INTEGER NOT NULL DEFAULT 3, wins INTEGER NOT NULL DEFAULT 0,
      skill_cd INTEGER NOT NULL DEFAULT 0,
      hero_class TEXT NOT NULL DEFAULT 'Knight', class_selected INTEGER NOT NULL DEFAULT 0,
      weapon TEXT NOT NULL DEFAULT 'Rusty Sword', weapon_attack INTEGER NOT NULL DEFAULT 0,
      armor TEXT NOT NULL DEFAULT 'Traveler Clothes', armor_defense INTEGER NOT NULL DEFAULT 0,
      pvp_wins INTEGER NOT NULL DEFAULT 0, pvp_losses INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS battles (
      user_id INTEGER PRIMARY KEY, monster_level INTEGER NOT NULL,
      monster_hp INTEGER NOT NULL, message_id INTEGER,
      turn_count INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS daily_claims (
      user_id INTEGER PRIMARY KEY, claimed_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS boss_defeats (
      user_id INTEGER NOT NULL, monster_level INTEGER NOT NULL,
      defeated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id, monster_level)
    );
    CREATE TABLE IF NOT EXISTS monster_discoveries (
      user_id INTEGER NOT NULL, monster_level INTEGER NOT NULL,
      discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id, monster_level)
    );
    CREATE TABLE IF NOT EXISTS quest_progress (
      user_id INTEGER NOT NULL, quest_id TEXT NOT NULL,
      progress INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0,
      claimed INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(user_id, quest_id)
    );
    CREATE TABLE IF NOT EXISTS achievement_progress (
      user_id INTEGER NOT NULL, achievement_id TEXT NOT NULL,
      progress INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0,
      claimed INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(user_id, achievement_id)
    );
    CREATE TABLE IF NOT EXISTS duels (
      duel_id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,
      challenger_id INTEGER NOT NULL, opponent_id INTEGER NOT NULL,
      challenger_hp INTEGER NOT NULL, opponent_hp INTEGER NOT NULL,
      turn_user_id INTEGER, status TEXT NOT NULL DEFAULT 'pending',
      winner_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS guilds (
      guild_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
      leader_id INTEGER NOT NULL, guild_level INTEGER NOT NULL DEFAULT 1,
      guild_xp INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS guild_members (
      user_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL,
      role TEXT NOT NULL DEFAULT 'member', joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS trades (
      trade_id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,
      initiator_id INTEGER NOT NULL, partner_id INTEGER NOT NULL,
      initiator_coins INTEGER NOT NULL DEFAULT 0, initiator_potions INTEGER NOT NULL DEFAULT 0,
      partner_coins INTEGER NOT NULL DEFAULT 0, partner_potions INTEGER NOT NULL DEFAULT 0,
      initiator_confirmed INTEGER NOT NULL DEFAULT 0, partner_confirmed INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_players_leaderboard ON players(level DESC, wins DESC);
    """)
    migrations = [
        "ALTER TABLE battles ADD COLUMN turn_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE daily_claims ADD COLUMN claimed_at INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN hero_class TEXT NOT NULL DEFAULT 'Knight'",
        "ALTER TABLE players ADD COLUMN class_selected INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN weapon TEXT NOT NULL DEFAULT 'Rusty Sword'",
        "ALTER TABLE players ADD COLUMN weapon_attack INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN armor TEXT NOT NULL DEFAULT 'Traveler Clothes'",
        "ALTER TABLE players ADD COLUMN armor_defense INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN pvp_wins INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN pvp_losses INTEGER NOT NULL DEFAULT 0",
    ]
    for migration in migrations:
        try:
            await db.execute(migration)
        except aiosqlite.OperationalError:
            pass
    await db.commit()
    await init_friend_tables(db)
    await init_party_tables(db)
    await init_group_tables(db)
    await init_character_tables(db)


async def get_player(user_id: int, username: str | None = None):
    assert db is not None
    await db.execute("INSERT OR IGNORE INTO players(user_id, username) VALUES (?, ?)", (user_id, username or "Adventurer"))
    if username:
        await db.execute("UPDATE players SET username=? WHERE user_id=?", (username, user_id))
    await db.commit()
    cur = await db.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
    return await cur.fetchone()


def menu(include_webapp: bool = False):
    rows = [
        [InlineKeyboardButton(text="🗺️ Explore", callback_data="explore"),
         InlineKeyboardButton(text="👤 Profile", callback_data="profile")],
        [InlineKeyboardButton(text="🎒 Inventory", callback_data="inventory"),
         InlineKeyboardButton(text="📜 Quests", callback_data="quests")],
        [InlineKeyboardButton(text="🛒 Shop", callback_data="shop"),
         InlineKeyboardButton(text="🧙 Hero Class", callback_data="class_menu")],
        [InlineKeyboardButton(text="🏅 Achievements", callback_data="achievements"),
         InlineKeyboardButton(text="⚔️ PvP Rank", callback_data="pvprank")],
        [InlineKeyboardButton(text="👥 Friends", callback_data="friend_list"),
         InlineKeyboardButton(text="🛡️ Party", callback_data="party_info")],
        [InlineKeyboardButton(text="🏰 Guild", callback_data="guild_info")],
        [InlineKeyboardButton(text="🎁 Daily Reward", callback_data="daily"),
         InlineKeyboardButton(text="🏆 Leaderboard", callback_data="leaderboard")],
    ]
    if WEBAPP_URL and include_webapp:
        rows.insert(0, [InlineKeyboardButton(text="🎮 Open 2D Adventure", web_app=WebAppInfo(url=WEBAPP_URL))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def class_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡️ Knight", callback_data="class:Knight"),
         InlineKeyboardButton(text="🔮 Mage", callback_data="class:Mage")],
        [InlineKeyboardButton(text="🏹 Archer", callback_data="class:Archer"),
         InlineKeyboardButton(text="🪓 Berserker", callback_data="class:Berserker")],
    ])


def shop_keyboard():
    rows = []
    for item_id, item in SHOP_ITEMS.items():
        rows.append([InlineKeyboardButton(
            text=f"{item['name']} · {item['cost']} coins · Lv.{item['level']}",
            callback_data=f"buy:{item_id}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def battle_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Attack", callback_data="battle:attack"),
         InlineKeyboardButton(text="🔥 Special Skill", callback_data="battle:skill")],
        [InlineKeyboardButton(text="🧪 Potion", callback_data="battle:potion"),
         InlineKeyboardButton(text="🏃 Escape", callback_data="battle:flee")],
    ])


def xp_needed(level: int) -> int:
    return level * 100


async def player_text(p):
    cur = await db.execute(
        "SELECT g.name, g.guild_level FROM guild_members gm JOIN guilds g ON g.guild_id=gm.guild_id WHERE gm.user_id=?",
        (p["user_id"],),
    )
    guild = await cur.fetchone()
    guild_line = f"🏰 Guild: <b>{escape(guild['name'])}</b> · Lv.{guild['guild_level']}\n" if guild else "🏰 Guild: None\n"
    return (f"👤 <b>{escape(p['username'] or 'Adventurer')}</b>\n"
            f"{guild_line}"
            f"🧙 Class: <b>{p['hero_class']}</b>\n"
            f"⚔️ Weapon: <b>{p['weapon']}</b> (+{p['weapon_attack']} ATK)\n"
            f"🛡️ Armor: <b>{p['armor']}</b> (+{p['armor_defense']} DEF)\n"
            f"⭐ Level: <b>{p['level']}/100</b>\n"
            f"✨ XP: <b>{p['xp']}/{xp_needed(p['level'])}</b>\n"
            f"❤️ HP: <b>{p['hp']}/{p['max_hp']}</b>\n"
            f"🪙 Coins: <b>{p['coins']}</b>\n"
            f"🏆 Victories: <b>{p['wins']}</b>\n"
            f"⚔️ PvP Record: <b>{p['pvp_wins']}W / {p['pvp_losses']}L</b>")


async def send_battle(target, user_id: int, intro: str = "", edit: bool = False):
    assert db is not None
    cur = await db.execute("SELECT * FROM battles WHERE user_id=?", (user_id,))
    battle = await cur.fetchone()
    p = await get_player(user_id)
    if not battle:
        return
    m = MONSTER_BY_LEVEL[battle["monster_level"]]
    text = (f"{intro}\n\n" if intro else "") + (
        f"⚔️ <b>ENCOUNTER: {m['name']}</b>\n"
        f"🏷️ Monster level: {m['level']} {'👑 BOSS' if m['boss'] else ''}\n"
        f"❤️ Enemy HP: <b>{max(0, battle['monster_hp'])}/{m['hp']}</b>\n"
        f"🧙 Your HP: <b>{p['hp']}/{p['max_hp']}</b>\n\n"
        f"<i>{m['story']}</i>\n"
        f"✨ Special: {m['special_move']}\n"
        f"🧬 Trait: {m['unique_power']} ({m['trait_effect']})\n"
        f"🎯 Weakness: {m['weakness']}\n"
        f"⚖️ Advantage: {m['advantage']}\n"
        f"⚠️ Disadvantage: {m['disadvantage']}"
    )
    if edit:
        await target.edit_text(text, reply_markup=battle_keyboard())
    else:
        sent = await target.answer(text, reply_markup=battle_keyboard())
        await db.execute("UPDATE battles SET message_id=? WHERE user_id=?", (sent.message_id, user_id))
        await db.commit()


async def _start_battle_unlocked(user_id: int, username: str | None, send_target):
    assert db is not None
    p = await get_player(user_id, username)
    cur = await db.execute("SELECT 1 FROM battles WHERE user_id=?", (user_id,))
    if await cur.fetchone():
        await send_target.answer("⚔️ Tumhari battle pehle se chal rahi hai. Uske buttons use karo.")
        return
    if not p["class_selected"]:
        await send_target.answer("🧙 Choose your hero class before entering the adventure.", reply_markup=class_keyboard())
        return
    if p["hp"] <= 0:
        await send_target.answer("💀 Your hero is exhausted. Use /heal before exploring again.")
        return
    level = p["level"]
    boss_defeated = False
    if level in BOSS_LEVELS:
        cur = await db.execute("SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?", (user_id, level))
        boss_defeated = await cur.fetchone() is not None
    monster_level = random.choice(nearby_monster_levels(level, boss_defeated))
    m = MONSTER_BY_LEVEL[monster_level]
    await db.execute("UPDATE players SET skill_cd=0 WHERE user_id=?", (user_id,))
    await db.execute("INSERT INTO battles(user_id, monster_level, monster_hp) VALUES (?, ?, ?)",
                     (user_id, monster_level, m["hp"]))
    await db.execute(
        "INSERT OR IGNORE INTO monster_discoveries(user_id, monster_level) VALUES (?, ?)",
        (user_id, monster_level),
    )
    await db.commit()
    await send_battle(send_target, user_id, "🌲 <b>You enter the wilds...</b>")


async def start_battle(user_id: int, username: str | None, send_target):
    async with player_locks[user_id]:
        await _start_battle_unlocked(user_id, username, send_target)


async def claim_daily_reward(user_id: int) -> bool:
    assert db is not None
    async with player_locks[user_id]:
        now = int(datetime.now(timezone.utc).timestamp())
        cur = await db.execute("SELECT claimed_at FROM daily_claims WHERE user_id=?", (user_id,))
        previous = await cur.fetchone()
        if previous and now - previous["claimed_at"] < 86400:
            return False
        await db.execute(
            "INSERT INTO daily_claims(user_id, claimed_at) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET claimed_at=excluded.claimed_at",
            (user_id, now),
        )
        await db.execute("UPDATE players SET coins=coins+50, potions=potions+1 WHERE user_id=?", (user_id,))
        await db.commit()
        return True


async def refresh_quest_progress(user_id: int):
    assert db is not None
    p = await get_player(user_id)
    for quest in QUESTS:
        if quest["kind"] == "level":
            progress = p["level"]
        elif quest["kind"] == "wins":
            progress = p["wins"]
        else:
            cur = await db.execute(
                "SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?",
                (user_id, quest["target"]),
            )
            progress = quest["target"] if await cur.fetchone() else 0
        await db.execute(
            "INSERT INTO quest_progress(user_id, quest_id, progress, completed) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, quest_id) DO UPDATE SET progress=excluded.progress, "
            "completed=MAX(quest_progress.completed, excluded.completed)",
            (user_id, quest["id"], progress, int(progress >= quest["target"])),
        )
    await db.commit()


async def quest_view(user_id: int):
    await refresh_quest_progress(user_id)
    cur = await db.execute("SELECT * FROM quest_progress WHERE user_id=?", (user_id,))
    states = {row["quest_id"]: row for row in await cur.fetchall()}
    lines = ["📜 <b>Story Quests</b>"]
    buttons = []
    for quest in QUESTS:
        state = states[quest["id"]]
        if state["claimed"]:
            status = "🎁 Claimed"
        elif state["completed"]:
            status = "✅ Ready to claim"
            buttons.append([InlineKeyboardButton(text=f"Claim: {quest['title']}", callback_data=f"questclaim:{quest['id']}")])
        else:
            status = f"🔒 {min(state['progress'], quest['target'])}/{quest['target']}"
        lines.append(f"\n<b>{quest['title']}</b> · {status}\n{quest['description']}")
    markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    return "\n".join(lines), markup


async def claim_quest_reward(user_id: int, quest_id: str) -> str:
    assert db is not None
    quest = next((q for q in QUESTS if q["id"] == quest_id), None)
    if not quest:
        return "That quest does not exist."
    async with player_locks[user_id]:
        await refresh_quest_progress(user_id)
        cur = await db.execute(
            "SELECT completed, claimed FROM quest_progress WHERE user_id=? AND quest_id=?",
            (user_id, quest_id),
        )
        state = await cur.fetchone()
        if not state or not state["completed"]:
            return "This quest is not complete yet."
        if state["claimed"]:
            return "You have already claimed this quest reward."
        await db.execute(
            "UPDATE players SET coins=coins+?, potions=potions+? WHERE user_id=?",
            (quest["coins"], quest["potions"], user_id),
        )
        await db.execute(
            "UPDATE quest_progress SET claimed=1 WHERE user_id=? AND quest_id=?",
            (user_id, quest_id),
        )
        await db.commit()
    return f"🎁 <b>{quest['title']}</b> reward claimed: +{quest['coins']} coins and +{quest['potions']} potions."


async def refresh_achievement_progress(user_id: int):
    assert db is not None
    p = await get_player(user_id)
    cur = await db.execute("SELECT COUNT(*) AS total FROM boss_defeats WHERE user_id=?", (user_id,))
    boss_count = (await cur.fetchone())["total"]
    cur = await db.execute("SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=100", (user_id,))
    alpha_defeated = await cur.fetchone() is not None
    for achievement in ACHIEVEMENTS:
        kind = achievement["kind"]
        if kind == "wins":
            progress = p["wins"]
        elif kind == "bosses":
            progress = boss_count
        elif kind == "level":
            progress = p["level"]
        elif kind == "alpha":
            progress = int(alpha_defeated)
        else:
            progress = int(p["weapon_attack"] >= 90 and p["armor_defense"] >= 60)
        await db.execute(
            "INSERT INTO achievement_progress(user_id, achievement_id, progress, completed) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, achievement_id) DO UPDATE SET progress=excluded.progress, "
            "completed=MAX(achievement_progress.completed, excluded.completed)",
            (user_id, achievement["id"], progress, int(progress >= achievement["target"])),
        )
    await db.commit()


async def achievement_view(user_id: int):
    await refresh_achievement_progress(user_id)
    cur = await db.execute("SELECT * FROM achievement_progress WHERE user_id=?", (user_id,))
    states = {row["achievement_id"]: row for row in await cur.fetchall()}
    lines = ["🏅 <b>Achievements</b>"]
    buttons = []
    for achievement in ACHIEVEMENTS:
        state = states[achievement["id"]]
        if state["claimed"]:
            status = "🎁 Claimed"
        elif state["completed"]:
            status = "✅ Complete · reward ready"
            buttons.append([InlineKeyboardButton(
                text=f"Claim: {achievement['title']}",
                callback_data=f"achclaim:{achievement['id']}",
            )])
        else:
            status = f"🔒 {min(state['progress'], achievement['target'])}/{achievement['target']}"
        lines.append(f"\n<b>{achievement['title']}</b> · {status}\n{achievement['description']}")
    markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    return "\n".join(lines), markup


async def claim_achievement_reward(user_id: int, achievement_id: str) -> str:
    assert db is not None
    achievement = next((a for a in ACHIEVEMENTS if a["id"] == achievement_id), None)
    if not achievement:
        return "That achievement does not exist."
    async with player_locks[user_id]:
        await refresh_achievement_progress(user_id)
        cur = await db.execute(
            "SELECT completed, claimed FROM achievement_progress WHERE user_id=? AND achievement_id=?",
            (user_id, achievement_id),
        )
        state = await cur.fetchone()
        if not state or not state["completed"]:
            return "This achievement is not complete yet."
        if state["claimed"]:
            return "You have already claimed this achievement reward."
        await db.execute(
            "UPDATE players SET coins=coins+?, potions=potions+? WHERE user_id=?",
            (achievement["coins"], achievement["potions"], user_id),
        )
        await db.execute(
            "UPDATE achievement_progress SET claimed=1 WHERE user_id=? AND achievement_id=?",
            (user_id, achievement_id),
        )
        await db.commit()
    return f"🏅 <b>{achievement['title']}</b> reward claimed: +{achievement['coins']} coins and +{achievement['potions']} potions."


async def finish_battle(user_id: int, won: bool, escaped: bool = False):
    assert db is not None
    cur = await db.execute("SELECT * FROM battles WHERE user_id=?", (user_id,))
    b = await cur.fetchone()
    if not b:
        return None
    m = MONSTER_BY_LEVEL[b["monster_level"]]
    await db.execute("DELETE FROM battles WHERE user_id=?", (user_id,))
    if escaped:
        await db.commit()
        return "🏃 You escaped. The wilderness is still waiting."
    if not won:
        await db.execute("UPDATE players SET hp=0 WHERE user_id=?", (user_id,))
        await db.commit()
        return "💀 You were defeated and returned to camp. Your HP is 0. Use /heal to recover before exploring again."
    p = await get_player(user_id)
    reward_xp = 35 + m["level"] * 18 + (m["level"] * 30 if m["boss"] else 0)
    reward_coins = 15 + m["level"] * 7 + (m["level"] * 25 if m["boss"] else 0)
    new_xp, new_level = p["xp"] + reward_xp, p["level"]
    while new_level < 100 and new_xp >= xp_needed(new_level):
        new_xp -= xp_needed(new_level)
        new_level += 1
    if new_level >= 100:
        new_level = 100
        new_xp = 0
    class_hp_bonus = HERO_CLASSES.get(p["hero_class"], HERO_CLASSES["Knight"])["hp"]
    new_max = 120 + (new_level - 1) * 20 + class_hp_bonus
    await db.execute("""UPDATE players SET xp=?, level=?, coins=coins+?, wins=wins+1,
        max_hp=?, hp=min(?, ?) WHERE user_id=?""",
        (new_xp, new_level, reward_coins, new_max, p["hp"] + 25, new_max, user_id))
    if m["boss"]:
        await db.execute("INSERT OR IGNORE INTO boss_defeats(user_id, monster_level) VALUES (?, ?)", (user_id, m["level"]))
    cur = await db.execute("SELECT guild_id FROM guild_members WHERE user_id=?", (user_id,))
    membership = await cur.fetchone()
    if membership:
        cur = await db.execute("SELECT guild_level, guild_xp FROM guilds WHERE guild_id=?", (membership["guild_id"],))
        guild = await cur.fetchone()
        if guild:
            guild_level, guild_xp = guild["guild_level"], guild["guild_xp"] + reward_xp
            while guild_level < 100 and guild_xp >= guild_level * 500:
                guild_xp -= guild_level * 500
                guild_level += 1
            await db.execute(
                "UPDATE guilds SET guild_level=?, guild_xp=? WHERE guild_id=?",
                (guild_level, guild_xp, membership["guild_id"]),
            )
    await db.commit()
    await refresh_quest_progress(user_id)
    level_note = f"\n🌟 LEVEL UP! You reached level {new_level}." if new_level > p["level"] else ""
    boss_note = "\n👑 Boss seal broken! The next region is now within reach." if m["boss"] else ""
    return f"🏆 <b>Victory!</b> {m['name']} defeated.\n✨ +{reward_xp} XP\n🪙 +{reward_coins} coins{level_note}{boss_note}"


@dp.message(F.web_app_data)
async def webapp_data(message: Message):
    try:
        payload = json.loads(message.web_app_data.data)
    except (TypeError, json.JSONDecodeError):
        await message.answer("The game sent an invalid action.")
        return
    if payload.get("action") == "explore":
        await start_battle(message.from_user.id, message.from_user.username, message)
    else:
        await message.answer("Unknown Mini App action.")


def duel_keyboard(duel_id: int, invite: bool = False):
    if invite:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⚔️ Accept Duel", callback_data=f"duel_accept:{duel_id}"),
            InlineKeyboardButton(text="✋ Decline", callback_data=f"duel_decline:{duel_id}"),
        ]])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Attack", callback_data=f"duel_action:attack:{duel_id}"),
         InlineKeyboardButton(text="🔥 Skill", callback_data=f"duel_action:skill:{duel_id}")],
        [InlineKeyboardButton(text="🏳️ Surrender", callback_data=f"duel_action:surrender:{duel_id}")],
    ])


async def duel_text(duel):
    challenger = await get_player(duel["challenger_id"])
    opponent = await get_player(duel["opponent_id"])
    turn = await get_player(duel["turn_user_id"]) if duel["status"] == "active" and duel["turn_user_id"] else None
    status = "⚔️ ACTIVE DUEL" if duel["status"] == "active" else "🏆 DUEL FINISHED"
    lines = [
        f"<b>{status}</b>",
        f"🛡️ {escape(challenger['username'] or 'Challenger')} · Lv.{challenger['level']} · ❤️ {duel['challenger_hp']}/{challenger['max_hp']}",
        f"⚔️ {escape(opponent['username'] or 'Opponent')} · Lv.{opponent['level']} · ❤️ {duel['opponent_hp']}/{opponent['max_hp']}",
    ]
    if turn:
        lines.append(f"\n⏳ Turn: <b>{escape(turn['username'] or 'Adventurer')}</b>")
    if duel["winner_id"]:
        winner = await get_player(duel["winner_id"])
        lines.append(f"\n🏆 Winner: <b>{escape(winner['username'] or 'Adventurer')}</b>")
    return "\n".join(lines)


def trade_keyboard(trade_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🤝 Accept Trade", callback_data=f"trade_accept:{trade_id}"),
        InlineKeyboardButton(text="✋ Decline", callback_data=f"trade_decline:{trade_id}"),
    ]])


async def trade_summary(trade):
    initiator = await get_player(trade["initiator_id"])
    partner = await get_player(trade["partner_id"])
    return (
        f"🤝 <b>Trade #{trade['trade_id']}</b> · {trade['status'].upper()}\n"
        f"<b>{escape(initiator['username'] or 'Player 1')}</b> offers: "
        f"{trade['initiator_coins']} coins, {trade['initiator_potions']} potions\n"
        f"<b>{escape(partner['username'] or 'Player 2')}</b> offers: "
        f"{trade['partner_coins']} coins, {trade['partner_potions']} potions\n"
        f"Confirmations: {'✅' if trade['initiator_confirmed'] else '⌛'} / "
        f"{'✅' if trade['partner_confirmed'] else '⌛'}"
    )


@dp.message(Command("trade"))
async def create_trade(message: Message):
    if message.chat.type not in {"group", "supergroup"} or not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("Reply to another player's message in a group, then send /trade.")
        return
    initiator_id = message.from_user.id
    partner_id = message.reply_to_message.from_user.id
    if initiator_id == partner_id or message.reply_to_message.from_user.is_bot:
        await message.answer("Choose another human player.")
        return
    initiator = await get_player(initiator_id, message.from_user.username or message.from_user.full_name)
    partner = await get_player(partner_id, message.reply_to_message.from_user.username or message.reply_to_message.from_user.full_name)
    if not initiator["class_selected"] or not partner["class_selected"]:
        await message.answer("Both players must register with /start and choose a class in the bot's private chat.")
        return
    cur = await db.execute(
        "SELECT 1 FROM trades WHERE status IN ('pending', 'open') "
        "AND (initiator_id IN (?, ?) OR partner_id IN (?, ?))",
        (initiator_id, partner_id, initiator_id, partner_id),
    )
    if await cur.fetchone():
        await message.answer("One of these players already has a pending or open trade.")
        return
    cur = await db.execute(
        "INSERT INTO trades(chat_id, initiator_id, partner_id, status) VALUES (?, ?, ?, 'pending')",
        (message.chat.id, initiator_id, partner_id),
    )
    await db.commit()
    trade_id = cur.lastrowid
    await message.answer(
        f"🤝 <b>Trade invitation #{trade_id}</b>\n"
        f"{escape(initiator['username'] or 'Player 1')} wants to trade with "
        f"{escape(partner['username'] or 'Player 2')}.",
        reply_markup=trade_keyboard(trade_id),
    )


@dp.callback_query(F.data.startswith("trade_accept:"))
async def accept_trade(call: CallbackQuery):
    trade_id = int(call.data.split(":", 1)[1])
    cur = await db.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,))
    trade = await cur.fetchone()
    if not trade or trade["status"] != "pending":
        await call.answer("This trade invitation is no longer active.", show_alert=True)
        return
    if call.from_user.id != trade["partner_id"]:
        await call.answer("Only the invited player can accept.", show_alert=True)
        return
    await call.answer()
    await db.execute("UPDATE trades SET status='open' WHERE trade_id=?", (trade_id,))
    await db.commit()
    cur = await db.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,))
    trade = await cur.fetchone()
    await call.message.edit_text(
        (await trade_summary(trade)) + "\n\nUse <code>/offer ID COINS POTIONS</code> to set your offer.",
    )


@dp.callback_query(F.data.startswith("trade_decline:"))
async def decline_trade(call: CallbackQuery):
    trade_id = int(call.data.split(":", 1)[1])
    cur = await db.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,))
    trade = await cur.fetchone()
    if not trade or trade["status"] != "pending":
        await call.answer("This trade invitation is no longer active.", show_alert=True)
        return
    if call.from_user.id != trade["partner_id"]:
        await call.answer("Only the invited player can decline.", show_alert=True)
        return
    await call.answer()
    await db.execute("UPDATE trades SET status='declined' WHERE trade_id=?", (trade_id,))
    await db.commit()
    await call.message.edit_text("✋ Trade declined.")


@dp.message(Command("offer"))
async def set_trade_offer(message: Message):
    if len(message.command) != 4 or not all(part.isdigit() for part in message.command[1:]):
        await message.answer("Usage: <code>/offer trade_id coins potions</code>.")
        return
    trade_id, coins, potions = map(int, message.command[1:])
    cur = await db.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,))
    trade = await cur.fetchone()
    if not trade or trade["status"] != "open":
        await message.answer("That trade is not open.")
        return
    user_id = message.from_user.id
    if user_id not in {trade["initiator_id"], trade["partner_id"]}:
        await message.answer("You are not part of this trade.")
        return
    p = await get_player(user_id, message.from_user.username)
    if coins > p["coins"] or potions > p["potions"]:
        await message.answer("Your offer exceeds your current coins or potions.")
        return
    if user_id == trade["initiator_id"]:
        await db.execute(
            "UPDATE trades SET initiator_coins=?, initiator_potions=?, initiator_confirmed=0, partner_confirmed=0 WHERE trade_id=?",
            (coins, potions, trade_id),
        )
    else:
        await db.execute(
            "UPDATE trades SET partner_coins=?, partner_potions=?, initiator_confirmed=0, partner_confirmed=0 WHERE trade_id=?",
            (coins, potions, trade_id),
        )
    await db.commit()
    cur = await db.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,))
    trade = await cur.fetchone()
    await message.answer((await trade_summary(trade)) + "\nBoth players must confirm with /confirmtrade ID.")


@dp.message(Command("confirmtrade"))
async def confirm_trade(message: Message):
    if len(message.command) != 2 or not message.command[1].isdigit():
        await message.answer("Usage: <code>/confirmtrade trade_id</code>.")
        return
    trade_id = int(message.command[1])
    cur = await db.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,))
    trade = await cur.fetchone()
    if not trade or trade["status"] != "open":
        await message.answer("That trade is not open.")
        return
    user_id = message.from_user.id
    if user_id == trade["initiator_id"]:
        await db.execute("UPDATE trades SET initiator_confirmed=1 WHERE trade_id=?", (trade_id,))
    elif user_id == trade["partner_id"]:
        await db.execute("UPDATE trades SET partner_confirmed=1 WHERE trade_id=?", (trade_id,))
    else:
        await message.answer("You are not part of this trade.")
        return
    await db.commit()
    cur = await db.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,))
    trade = await cur.fetchone()
    if trade["initiator_confirmed"] and trade["partner_confirmed"]:
        initiator = await get_player(trade["initiator_id"])
        partner = await get_player(trade["partner_id"])
        if (initiator["coins"] < trade["initiator_coins"] or initiator["potions"] < trade["initiator_potions"]
                or partner["coins"] < trade["partner_coins"] or partner["potions"] < trade["partner_potions"]):
            await db.execute(
                "UPDATE trades SET initiator_confirmed=0, partner_confirmed=0 WHERE trade_id=?",
                (trade_id,),
            )
            await db.commit()
            await message.answer("Trade paused: one player's balance changed. Update your offers and confirm again.")
            return
        await db.execute(
            "UPDATE players SET coins=coins-?+?, potions=potions-?+? WHERE user_id=?",
            (trade["initiator_coins"], trade["partner_coins"], trade["initiator_potions"], trade["partner_potions"], trade["initiator_id"]),
        )
        await db.execute(
            "UPDATE players SET coins=coins-?+?, potions=potions-?+? WHERE user_id=?",
            (trade["partner_coins"], trade["initiator_coins"], trade["partner_potions"], trade["initiator_potions"], trade["partner_id"]),
        )
        await db.execute("UPDATE trades SET status='completed' WHERE trade_id=?", (trade_id,))
        await db.commit()
        if trade["chat_id"] < 0:
            try:
                await record_group_activity(db,trade["chat_id"],"trade")
                await award_group_xp(db,trade["chat_id"],10)
            except GroupError:
                pass
        await message.answer(f"✅ Trade #{trade_id} completed. Items and coins have been exchanged.")
        return
    await message.answer((await trade_summary(trade)) + "\nWaiting for the other player to confirm.")


@dp.message(Command("canceltrade"))
async def cancel_trade(message: Message):
    if len(message.command) != 2 or not message.command[1].isdigit():
        await message.answer("Usage: <code>/canceltrade trade_id</code>.")
        return
    trade_id = int(message.command[1])
    cur = await db.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,))
    trade = await cur.fetchone()
    if not trade or trade["status"] not in {"pending", "open"}:
        await message.answer("That trade cannot be cancelled.")
        return
    if message.from_user.id not in {trade["initiator_id"], trade["partner_id"]}:
        await message.answer("You are not part of this trade.")
        return
    await db.execute("UPDATE trades SET status='cancelled' WHERE trade_id=?", (trade_id,))
    await db.commit()
    await message.answer(f"Trade #{trade_id} cancelled.")



def friend_request_keyboard(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💚 Accept", callback_data=f"friend_accept:{request_id}"),
        InlineKeyboardButton(text="✋ Decline", callback_data=f"friend_decline:{request_id}"),
    ]])



@dp.callback_query(F.data == "friend_list")
async def cb_friend_list(call: CallbackQuery):
    await call.answer()
    friends = await list_friends(db, call.from_user.id)
    if not friends:
        await call.message.answer("👥 Your friend list is empty. Reply to a player's group message with /friend request.")
        return
    lines = ["👥 <b>Your Friends</b>"]
    for index, friend in enumerate(friends, 1):
        lines.append(f"{index}. {escape(friend['username'] or 'Adventurer')} · Lv.{friend['level']} · ID <code>{friend['user_id']}</code>")
    await call.message.answer("\n".join(lines))


@dp.message(Command("friend"))
async def friend_command(message: Message):
    args = (message.text or "").split(maxsplit=2)
    action = args[1].lower() if len(args) > 1 else "list"
    user_id = message.from_user.id

    if action == "request":
        if message.chat.type not in {"group", "supergroup"} or not message.reply_to_message or not message.reply_to_message.from_user:
            await message.answer("Reply to another player's message in a group, then use /friend request.")
            return
        target = message.reply_to_message.from_user
        if target.is_bot:
            await message.answer("Bots cannot join your friend list.")
            return
        requester = await get_player(user_id, message.from_user.username or message.from_user.full_name)
        invited = await get_player(target.id, target.username or target.full_name)
        if not requester["class_selected"] or not invited["class_selected"]:
            await message.answer("Both players must register with /start and choose a class first.")
            return
        try:
            request_id = await send_friend_request(db, user_id, target.id)
        except FriendError as exc:
            await message.answer(escape(str(exc)))
            return
        await message.answer(
            f"🤝 <b>Friend request #{request_id}</b>\n"
            f"{escape(requester['username'] or 'Adventurer')} invited "
            f"{escape(invited['username'] or 'Adventurer')}.",
            reply_markup=friend_request_keyboard(request_id),
        )
        return

    if action in {"accept", "decline"}:
        if len(args) < 3 or not args[2].isdigit():
            await message.answer(f"Usage: <code>/friend {action} request_id</code>.")
            return
        request_id = int(args[2])
        try:
            await respond_to_friend_request(db, request_id, user_id, action == "accept")
        except FriendError as exc:
            await message.answer(escape(str(exc)))
            return
        await message.answer("💚 Friend request accepted." if action == "accept" else "Friend request declined.")
        return

    if action == "remove":
        if len(args) < 3 or not args[2].isdigit():
            await message.answer("Usage: <code>/friend remove player_id</code>.")
            return
        try:
            await remove_friend(db, user_id, int(args[2]))
        except FriendError as exc:
            await message.answer(escape(str(exc)))
            return
        await message.answer("Friend removed.")
        return

    if action == "list":
        friends = await list_friends(db, user_id)
        if not friends:
            await message.answer("👥 Your friend list is empty. Reply to a player's group message with /friend request.")
            return
        lines = ["👥 <b>Your Friends</b>"]
        for index, friend in enumerate(friends, 1):
            lines.append(f"{index}. {escape(friend['username'] or 'Adventurer')} · Lv.{friend['level']} · ID <code>{friend['user_id']}</code>")
        await message.answer("\n".join(lines))
        return

    await message.answer(
        "Friend commands:\n"
        "• Reply to a player in a group: <code>/friend request</code>\n"
        "• <code>/friend accept request_id</code>\n"
        "• <code>/friend decline request_id</code>\n"
        "• <code>/friend list</code>\n"
        "• <code>/friend remove player_id</code>"
    )


@dp.callback_query(F.data.startswith("friend_accept:"))
async def accept_friend_callback(call: CallbackQuery):
    try:
        request_id = int(call.data.split(":", 1)[1])
    except (TypeError, ValueError, IndexError):
        await call.answer("Invalid friend request.", show_alert=True)
        return
    try:
        await respond_to_friend_request(db, request_id, call.from_user.id, True)
    except FriendError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.answer("Friend added!")
    await call.message.edit_text(f"{call.message.text}\n\n💚 Friend request accepted.")


@dp.callback_query(F.data.startswith("friend_decline:"))
async def decline_friend_callback(call: CallbackQuery):
    try:
        request_id = int(call.data.split(":", 1)[1])
    except (TypeError, ValueError, IndexError):
        await call.answer("Invalid friend request.", show_alert=True)
        return
    try:
        await respond_to_friend_request(db, request_id, call.from_user.id, False)
    except FriendError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.answer("Request declined.")
    await call.message.edit_text(f"{call.message.text}\n\nFriend request declined.")



def party_invite_keyboard(invite_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛡️ Join Party", callback_data=f"party_accept:{invite_id}"),
        InlineKeyboardButton(text="✋ Decline", callback_data=f"party_decline:{invite_id}"),
    ]])


async def party_text(user_id: int):
    party, members = await get_party_info(db, user_id)
    lines = [
        f"🛡️ <b>Party #{party['party_id']}</b> · {party['member_count']}/4 players",
        f"👑 Leader: <code>{party['leader_id']}</code>",
    ]
    for member in members:
        icon = "👑" if member["user_id"] == party["leader_id"] else "•"
        lines.append(f"{icon} {escape(member['username'] or 'Adventurer')} · Lv.{member['level']}")
    return "\n".join(lines)



@dp.callback_query(F.data == "party_info")
async def cb_party_info(call: CallbackQuery):
    await call.answer()
    try:
        await call.message.answer(await party_text(call.from_user.id))
    except PartyError as exc:
        await call.message.answer(escape(str(exc)))


@dp.message(Command("party"))
async def party_command(message: Message):
    args = (message.text or "").split(maxsplit=1)
    action = args[1].lower() if len(args) > 1 else "info"
    user_id = message.from_user.id
    player = await get_player(user_id, message.from_user.username or message.from_user.full_name)
    if action in {"create", "invite", "accept"} and not player["class_selected"]:
        await message.answer("Choose your hero class with /class before joining a party.")
        return
    try:
        if action == "create":
            party_id = await create_party(db, user_id)
            await message.answer(f"🛡️ Party #{party_id} created. You are the leader.")
            return
        if action == "invite":
            if message.chat.type not in {"group", "supergroup"} or not message.reply_to_message or not message.reply_to_message.from_user:
                await message.answer("Reply to a player's group message, then use /party invite.")
                return
            target = message.reply_to_message.from_user
            if target.is_bot:
                await message.answer("Bots cannot join a party.")
                return
            party, _ = await get_party_info(db, user_id)
            requester = player
            invited = await get_player(target.id, target.username or target.full_name)
            if not requester["class_selected"] or not invited["class_selected"]:
                await message.answer("Both players must register with /start and choose a class first.")
                return
            invite_id = await invite_to_party(db, party["party_id"], user_id, target.id)
            await message.answer(
                f"🛡️ <b>Party invitation #{invite_id}</b>\n"
                f"{escape(requester['username'] or 'Leader')} invited "
                f"{escape(invited['username'] or 'Adventurer')}.",
                reply_markup=party_invite_keyboard(invite_id),
            )
            return
        if action in {"accept", "decline"}:
            parts = (message.text or "").split()
            if len(parts) != 3 or not parts[2].isdigit():
                await message.answer(f"Usage: <code>/party {action} invite_id</code>.")
                return
            await respond_to_party_invite(db, int(parts[2]), user_id, action == "accept")
            await message.answer("🛡️ You joined the party." if action == "accept" else "Party invitation declined.")
            return
        if action == "leave":
            new_leader = await leave_party(db, user_id)
            await message.answer(
                f"You left the party. Leadership passed to player <code>{new_leader}</code>."
                if new_leader else "You left the party."
            )
            return
        if action == "disband":
            party, _ = await get_party_info(db, user_id)
            await disband_party(db, party["party_id"], user_id)
            await message.answer("Party disbanded.")
            return
        if action == "info":
            await message.answer(await party_text(user_id))
            return
    except PartyError as exc:
        await message.answer(escape(str(exc)))
        return
    await message.answer(
        "Party commands: <code>/party create</code>, <code>/party invite</code> (reply to player), "
        "<code>/party accept ID</code>, <code>/party decline ID</code>, "
        "<code>/party info</code>, <code>/party leave</code>, <code>/party disband</code>."
    )


@dp.callback_query(F.data.startswith("party_accept:"))
async def accept_party_callback(call: CallbackQuery):
    try:
        invite_id = int(call.data.split(":", 1)[1])
    except (TypeError, ValueError, IndexError):
        await call.answer("Invalid party invitation.", show_alert=True)
        return
    try:
        await respond_to_party_invite(db, invite_id, call.from_user.id, True)
    except PartyError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.answer("Joined party!")
    await call.message.edit_text(f"{call.message.text}\n\n🛡️ Party invitation accepted.")


@dp.callback_query(F.data.startswith("party_decline:"))
async def decline_party_callback(call: CallbackQuery):
    try:
        invite_id = int(call.data.split(":", 1)[1])
    except (TypeError, ValueError, IndexError):
        await call.answer("Invalid party invitation.", show_alert=True)
        return
    try:
        await respond_to_party_invite(db, invite_id, call.from_user.id, False)
    except PartyError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.answer("Invitation declined.")
    await call.message.edit_text(f"{call.message.text}\n\nParty invitation declined.")



@dp.message(Command("group"))
async def group_command(message: Message):
    args=(message.text or "").split(maxsplit=2)
    action=args[1].lower() if len(args)>1 else "info"
    uid=message.from_user.id
    if action=="top":
        groups=await top_groups(db)
        lines=["🏆 <b>Adventure Group Rankings</b>"]
        for i,g in enumerate(groups,1): lines.append(f"{i}. {escape(g['title'])} · Lv.{g['group_level']} · XP {g['group_xp']}")
        await message.answer("\n".join(lines) if len(lines)>1 else "No registered groups yet.")
        return
    if message.chat.type not in {"group","supergroup"}:
        await message.answer("Use group commands inside a Telegram group. /group top works anywhere.")
        return
    cid=message.chat.id
    if await is_group_banned(db,cid,uid):
        await message.answer("⛔ You are blocked from this group's game features.")
        return
    if action=="register":
        try: admins=await message.bot.get_chat_administrators(cid)
        except Exception:
            await message.answer("I need access to the group's admin list to verify its owner and admins."); return
        actor=next((a for a in admins if a.user.id==uid),None)
        owner=next((a for a in admins if a.status=="creator"),None)
        if not actor or not owner:
            await message.answer("Only the Telegram group owner or an administrator can register it."); return
        try:
            await register_group(db,cid,message.chat.title or "Adventure Group",owner.user.id)
            for a in admins: await set_group_admin(db,cid,a.user.id,"owner" if a.status=="creator" else "admin")
        except GroupError as exc:
            await message.answer(escape(str(exc))); return
        await message.answer("✅ Group registered. Owner and admin roles verified."); return
    try: profile=await get_group_profile(db,cid)
    except GroupError as exc:
        await message.answer(escape(str(exc))); return
    player=await get_player(uid,message.from_user.username or message.from_user.full_name)
    if not player["class_selected"]:
        await message.answer("Choose a hero class with /class first."); return
    await record_group_player(db,cid,uid,player["username"],player["level"])
    if action=="info":
        await message.answer(f"🏰 <b>{escape(profile['title'])}</b>\nLevel {profile['group_level']} · XP {profile['group_xp']}/{profile['group_level']*500}\nPlayers: {profile['player_count']} · Verified admins: {profile['admin_count']}\nOwner ID: <code>{profile['owner_id']}</code>"); return
    if action=="members":
        rows=await list_group_players(db,cid); lines=[f"👥 <b>{escape(profile['title'])} roster</b>"]
        lines += [f"{i}. {escape(r['username'] or 'Adventurer')} · Lv.{r['player_level']}" for i,r in enumerate(rows,1)]
        await message.answer("\n".join(lines)); return
    if action=="missions":
        rows=await get_group_missions(db,cid); lines=["📜 <b>Daily group missions</b>"]
        for r in rows: lines.append(f"{'✅' if r['completed'] else '▫️'} {r['title']}: {r['progress']}/{r['target']} · {r['reward']} coins")
        await message.answer("\n".join(lines)); return
    if action=="claim":
        if len(args)<3: await message.answer("Usage: /group claim battles|boss|trades"); return
        try:
            coins,xp=await claim_group_mission(db,cid,uid,args[2].lower())
            await db.execute("UPDATE players SET coins=coins+? WHERE user_id=?",(coins,uid)); await db.commit()
            await message.answer(f"🎁 Claimed {coins} coins and {xp} group XP.")
        except GroupError as exc: await message.answer(escape(str(exc)))
        return
    if action=="raid":
        parts=(message.text or "").split(); sub=parts[2].lower() if len(parts)>2 else "status"
        if sub=="start":
            try:
                if not await is_group_admin(db,cid,uid): raise GroupError("Only verified group admins can start a raid.")
                level=min(100,max(10,((profile["group_level"]+9)//10)*10)); boss=MONSTER_BY_LEVEL[level]
                rid=await start_group_raid(db,cid,uid,level,boss["name"],boss["hp"]*5)
                await message.answer(f"🐉 <b>GROUP RAID #{rid}</b>\n{escape(boss['name'])} · Lv.{level} · {boss['hp']*5} HP\nUse /group raid attack.")
            except GroupError as exc: await message.answer(escape(str(exc)))
            return
        if sub=="attack":
            try:
                result=await attack_group_raid(db,cid,uid,max(1,player["level"]*5+player["weapon_attack"]))
                await record_group_activity(db,cid,"boss" if result["status"]=="won" else "battle")
                await award_group_xp(db,cid,100 if result["status"]=="won" else 10)
                await message.answer(f"⚔️ {escape(player['username'] or 'Adventurer')} deals {result['damage']} damage.\n{escape(result['boss_name'])}: {result['hp']}/{result['max_hp']} HP\n"+("🏆 <b>RAID CLEARED!</b>" if result["status"]=="won" else "The raid continues."))
            except GroupError as exc: await message.answer(escape(str(exc)))
            return
        raid=await group_raid_status(db,cid)
        await message.answer("No raid has been started." if not raid else f"🐉 {escape(raid['boss_name'])}: {raid['hp']}/{raid['max_hp']} HP · {raid['status'].upper()}"); return
    if action in {"ban","unban"}:
        if len(args)<3 or not args[2].isdigit():
            await message.answer("Usage: /group ban|unban player_id [reason]"); return
        try:
            await set_group_ban(db,cid,uid,int(args[2]),action=="ban"," ".join(args[3:]))
            await message.answer("Player blocked from group game features." if action=="ban" else "Player unblocked.")
        except GroupError as exc: await message.answer(escape(str(exc)))
        return
    await message.answer("Commands: /group register, info, members, missions, claim ID, raid start|status|attack, ban|unban ID, top.")

async def guild_summary(guild_id: int):
    cur = await db.execute(
        "SELECT g.*, COUNT(m.user_id) AS member_count FROM guilds g "
        "LEFT JOIN guild_members m ON m.guild_id=g.guild_id WHERE g.guild_id=? GROUP BY g.guild_id",
        (guild_id,),
    )
    guild = await cur.fetchone()
    if not guild:
        return None
    cur = await db.execute(
        "SELECT p.username, p.level, gm.role FROM guild_members gm "
        "JOIN players p ON p.user_id=gm.user_id WHERE gm.guild_id=? ORDER BY gm.role DESC, p.level DESC",
        (guild_id,),
    )
    members = await cur.fetchall()
    lines = [
        f"🏰 <b>{escape(guild['name'])}</b> · Guild Lv.{guild['guild_level']}",
        f"👥 Members: {guild['member_count']}/20 · Guild XP: {guild['guild_xp']}/{guild['guild_level'] * 500}",
    ]
    for member in members:
        icon = "👑" if member["role"] == "leader" else "•"
        lines.append(f"{icon} {escape(member['username'] or 'Adventurer')} · Lv.{member['level']}")
    return "\n".join(lines)


@dp.message(Command("guild"))
async def guild_command(message: Message):
    args = message.text.split(maxsplit=2)
    action = args[1].lower() if len(args) > 1 else "info"
    user_id = message.from_user.id
    p = await get_player(user_id, message.from_user.username or message.from_user.full_name)
    cur = await db.execute("SELECT guild_id, role FROM guild_members WHERE user_id=?", (user_id,))
    membership = await cur.fetchone()

    if action == "create":
        if membership:
            await message.answer("You are already in a guild. Leave it before creating another.")
            return
        if len(args) < 3:
            await message.answer("Usage: <code>/guild create Guild Name</code> (3–20 characters).")
            return
        name = " ".join(args[2].split()).strip()
        if not 3 <= len(name) <= 20 or not re.fullmatch(r"[A-Za-z0-9 _-]+", name):
            await message.answer("Guild names must be 3–20 characters and use letters, numbers, spaces, _ or -.")
            return
        debit = await db.execute("UPDATE players SET coins=coins-100 WHERE user_id=? AND coins>=100", (user_id,))
        if debit.rowcount == 0:
            await message.answer("Creating a guild costs 100 coins.")
            return
        try:
            cur = await db.execute("INSERT INTO guilds(name, leader_id) VALUES (?, ?)", (name, user_id))
        except aiosqlite.IntegrityError:
            await db.rollback()
            await message.answer("That guild name is already taken.")
            return
        guild_id = cur.lastrowid
        await db.execute("INSERT INTO guild_members(user_id, guild_id, role) VALUES (?, ?, 'leader')", (user_id, guild_id))
        await db.commit()
        await message.answer(f"🏰 Guild <b>{escape(name)}</b> created! Guild ID: <code>{guild_id}</code>.")
        return

    if action == "join":
        if membership:
            await message.answer("You are already in a guild.")
            return
        if len(args) < 3 or not args[2].isdigit():
            await message.answer("Usage: <code>/guild join guild_id</code>.")
            return
        guild_id = int(args[2])
        cur = await db.execute("SELECT name FROM guilds WHERE guild_id=?", (guild_id,))
        guild = await cur.fetchone()
        if not guild:
            await message.answer("Guild not found.")
            return
        cur = await db.execute("SELECT COUNT(*) AS total FROM guild_members WHERE guild_id=?", (guild_id,))
        if (await cur.fetchone())["total"] >= 20:
            await message.answer("This guild has reached its 20-member limit.")
            return
        await db.execute("INSERT INTO guild_members(user_id, guild_id, role) VALUES (?, ?, 'member')", (user_id, guild_id))
        await db.commit()
        await message.answer(f"✅ You joined <b>{escape(guild['name'])}</b>.")
        return

    if action == "leave":
        if not membership:
            await message.answer("You are not in a guild.")
            return
        if membership["role"] == "leader":
            cur = await db.execute("SELECT COUNT(*) AS total FROM guild_members WHERE guild_id=?", (membership["guild_id"],))
            if (await cur.fetchone())["total"] > 1:
                await message.answer("Guild leaders cannot leave while members remain. Use /guild disband; leadership transfer is not available yet.")
                return
            await db.execute("DELETE FROM guilds WHERE guild_id=?", (membership["guild_id"],))
        await db.execute("DELETE FROM guild_members WHERE user_id=?", (user_id,))
        await db.commit()
        await message.answer("You left your guild.")
        return

    if action == "disband":
        if not membership or membership["role"] != "leader":
            await message.answer("Only a guild leader can disband a guild.")
            return
        await db.execute("DELETE FROM guild_members WHERE guild_id=?", (membership["guild_id"],))
        await db.execute("DELETE FROM guilds WHERE guild_id=?", (membership["guild_id"],))
        await db.commit()
        await message.answer("🏰 Your guild has been disbanded.")
        return

    if action == "top":
        cur = await db.execute(
            "SELECT g.guild_id, g.name, g.guild_level, g.guild_xp, COUNT(m.user_id) AS members "
            "FROM guilds g LEFT JOIN guild_members m ON m.guild_id=g.guild_id "
            "GROUP BY g.guild_id ORDER BY g.guild_level DESC, g.guild_xp DESC LIMIT 10"
        )
        rows = await cur.fetchall()
        lines = ["🏆 <b>Top Guilds</b>"]
        for i, row in enumerate(rows, 1):
            lines.append(f"{i}. <b>{escape(row['name'])}</b> · Lv.{row['guild_level']} · {row['members']} members · ID {row['guild_id']}")
        await message.answer("\n".join(lines))
        return

    if action == "info" and membership:
        text = await guild_summary(membership["guild_id"])
        await message.answer(text or "Guild not found.")
        return
    if action == "info":
        await message.answer("You are not in a guild. Use <code>/guild create Name</code> or <code>/guild join ID</code>.")
        return
    await message.answer("Guild commands: /guild create Name, /guild join ID, /guild leave, /guild info, /guild top, /guild disband.")


@dp.callback_query(F.data == "guild_info")
async def cb_guild_info(call: CallbackQuery):
    await call.answer()
    cur = await db.execute("SELECT guild_id FROM guild_members WHERE user_id=?", (call.from_user.id,))
    membership = await cur.fetchone()
    if not membership:
        await call.message.answer("You are not in a guild. Use /guild create Name or /guild join ID.")
        return
    await call.message.answer(await guild_summary(membership["guild_id"]))


@dp.message(Command("duel"))
async def create_duel(message: Message):
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("Use /duel as a reply to another player's message inside a group.")
        return
    target_message = message.reply_to_message
    if not target_message or not target_message.from_user:
        await message.answer("Reply to the player you want to challenge, then send /duel.")
        return
    challenger_id = message.from_user.id
    opponent_id = target_message.from_user.id
    if challenger_id == opponent_id or target_message.from_user.is_bot:
        await message.answer("You need to challenge another human player.")
        return
    challenger = await get_player(challenger_id, message.from_user.username or message.from_user.full_name)
    opponent = await get_player(opponent_id, target_message.from_user.username or target_message.from_user.full_name)
    if not challenger["class_selected"] or not opponent["class_selected"]:
        await message.answer("Both players must use /start in the bot's private chat and choose a hero class first.")
        return
    cur = await db.execute(
        "SELECT 1 FROM duels WHERE status IN ('active', 'pending') AND (challenger_id IN (?, ?) OR opponent_id IN (?, ?))",
        (challenger_id, opponent_id, challenger_id, opponent_id),
    )
    if await cur.fetchone():
        await message.answer("One of these players is already in an active duel.")
        return
    cur = await db.execute(
        "INSERT INTO duels(chat_id, challenger_id, opponent_id, challenger_hp, opponent_hp, status) "
        "VALUES (?, ?, ?, ?, ?, 'pending')",
        (message.chat.id, challenger_id, opponent_id, challenger["max_hp"], opponent["max_hp"]),
    )
    await db.commit()
    duel_id = cur.lastrowid
    await message.answer(
        f"⚔️ <b>Duel Challenge #{duel_id}</b>\n"
        f"{escape(challenger['username'] or 'Challenger')} challenges "
        f"{escape(opponent['username'] or 'Opponent')}!\n"
        "The challenged player must accept.",
        reply_markup=duel_keyboard(duel_id, invite=True),
    )


@dp.callback_query(F.data.startswith("duel_accept:"))
async def accept_duel(call: CallbackQuery):
    duel_id = int(call.data.split(":", 1)[1])
    cur = await db.execute("SELECT * FROM duels WHERE duel_id=?", (duel_id,))
    duel = await cur.fetchone()
    if not duel or duel["status"] != "pending":
        await call.answer("This duel invitation is no longer active.", show_alert=True)
        return
    if call.from_user.id != duel["opponent_id"]:
        await call.answer("Only the challenged player can accept.", show_alert=True)
        return
    await call.answer()
    await db.execute(
        "UPDATE duels SET status='active', turn_user_id=challenger_id WHERE duel_id=? AND status='pending'",
        (duel_id,),
    )
    await db.commit()
    cur = await db.execute("SELECT * FROM duels WHERE duel_id=?", (duel_id,))
    duel = await cur.fetchone()
    await call.message.edit_text(await duel_text(duel), reply_markup=duel_keyboard(duel_id))


@dp.callback_query(F.data.startswith("duel_decline:"))
async def decline_duel(call: CallbackQuery):
    duel_id = int(call.data.split(":", 1)[1])
    cur = await db.execute("SELECT * FROM duels WHERE duel_id=?", (duel_id,))
    duel = await cur.fetchone()
    if not duel or duel["status"] != "pending":
        await call.answer("This duel invitation is no longer active.", show_alert=True)
        return
    if call.from_user.id != duel["opponent_id"]:
        await call.answer("Only the challenged player can decline.", show_alert=True)
        return
    await call.answer()
    await db.execute("UPDATE duels SET status='declined' WHERE duel_id=?", (duel_id,))
    await db.commit()
    await call.message.edit_text("✋ Duel declined.")


@dp.callback_query(F.data.startswith("duel_action:"))
async def duel_action(call: CallbackQuery):
    _, action, duel_id_text = call.data.split(":", 2)
    duel_id = int(duel_id_text)
    cur = await db.execute("SELECT * FROM duels WHERE duel_id=?", (duel_id,))
    duel = await cur.fetchone()
    if not duel or duel["status"] != "active":
        await call.answer("This duel is not active.", show_alert=True)
        return
    user_id = call.from_user.id
    if user_id not in {duel["challenger_id"], duel["opponent_id"]}:
        await call.answer("You are not part of this duel.", show_alert=True)
        return
    if duel["turn_user_id"] != user_id:
        await call.answer("Wait for your turn.", show_alert=True)
        return
    if action not in {"attack", "skill", "surrender"}:
        await call.answer("Unknown duel action.", show_alert=True)
        return
    await call.answer()
    if action == "surrender":
        winner_id = duel["opponent_id"] if user_id == duel["challenger_id"] else duel["challenger_id"]
        loser_id = user_id
        await db.execute("UPDATE duels SET status='finished', winner_id=? WHERE duel_id=?", (winner_id, duel_id))
        await db.execute("UPDATE players SET pvp_wins=pvp_wins+1 WHERE user_id=?", (winner_id,))
        await db.execute("UPDATE players SET pvp_losses=pvp_losses+1 WHERE user_id=?", (loser_id,))
        await db.commit()
    else:
        attacker_id = user_id
        defender_id = duel["opponent_id"] if user_id == duel["challenger_id"] else duel["challenger_id"]
        attacker = await get_player(attacker_id)
        defender = await get_player(defender_id)
        attacker_class = HERO_CLASSES.get(attacker["hero_class"], HERO_CLASSES["Knight"])
        defender_class = HERO_CLASSES.get(defender["hero_class"], HERO_CLASSES["Knight"])
        base = attacker["level"] * 8 + attacker_class["attack"] + attacker["weapon_attack"]
        if action == "skill":
            base = int(base * 1.8)
        damage = max(5, base + random.randint(0, 12) - defender["armor_defense"] - defender_class["defense"])
        if user_id == duel["challenger_id"]:
            new_hp = max(0, duel["opponent_hp"] - damage)
            await db.execute("UPDATE duels SET opponent_hp=? WHERE duel_id=?", (new_hp, duel_id))
        else:
            new_hp = max(0, duel["challenger_hp"] - damage)
            await db.execute("UPDATE duels SET challenger_hp=? WHERE duel_id=?", (new_hp, duel_id))
        if new_hp == 0:
            await db.execute("UPDATE duels SET status='finished', winner_id=? WHERE duel_id=?", (user_id, duel_id))
            await db.execute("UPDATE players SET pvp_wins=pvp_wins+1 WHERE user_id=?", (user_id,))
            await db.execute("UPDATE players SET pvp_losses=pvp_losses+1 WHERE user_id=?", (defender_id,))
        else:
            await db.execute("UPDATE duels SET turn_user_id=? WHERE duel_id=?", (defender_id, duel_id))
        await db.commit()
    cur = await db.execute("SELECT * FROM duels WHERE duel_id=?", (duel_id,))
    duel = await cur.fetchone()
    if duel["status"] == "finished" and duel["chat_id"] < 0 and duel["winner_id"]:
        try:
            await record_group_activity(db,duel["chat_id"],"battle")
            await award_group_xp(db,duel["chat_id"],20)
        except GroupError:
            pass
    markup = duel_keyboard(duel_id) if duel["status"] == "active" else None
    await call.message.edit_text(await duel_text(duel), reply_markup=markup)


@dp.message(Command("pvprank"))
async def pvprank(message: Message):
    cur = await db.execute(
        "SELECT username, pvp_wins, pvp_losses FROM players ORDER BY pvp_wins DESC, pvp_losses ASC LIMIT 10"
    )
    rows = await cur.fetchall()
    lines = ["⚔️ <b>PvP Rankings</b>"]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. {escape(row['username'] or 'Adventurer')} · {row['pvp_wins']}W / {row['pvp_losses']}L")
    await message.answer("\n".join(lines))


@dp.message(Command("start"))
async def start(message: Message):
    p = await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    if not p["class_selected"]:
        await message.answer(
            "🌟 <b>Choose Your Hero Class</b>\n\n"
            "🛡️ Knight: high HP and defence.\n"
            "🔮 Mage: powerful magic attacks.\n"
            "🏹 Archer: fast and precise.\n"
            "🪓 Berserker: massive damage, lower defence.",
            reply_markup=class_keyboard(),
        )
        return
    await message.answer(
        "🌌 <b>THE PEAK ADVENTURE</b>\n\n"
        "A quiet world is breaking. Strange creatures are changing, old kingdoms have fallen, "
        "and a forgotten force is waking beneath the earth. Your journey begins with one small slime...\n\n"
        "Explore, fight monsters, grow stronger, and uncover the mystery behind the 100 levels.\n\n"
        "Use the buttons below or /help.",
        reply_markup=menu(include_webapp=message.chat.type == "private"))



@dp.message(Command("admin"))
async def admin_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ This command is restricted to bot administrators.")
        return
    args=(message.text or "").split(maxsplit=2)
    action=args[1].lower() if len(args)>1 else "stats"
    if action=="stats":
        stats=await dashboard_stats(db)
        await message.answer(
            "🛠️ <b>THE PEAK ADMIN PANEL</b>\n"
            f"Players: {stats['players']}\nActive monster battles: {stats['active_battles']}\n"
            f"Guilds: {stats['guilds']}\nRegistered groups: {stats['registered_groups']}\n"
            f"Active PvP duels: {stats['active_duels']}\n\n"
            "Commands: /admin player ID, /admin coins ID +/-AMOUNT, /admin announce MESSAGE."
        )
        return
    if action=="player":
        if len(args)<3 or not args[2].isdigit():
            await message.answer("Usage: /admin player player_id"); return
        cur=await db.execute("SELECT * FROM players WHERE user_id=?",(int(args[2]),))
        player=await cur.fetchone()
        if not player:
            await message.answer("Player account not found."); return
        await message.answer(
            f"👤 <b>{escape(player['username'] or 'Adventurer')}</b> · ID <code>{player['user_id']}</code>\n"
            f"Level {player['level']} · {player['hero_class']} · XP {player['xp']}\n"
            f"HP {player['hp']}/{player['max_hp']} · Coins {player['coins']} · Wins {player['wins']}"
        )
        return
    if action=="coins":
        if len(args)<3:
            await message.answer("Usage: /admin coins player_id amount_delta"); return
        parts=args[2].split()
        if len(parts)!=2 or not parts[0].isdigit() or not re.fullmatch(r"-?\d+",parts[1]):
            await message.answer("Usage: /admin coins player_id amount_delta"); return
        try:
            balance=await adjust_player_coins(db,int(parts[0]),int(parts[1]))
            await message.answer(f"✅ Player <code>{parts[0]}</code> coin balance is now {balance}.")
        except AdminError as exc: await message.answer(escape(str(exc)))
        return
    if action=="announce":
        if len(args)<3 or not args[2].strip():
            await message.answer("Usage: /admin announce your announcement"); return
        cur=await db.execute("SELECT user_id FROM players")
        player_ids=[row["user_id"] for row in await cur.fetchall()]
        sent=failed=0
        text=escape(args[2].strip()[:3500])
        for index,user_id in enumerate(player_ids,1):
            try:
                await message.bot.send_message(user_id,"📢 <b>THE PEAK ANNOUNCEMENT</b>\n\n"+text)
                sent+=1
            except Exception:
                failed+=1
            if index%20==0: await asyncio.sleep(1)
        await message.answer(f"📢 Broadcast finished. Sent: {sent}. Failed: {failed}.")
        return
    await message.answer("Admin commands: /admin stats, /admin player ID, /admin coins ID +/-AMOUNT, /admin announce MESSAGE.")


@dp.message(Command("export"))
async def export_account(message: Message):
    try:
        data=await export_player_data(db,message.from_user.id)
    except AdminError as exc:
        await message.answer(escape(str(exc))); return
    payload=json.dumps(data,ensure_ascii=False,indent=2,default=str).encode("utf-8")
    document=BufferedInputFile(payload,filename=f"peak-adventure-{message.from_user.id}-export.json")
    await message.answer_document(document,caption="Your personal account data export. Keep this file private.")


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "<b>📖 Adventure Guide</b>\n"
        "/start - Main menu\n/profile - Your hero stats\n/explore - Find a monster\n"
        "/inventory - Potions and items\n/map - World and boss milestones\n"
        "/quests - Current objectives\n/daily - Daily coins and potion\n"
        "/leaderboard - Top adventurers\n/heal - Restore HP (uses 30 coins)\n"
        "/class - View hero classes\n/shop - Buy weapons, armor and potions\n"
        "/claimquest quest_id - Claim a completed quest reward\n"
        "/achievements - View achievements\n/claimachievement achievement_id - Claim an achievement\n"
        "/duel - Challenge a player by replying to their message in a group\n/pvprank - PvP rankings\n"
        "/friend request|accept|decline|list|remove - Friend list\n"
        "/party create|invite|accept|decline|info|leave|disband - Party management\n"
        "/guild create|join|leave|info|top|disband - Guild management\n"
        "/group register|info|members|missions|claim|raid|ban|unban|top - Telegram group features\n"
        "/admin - Bot administration (authorized IDs only)\n/export - Download your account data\n"
        "/trade - Start a trade by replying to a player\n/offer, /confirmtrade, /canceltrade - Manage trades\n"
        "/monster level - Inspect a monster\n/bestiary - View discovered monsters\n\n"
        "During battle use Attack, Special Skill, Potion or Escape buttons.")


@dp.message(Command("profile"))
async def profile(message: Message):
    p = await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(await player_text(p))


@dp.message(Command("explore"))
async def explore(message: Message):
    await start_battle(message.from_user.id, message.from_user.username, message)


@dp.message(Command("inventory"))
async def inventory(message: Message):
    p = await get_player(message.from_user.id)
    await message.answer(
        f"🎒 <b>Inventory</b>\n🧪 Health Potions: {p['potions']}\n🪙 Coins: {p['coins']}\n"
        f"⚔️ Weapon: {p['weapon']} (+{p['weapon_attack']} ATK)\n"
        f"🛡️ Armor: {p['armor']} (+{p['armor_defense']} DEF)\n\n"
        "Use /shop to upgrade your gear or /heal to restore HP."
    )


@dp.message(Command("class"))
async def show_classes(message: Message):
    p = await get_player(message.from_user.id)
    await message.answer(
        f"🧙 Current class: <b>{p['hero_class']}</b>\n"
        "Knight: HP +40, ATK +8, DEF +12\n"
        "Mage: ATK +18, faster Arcane Nova\n"
        "Archer: ATK +12, DEF +4, SPEED +10\n"
        "Berserker: HP +25, ATK +22, DEF -3\n\n"
        "Class choice is permanent in this version."
    )


@dp.message(Command("shop"))
async def shop(message: Message):
    await get_player(message.from_user.id, message.from_user.username)
    await message.answer("🛒 <b>Adventurer's Shop</b>\nBuy stronger gear as you level up.", reply_markup=shop_keyboard())


@dp.message(Command("heal"))
async def heal(message: Message):
    p = await get_player(message.from_user.id)
    cur = await db.execute("SELECT 1 FROM battles WHERE user_id=?", (message.from_user.id,))
    if await cur.fetchone():
        await message.answer("⚔️ Finish or escape your current battle before healing at camp.")
        return
    if p["hp"] >= p["max_hp"]:
        await message.answer("❤️ Your HP is already full.")
    elif p["coins"] < 30:
        await message.answer("🪙 You need 30 coins to heal.")
    else:
        debit = await db.execute(
            "UPDATE players SET coins=coins-30, hp=max_hp WHERE user_id=? AND coins>=30",
            (message.from_user.id,),
        )
        await db.commit()
        if debit.rowcount:
            await message.answer("✨ Your HP has been fully restored.")
        else:
            await message.answer("🪙 You need 30 coins to heal.")


@dp.message(Command("map"))
async def map_cmd(message: Message):
    p = await get_player(message.from_user.id)
    worlds = ["🌱 Whispering Meadow", "🏜️ Ashen Desert", "🌩️ Stormglass Highlands", "🏰 Hollow Kingdom",
              "🌋 Ember Abyss", "❄️ Frostfang Peaks", "🕳️ Primordial Rift", "🌌 Celestial Ruins",
              "⌛ Eternal Hour", "🌠 Origin Realm"]
    idx = min(9, (p["level"] - 1) // 10)
    await message.answer(f"🗺️ <b>World Map</b>\nCurrent region: <b>{worlds[idx]}</b>\nProgress: Level {p['level']}/100\nBoss gates: levels 10, 20, 30 ... 100.")


@dp.message(Command("monster"))
async def monster_info(message: Message):
    if len(message.command) < 2 or not message.command[1].isdigit():
        await message.answer("Usage: <code>/monster 1</code> to inspect a monster.")
        return
    level = int(message.command[1])
    if level not in MONSTER_BY_LEVEL:
        await message.answer("Monster level must be between 1 and 100.")
        return
    m = MONSTER_BY_LEVEL[level]
    await message.answer(
        f"👹 <b>{m['name']}</b> · Level {m['level']} · {m['rank']}\n"
        f"⚡ Power: {m['power']}\n❤️ HP: {m['hp']}\n⚔️ ATK: {m['attack_power']} · 🛡️ DEF: {m['defense']} · 💨 SPD: {m['speed']}\n"
        f"✨ Special Move: {m['special_move']}\n🧬 Unique Power: {m['unique_power']}\n"
        f"⚖️ Advantage: {m['advantage']}\n⚠️ Disadvantage: {m['disadvantage']}\n"
        f"🎯 Weakness: {m['weakness']}\n\n<i>{m['story']}</i>"
    )


@dp.message(Command("bestiary"))
async def bestiary(message: Message):
    await get_player(message.from_user.id)
    cur = await db.execute(
        "SELECT monster_level FROM monster_discoveries WHERE user_id=? ORDER BY monster_level",
        (message.from_user.id,),
    )
    rows = await cur.fetchall()
    if not rows:
        await message.answer("📚 <b>Monster Bestiary</b>\nNo creatures discovered yet. Use /explore to begin your research.")
        return
    lines = [f"📚 <b>Monster Bestiary</b> · {len(rows)}/100 discovered"]
    for row in rows:
        monster = MONSTER_BY_LEVEL[row["monster_level"]]
        marker = "👑" if monster["boss"] else "•"
        lines.append(f"{marker} Lv.{monster['level']} {monster['name']} · {monster['element']}")
    lines.append("\nUse /monster <code>level</code> for full details.")
    await message.answer("\n".join(lines))


@dp.message(Command("achievements"))
async def achievements(message: Message):
    text, markup = await achievement_view(message.from_user.id)
    await message.answer(text, reply_markup=markup)


@dp.message(Command("claimachievement"))
async def claimachievement(message: Message):
    if len(message.command) < 2:
        await message.answer("Usage: <code>/claimachievement achievement_id</code>.")
        return
    result = await claim_achievement_reward(message.from_user.id, message.command[1])
    await message.answer(result)


@dp.message(Command("quests"))
async def quests(message: Message):
    text, markup = await quest_view(message.from_user.id)
    await message.answer(text, reply_markup=markup)


@dp.message(Command("claimquest"))
async def claimquest(message: Message):
    if len(message.command) < 2:
        await message.answer("Usage: <code>/claimquest quest_id</code>. Use /quests to see available rewards.")
        return
    result = await claim_quest_reward(message.from_user.id, message.command[1])
    await message.answer(result)


@dp.message(Command("daily"))
async def daily(message: Message):
    await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    claimed = await claim_daily_reward(message.from_user.id)
    if claimed:
        await message.answer("🎁 Daily reward claimed: +50 coins and +1 potion. Come back tomorrow!")
    else:
        await message.answer("⏳ You have already claimed today's reward. Come back 24 hours after your last claim.")


@dp.message(Command("leaderboard"))
async def leaderboard(message: Message):
    cur = await db.execute("SELECT username, level, wins FROM players ORDER BY level DESC, wins DESC LIMIT 10")
    rows = await cur.fetchall()
    if not rows:
        await message.answer("No adventurers yet.")
        return
    lines = ["🏆 <b>Top Adventurers</b>"]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. {escape(row['username'] or 'Adventurer')} · Lv.{row['level']} · {row['wins']} wins")
    await message.answer("\n".join(lines))


@dp.callback_query(F.data == "explore")
async def cb_explore(call: CallbackQuery):
    await call.answer()
    await start_battle(call.from_user.id, call.from_user.username, call.message)


@dp.callback_query(F.data == "class_menu")
async def cb_class_menu(call: CallbackQuery):
    await call.answer()
    p = await get_player(call.from_user.id, call.from_user.username)
    if p["class_selected"]:
        await call.message.answer(f"🧙 Your class is <b>{p['hero_class']}</b>. Class changes are locked in this version.")
    else:
        await call.message.answer("Choose your hero class:", reply_markup=class_keyboard())


@dp.callback_query(F.data.startswith("class:"))
async def cb_choose_class(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    chosen = call.data.split(":", 1)[1]
    if chosen not in HERO_CLASSES:
        await call.message.answer("Unknown class.")
        return
    p = await get_player(user_id, call.from_user.username)
    if p["class_selected"]:
        await call.message.answer("Your hero class has already been chosen.")
        return
    stats = HERO_CLASSES[chosen]
    cur = await db.execute(
        "UPDATE players SET hero_class=?, class_selected=1, max_hp=max_hp+?, hp=hp+? WHERE user_id=? AND class_selected=0",
        (chosen, stats["hp"], stats["hp"], user_id),
    )
    await db.commit()
    if cur.rowcount == 0:
        await call.message.answer("Your hero class has already been chosen.")
        return
    await call.message.answer(
        f"✨ You are now a <b>{chosen}</b>!\n"
        f"Class skill: {stats['skill']}\nElement: {stats['element']}\n"
        "Your adventure begins now.",
        reply_markup=menu(include_webapp=call.message.chat.type == "private"),
    )


@dp.callback_query(F.data == "shop")
async def cb_shop(call: CallbackQuery):
    await call.answer()
    await call.message.answer("🛒 <b>Adventurer's Shop</b>\nChoose an item to buy:", reply_markup=shop_keyboard())


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy_item(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    item_id = call.data.split(":", 1)[1]
    item = SHOP_ITEMS.get(item_id)
    if not item:
        await call.message.answer("That shop item does not exist.")
        return
    p = await get_player(user_id, call.from_user.username)
    if not p["class_selected"]:
        await call.message.answer("Choose your hero class first.")
        return
    active = await db.execute("SELECT 1 FROM battles WHERE user_id=?", (user_id,))
    if await active.fetchone():
        await call.message.answer("Finish or escape your current battle before shopping.")
        return
    if p["level"] < item["level"]:
        await call.message.answer(f"🔒 You need level {item['level']} to buy {item['name']}.")
        return
    if p["coins"] < item["cost"]:
        await call.message.answer(f"🪙 You need {item['cost']} coins for {item['name']}.")
        return
    if item["type"] == "weapon" and item["bonus"] <= p["weapon_attack"]:
        await call.message.answer("Your current weapon is already as strong or stronger.")
        return
    if item["type"] == "armor" and item["bonus"] <= p["armor_defense"]:
        await call.message.answer("Your current armor is already as strong or stronger.")
        return
    debit = await db.execute("UPDATE players SET coins=coins-? WHERE user_id=? AND coins>=?", (item["cost"], user_id, item["cost"]))
    if debit.rowcount == 0:
        await call.message.answer("🪙 You no longer have enough coins for this purchase.")
        return
    if item["type"] == "weapon":
        await db.execute("UPDATE players SET weapon=?, weapon_attack=? WHERE user_id=?", (item["name"], item["bonus"], user_id))
    elif item["type"] == "armor":
        await db.execute("UPDATE players SET armor=?, armor_defense=? WHERE user_id=?", (item["name"], item["bonus"], user_id))
    else:
        await db.execute("UPDATE players SET potions=potions+? WHERE user_id=?", (item["bonus"], user_id))
    await db.commit()
    await call.message.answer(f"✅ Purchased <b>{item['name']}</b> for {item['cost']} coins.")


@dp.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery):
    await call.answer()
    p = await get_player(call.from_user.id, call.from_user.username)
    await call.message.answer(await player_text(p), reply_markup=menu(include_webapp=call.message.chat.type == "private"))


@dp.callback_query(F.data == "inventory")
async def cb_inventory(call: CallbackQuery):
    await call.answer()
    p = await get_player(call.from_user.id)
    await call.message.answer(f"🎒 <b>Inventory</b>\n🧪 Potions: {p['potions']}\n🪙 Coins: {p['coins']}")


@dp.callback_query(F.data == "achievements")
async def cb_achievements(call: CallbackQuery):
    await call.answer()
    text, markup = await achievement_view(call.from_user.id)
    await call.message.answer(text, reply_markup=markup)


@dp.callback_query(F.data.startswith("achclaim:"))
async def cb_claim_achievement(call: CallbackQuery):
    await call.answer()
    achievement_id = call.data.split(":", 1)[1]
    result = await claim_achievement_reward(call.from_user.id, achievement_id)
    await call.message.answer(result)


@dp.callback_query(F.data == "quests")
async def cb_quests(call: CallbackQuery):
    await call.answer()
    text, markup = await quest_view(call.from_user.id)
    await call.message.answer(text, reply_markup=markup)


@dp.callback_query(F.data.startswith("questclaim:"))
async def cb_claim_quest(call: CallbackQuery):
    await call.answer()
    quest_id = call.data.split(":", 1)[1]
    result = await claim_quest_reward(call.from_user.id, quest_id)
    await call.message.answer(result)


@dp.callback_query(F.data == "daily")
async def cb_daily(call: CallbackQuery):
    await call.answer()
    await get_player(call.from_user.id, call.from_user.username)
    claimed = await claim_daily_reward(call.from_user.id)
    if claimed:
        await call.message.answer("🎁 Daily reward claimed: +50 coins and +1 potion. Come back tomorrow!")
    else:
        await call.message.answer("⏳ You have already claimed today's reward. Come back after the UTC day resets.")


@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    await call.answer()
    cur = await db.execute("SELECT username, level, wins FROM players ORDER BY level DESC, wins DESC LIMIT 10")
    rows = await cur.fetchall()
    await call.message.answer("🏆 <b>Leaderboard</b>\n" + "\n".join(
        f"{i}. {escape(r['username'] or 'Adventurer')} · Lv.{r['level']} · {r['wins']} wins" for i, r in enumerate(rows, 1)))


async def _battle_action_unlocked(call: CallbackQuery):
    assert db is not None
    await call.answer()
    user_id = call.from_user.id
    cur = await db.execute("SELECT * FROM battles WHERE user_id=?", (user_id,))
    b = await cur.fetchone()
    if not b:
        await call.message.edit_text("This battle has ended. Use /explore to find another monster.")
        return
    p = await get_player(user_id, call.from_user.username)
    m = MONSTER_BY_LEVEL[b["monster_level"]]
    class_stats = HERO_CLASSES.get(p["hero_class"], HERO_CLASSES["Knight"])
    action = call.data.split(":", 1)[1]
    if action not in {"attack", "skill", "potion", "flee"}:
        await call.message.answer("Unknown battle action. Please use the battle buttons.")
        return
    if action == "flee":
        result = await finish_battle(user_id, False, escaped=True)
        await call.message.edit_text(result, reply_markup=menu(include_webapp=call.message.chat.type == "private"))
        return
    if action == "potion":
        if p["potions"] <= 0:
            await call.message.answer("🧪 No potions left!")
            return
        heal_amount = min(80, p["max_hp"] - p["hp"])
        if heal_amount <= 0:
            await call.message.answer("❤️ HP is already full.")
            return
        await db.execute("UPDATE players SET potions=potions-1, hp=hp+? WHERE user_id=?", (heal_amount, user_id))
        damage = 0
        action_line = f"🧪 You recover {heal_amount} HP."
    elif action == "skill":
        if p["skill_cd"] > 0:
            await call.message.answer(f"⏳ Skill cooling down: {p['skill_cd']} turn(s).")
            return
        damage = max(25, (p["level"] * 13 + 30 + class_stats["attack"] * 2 + p["weapon_attack"] * 2) - m["defense"] // 2) * 2
        await db.execute("UPDATE players SET skill_cd=? WHERE user_id=?", (skill_cooldown_for_class(p["hero_class"]), user_id))
        action_line = f"🔥 <b>{class_stats['skill']}!</b> You deal {damage} damage."
    else:
        damage = max(8, p["level"] * 10 + class_stats["attack"] + p["weapon_attack"] + random.randint(5, 18) - m["defense"] // 3)
        action_line = f"⚔️ You strike for {damage} damage."
    if action != "potion":
        elemental_multiplier = 1.0
        if class_stats["element"] == m["weakness"]:
            elemental_multiplier = 1.5
            action_line += f" ✨ Super effective! {class_stats['element']} exploits its weakness."
        elif class_stats["element"] == m["element"]:
            elemental_multiplier = 0.8
            action_line += f" 🧱 {m['element']} resists your matching element."
        damage = max(1, int(damage * elemental_multiplier))
        if m["trait_effect"] == "armored":
            damage = max(1, int(damage * 0.85))
            action_line += " 🛡️ Its armor absorbs part of the hit."
        if m["trait_effect"] == "shield" and (b["turn_count"] + 1) % 3 == 1:
            damage = max(1, int(damage * 0.7))
            action_line += " 🔰 Its shield blocks part of this strike."
    else:
        damage = 0
    new_enemy_hp = max(0, b["monster_hp"] - damage)
    turn_count = b["turn_count"] + 1
    if new_enemy_hp > 0 and m["trait_effect"] == "regenerate":
        regen = max(1, m["hp"] // 50)
        new_enemy_hp = min(m["hp"], new_enemy_hp + regen)
    if new_enemy_hp == 0:
        await db.execute("UPDATE players SET hp=min(max_hp, hp+15), skill_cd=max(0, skill_cd-1) WHERE user_id=?", (user_id,))
        await db.commit()
        result = await finish_battle(user_id, True)
        await call.message.edit_text(f"{action_line}\n\n{result}", reply_markup=menu(include_webapp=call.message.chat.type == "private"))
        return
    p = await get_player(user_id)
    previous_boss_phase = get_boss_phase(m["boss"], b["monster_hp"], m["hp"])
    current_boss_phase = get_boss_phase(m["boss"], new_enemy_hp, m["hp"])
    enemy_tactic = choose_monster_tactic(m["trait_effect"], turn_count, new_enemy_hp, m["hp"], is_boss=m["boss"], boss_phase=current_boss_phase)
    special_turn = enemy_tactic == "special"
    enemy_damage = calculate_enemy_damage(
        m["attack_power"], p["level"], p["armor_defense"], class_stats["defense"],
        m["speed"], random.randint(-3, 6),
        fury=m["trait_effect"] == "fury" and new_enemy_hp <= int(m["hp"] * 0.3),
        special=special_turn,
        boss_phase=current_boss_phase,
    )
    if m["trait_effect"] == "berserk" and new_enemy_hp <= int(m["hp"] * 0.5):
        enemy_damage = int(enemy_damage * 1.35)
    evaded = class_evades(class_stats["speed"], random.randint(1, 100))
    if evaded:
        enemy_damage = 0
    reflect_damage = max(1, damage // 5) if m["trait_effect"] == "reflect" and action != "potion" else 0
    poison_damage = max(1, p["max_hp"] // 40) if m["trait_effect"] == "poison" else 0
    new_hp = max(0, p["hp"] - enemy_damage - reflect_damage - poison_damage)
    effect_notes = []
    if current_boss_phase > previous_boss_phase:
        effect_notes.append(f"👑 {m['name']} enters BOSS PHASE {current_boss_phase}!")
    if evaded:
        effect_notes.append(f"💨 Your {p['hero_class']} speed dodges the monster's strike.")
    if reflect_damage:
        effect_notes.append(f"🪞 Your strike is reflected for {reflect_damage} damage.")
    if poison_damage:
        effect_notes.append(f"☠️ Poison deals {poison_damage} damage.")
    if enemy_damage > 0 and m["trait_effect"] == "drain":
        new_enemy_hp = min(m["hp"], new_enemy_hp + max(1, enemy_damage // 10))
    elif enemy_damage > 0 and m["trait_effect"] == "lifesteal":
        stolen = max(1, enemy_damage // 4)
        new_enemy_hp = min(m["hp"], new_enemy_hp + stolen)
        effect_notes.append(f"🩸 The monster steals {stolen} HP.")
    await db.execute("UPDATE battles SET monster_hp=?, turn_count=? WHERE user_id=?", (new_enemy_hp, turn_count, user_id))
    await db.execute("UPDATE players SET hp=?, skill_cd=max(0, skill_cd-1) WHERE user_id=?", (new_hp, user_id))
    await db.commit()
    effect_text = " " + " ".join(effect_notes) if effect_notes else ""
    if new_hp == 0:
        result = await finish_battle(user_id, False)
        await call.message.edit_text(f"{action_line}\n💥 {m['name']} hits you for {enemy_damage}.{effect_text}\n\n{result}", reply_markup=menu(include_webapp=call.message.chat.type == "private"))
        return
    enemy_action = (
        f"💨 You evade {m['name']}'s attack with your {p['hero_class']} speed!"
        if evaded else (
            f"💥 {m['name']} uses {m['special_move']} and hits for {enemy_damage}!"
            if special_turn else f"💥 {m['name']} hits you for {enemy_damage}."
        )
    )
    enemy_action += effect_text
    await send_battle(call.message, user_id, f"{action_line}\n{enemy_action}", edit=True)


@dp.callback_query(F.data.startswith("battle:"))
async def battle_action(call: CallbackQuery):
    async with player_locks[call.from_user.id]:
        await _battle_action_unlocked(call)


async def miniapp_state(user: dict):
    user_id = user["id"]
    p = await get_player(user_id, user.get("username") or user.get("first_name") or "Adventurer")
    region_names = [
        "Whispering Meadow", "Ashen Desert", "Stormglass Highlands", "Hollow Kingdom",
        "Ember Abyss", "Frostfang Peaks", "Primordial Rift", "Celestial Ruins",
        "Eternal Hour", "Origin Realm",
    ]
    region_index = min(9, (p["level"] - 1) // 10)
    boss_defeated = False
    if p["level"] in BOSS_LEVELS:
        cur = await db.execute(
            "SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?",
            (user_id, p["level"]),
        )
        boss_defeated = await cur.fetchone() is not None
    nearby_levels = nearby_monster_levels(p["level"], boss_defeated)
    nearby_monsters = [
        {
            "name": MONSTER_BY_LEVEL[level]["name"],
            "level": level,
            "element": MONSTER_BY_LEVEL[level]["element"],
            "boss": MONSTER_BY_LEVEL[level]["boss"],
        }
        for level in nearby_levels
    ]
    monster = MONSTER_BY_LEVEL[nearby_levels[0]]
    cur = await db.execute("SELECT * FROM battles WHERE user_id=?", (user_id,))
    battle_row = await cur.fetchone()
    battle = None
    if battle_row:
        active_monster = MONSTER_BY_LEVEL[battle_row["monster_level"]]
        battle = {
            "level": active_monster["level"],
            "name": active_monster["name"],
            "hp": battle_row["monster_hp"],
            "max_hp": active_monster["hp"],
            "special_move": active_monster["special_move"],
            "unique_power": active_monster["unique_power"],
            "trait_effect": active_monster["trait_effect"],
            "story": active_monster["story"],
            "weakness": active_monster["weakness"],
            "phase": get_boss_phase(active_monster["boss"], battle_row["monster_hp"], active_monster["hp"]),
        }
    class_stats = HERO_CLASSES.get(p["hero_class"], HERO_CLASSES["Knight"])
    appearance = await get_appearance(db, user_id)
    return {
        "first_name": user.get("first_name") or user.get("username") or "Adventurer",
        "class_selected": bool(p["class_selected"]),
        "battle_active": battle is not None,
        "hero_class": p["hero_class"],
        "appearance": appearance,
        "class_skill": class_stats["skill"],
        "weapon": p["weapon"],
        "weapon_attack": p["weapon_attack"],
        "armor": p["armor"],
        "armor_defense": p["armor_defense"],
        "level": p["level"],
        "xp": p["xp"],
        "xp_required": xp_needed(p["level"]),
        "hp": p["hp"],
        "max_hp": p["max_hp"],
        "potions": p["potions"],
        "skill_cd": p["skill_cd"],
        "coins": p["coins"],
        "region": region_names[region_index],
        "monster": {"name": monster["name"], "level": monster["level"], "element": monster["element"]},
        "nearby_monsters": nearby_monsters,
        "battle": battle,
    }


async def api_state(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    async with db_lock:
        return web.json_response(await miniapp_state(user))


async def api_explore(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "Invalid JSON body."}, status=400)
    if not isinstance(payload, dict):
        return web.json_response({"error": "JSON body must be an object."}, status=400)
    requested_monster_level = payload.get("monster_level")
    if requested_monster_level is not None and (type(requested_monster_level) is not int or not 1 <= requested_monster_level <= 100):
        return web.json_response({"error": "Invalid monster level."}, status=400)
    user_id = user["id"]
    async with db_lock:
      async with player_locks[user_id]:
        p = await get_player(user_id, user.get("username") or user.get("first_name"))
        if not p["class_selected"]:
            return web.json_response({"error": "Choose a hero class in the Telegram chat first."}, status=409)
        if p["hp"] <= 0:
            return web.json_response({"error": "Your hero is exhausted. Use /heal in the Telegram chat."}, status=409)
        cur = await db.execute("SELECT 1 FROM battles WHERE user_id=?", (user_id,))
        if not await cur.fetchone():
            level = p["level"]
            boss_defeated = False
            if level in BOSS_LEVELS:
                cur = await db.execute(
                    "SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?",
                    (user_id, level),
                )
                boss_defeated = await cur.fetchone() is not None
            available_monster_levels = nearby_monster_levels(level, boss_defeated)
            if requested_monster_level is not None and requested_monster_level not in available_monster_levels:
                return web.json_response({"error": "That monster is not available at your current level."}, status=409)
            monster_level = requested_monster_level if requested_monster_level is not None else random.choice(available_monster_levels)
            monster = MONSTER_BY_LEVEL[monster_level]
            await db.execute("UPDATE players SET skill_cd=0 WHERE user_id=?", (user_id,))
            await db.execute(
                "INSERT INTO battles(user_id, monster_level, monster_hp) VALUES (?, ?, ?)",
                (user_id, monster_level, monster["hp"]),
            )
            await db.execute(
                "INSERT OR IGNORE INTO monster_discoveries(user_id, monster_level) VALUES (?, ?)",
                (user_id, monster_level),
            )
            await db.commit()
    return web.json_response({"message": "A monster approaches!", "state": await miniapp_state(user)})


async def api_appearance(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    if request.content_length is not None and request.content_length > 4096:
        return web.json_response({"error": "Appearance request is too large."}, status=413)
    try:
        payload = await request.json()
        appearance = await save_appearance(db, user["id"], payload)
    except (ValueError, AppearanceError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    async with db_lock:
        return web.json_response({"message": "Character appearance saved.", "state": await miniapp_state(user)})


async def api_action(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "Invalid JSON body."}, status=400)
    if not isinstance(payload, dict):
        return web.json_response({"error": "JSON body must be an object."}, status=400)
    action = payload.get("action")
    if action not in {"attack", "skill", "potion", "flee"}:
        return web.json_response({"error": "Unknown battle action."}, status=400)
    user_id = user["id"]
    async with db_lock:
      async with player_locks[user_id]:
        cur = await db.execute("SELECT * FROM battles WHERE user_id=?", (user_id,))
        battle = await cur.fetchone()
        if not battle:
            return web.json_response({"error": "There is no active battle."}, status=409)
        p = await get_player(user_id, user.get("username"))
        monster = MONSTER_BY_LEVEL[battle["monster_level"]]
        class_stats = HERO_CLASSES.get(p["hero_class"], HERO_CLASSES["Knight"])
        if action == "flee":
            message = await finish_battle(user_id, False, escaped=True)
            return web.json_response({"message": message, "state": await miniapp_state(user)})
        if action == "potion":
            if p["potions"] <= 0:
                return web.json_response({"error": "You have no health potions."}, status=409)
            heal_amount = min(80, p["max_hp"] - p["hp"])
            if heal_amount <= 0:
                return web.json_response({"error": "Your HP is already full."}, status=409)
            await db.execute(
                "UPDATE players SET potions=potions-1, hp=hp+? WHERE user_id=?",
                (heal_amount, user_id),
            )
            damage = 0
            action_line = f"You recover {heal_amount} HP."
        elif action == "skill":
            if p["skill_cd"] > 0:
                return web.json_response({"error": f"Skill cooling down: {p['skill_cd']} turn(s)."}, status=409)
            damage = max(
                25,
                (p["level"] * 13 + 30 + class_stats["attack"] * 2 + p["weapon_attack"] * 2)
                - monster["defense"] // 2,
            ) * 2
            await db.execute("UPDATE players SET skill_cd=? WHERE user_id=?", (skill_cooldown_for_class(p["hero_class"]), user_id))
            action_line = f"{class_stats['skill']} deals {damage} damage."
        else:
            damage = max(
                8,
                p["level"] * 10 + class_stats["attack"] + p["weapon_attack"]
                + random.randint(5, 18) - monster["defense"] // 3,
            )
            action_line = f"You strike for {damage} damage."
        if action != "potion":
            if class_stats["element"] == monster["weakness"]:
                damage = int(damage * 1.5)
                action_line += f" Super effective: {class_stats['element']} hits its weakness."
            elif class_stats["element"] == monster["element"]:
                damage = int(damage * 0.8)
                action_line += f" {monster['element']} resists your matching element."
            if monster["trait_effect"] == "armored":
                damage = int(damage * 0.85)
                action_line += " Its armor absorbs part of the hit."
            if monster["trait_effect"] == "shield" and (battle["turn_count"] + 1) % 3 == 1:
                damage = max(1, int(damage * 0.7))
                action_line += " Its shield blocks part of this strike."
        new_enemy_hp = max(0, battle["monster_hp"] - damage)
        turn_count = battle["turn_count"] + 1
        if new_enemy_hp > 0 and monster["trait_effect"] == "regenerate":
            new_enemy_hp = min(monster["hp"], new_enemy_hp + max(1, monster["hp"] // 50))
        if new_enemy_hp == 0:
            await db.execute(
                "UPDATE players SET hp=min(max_hp, hp+15), skill_cd=max(0, skill_cd-1) WHERE user_id=?",
                (user_id,),
            )
            await db.commit()
            message = await finish_battle(user_id, True)
            return web.json_response({"message": f"{action_line} {message}", "state": await miniapp_state(user)})
        p = await get_player(user_id)
        previous_boss_phase = get_boss_phase(monster["boss"], battle["monster_hp"], monster["hp"])
        current_boss_phase = get_boss_phase(monster["boss"], new_enemy_hp, monster["hp"])
        enemy_tactic = choose_monster_tactic(monster["trait_effect"], turn_count, new_enemy_hp, monster["hp"], is_boss=monster["boss"], boss_phase=current_boss_phase)
        special_turn = enemy_tactic == "special"
        enemy_damage = calculate_enemy_damage(
            monster["attack_power"], p["level"], p["armor_defense"], class_stats["defense"],
            monster["speed"], random.randint(-3, 6),
            fury=monster["trait_effect"] == "fury" and new_enemy_hp <= int(monster["hp"] * 0.3),
            special=special_turn,
            boss_phase=current_boss_phase,
        )
        if monster["trait_effect"] == "berserk" and new_enemy_hp <= int(monster["hp"] * 0.5):
            enemy_damage = int(enemy_damage * 1.35)
        evaded = class_evades(class_stats["speed"], random.randint(1, 100))
        if evaded:
            enemy_damage = 0
        reflect_damage = max(1, damage // 5) if monster["trait_effect"] == "reflect" and action != "potion" else 0
        poison_damage = max(1, p["max_hp"] // 40) if monster["trait_effect"] == "poison" else 0
        new_hp = max(0, p["hp"] - enemy_damage - reflect_damage - poison_damage)
        effect_notes = []
        if current_boss_phase > previous_boss_phase:
            effect_notes.append(f"{monster['name']} enters BOSS PHASE {current_boss_phase}!")
        if evaded:
            effect_notes.append(f"Your {p['hero_class']} speed dodges the monster's strike.")
        if reflect_damage:
            effect_notes.append(f"Your strike is reflected for {reflect_damage} damage.")
        if poison_damage:
            effect_notes.append(f"Poison deals {poison_damage} damage.")
        if enemy_damage > 0 and monster["trait_effect"] == "drain":
            new_enemy_hp = min(monster["hp"], new_enemy_hp + max(1, enemy_damage // 10))
        elif enemy_damage > 0 and monster["trait_effect"] == "lifesteal":
            stolen = max(1, enemy_damage // 4)
            new_enemy_hp = min(monster["hp"], new_enemy_hp + stolen)
            effect_notes.append(f"The monster steals {stolen} HP.")
        await db.execute(
            "UPDATE battles SET monster_hp=?, turn_count=? WHERE user_id=?",
            (new_enemy_hp, turn_count, user_id),
        )
        await db.execute(
            "UPDATE players SET hp=?, skill_cd=max(0, skill_cd-1) WHERE user_id=?",
            (new_hp, user_id),
        )
        await db.commit()
        effect_text = " " + " ".join(effect_notes) if effect_notes else ""
        if new_hp == 0:
            message = await finish_battle(user_id, False)
            return web.json_response({
                "message": f"{action_line} {monster['name']} hits you for {enemy_damage}.{effect_text} {message}",
                "state": await miniapp_state(user),
            })
        enemy_text = (
            f"You evade {monster['name']}'s attack with your {p['hero_class']} speed!"
            if evaded else (
                f"{monster['name']} uses {monster['special_move']} and hits for {enemy_damage}!"
                if special_turn else f"{monster['name']} hits you for {enemy_damage}."
            )
        )
        enemy_text += effect_text
        return web.json_response({
            "message": f"{action_line} {enemy_text}",
            "state": await miniapp_state(user),
        })


async def start_web_server():
    async def serve_index(request: web.Request):
        return web.FileResponse(WEB_DIR / "index.html")

    async def serve_css(request: web.Request):
        return web.FileResponse(WEB_DIR / "style.css")

    async def serve_js(request: web.Request):
        return web.FileResponse(WEB_DIR / "game.js")

    async def healthz(request: web.Request):
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/", serve_index)
    app.router.add_get("/style.css", serve_css)
    app.router.add_get("/game.js", serve_js)
    app.router.add_get("/api/state", api_state)
    app.router.add_post("/api/explore", api_explore)
    app.router.add_post("/api/action", api_action)
    app.router.add_post("/api/appearance", api_appearance)
    app.router.add_get("/healthz", healthz)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    log.info("Mini App web server listening on %s:%s", WEB_HOST, WEB_PORT)
    return runner


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it to your .env file.")
    if WEBAPP_URL and not WEBAPP_URL.startswith("https://"):
        raise RuntimeError("WEBAPP_URL must use public HTTPS for Telegram Mini Apps.")
    await init_db()
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    runner = await start_web_server()
    log.info("Starting The Peak Adventure bot")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()
        if db:
            await db.close()


if __name__ == "__main__":
    asyncio.run(main())
