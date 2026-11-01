"""The Peak Adventure - Telegram turn-based RPG bot."""
import asyncio
from html import escape
import json
import logging
import os
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv
from aiohttp import web
from aiogram.types import WebAppInfo

from game_rules import validate_monster_catalogue
from telegram_auth import validate_init_data

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
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

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("peak-adventure")
dp = Dispatcher()
db: aiosqlite.Connection | None = None
player_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


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
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS battles (
      user_id INTEGER PRIMARY KEY, monster_level INTEGER NOT NULL,
      monster_hp INTEGER NOT NULL, message_id INTEGER,
      turn_count INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS daily_claims (
      user_id INTEGER PRIMARY KEY, claimed_on TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS boss_defeats (
      user_id INTEGER NOT NULL, monster_level INTEGER NOT NULL,
      defeated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id, monster_level)
    );
    CREATE TABLE IF NOT EXISTS quest_progress (
      user_id INTEGER NOT NULL, quest_id TEXT NOT NULL,
      progress INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0,
      claimed INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(user_id, quest_id)
    );
    CREATE INDEX IF NOT EXISTS idx_players_leaderboard ON players(level DESC, wins DESC);
    """)
    migrations = [
        "ALTER TABLE battles ADD COLUMN turn_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN hero_class TEXT NOT NULL DEFAULT 'Knight'",
        "ALTER TABLE players ADD COLUMN class_selected INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN weapon TEXT NOT NULL DEFAULT 'Rusty Sword'",
        "ALTER TABLE players ADD COLUMN weapon_attack INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN armor TEXT NOT NULL DEFAULT 'Traveler Clothes'",
        "ALTER TABLE players ADD COLUMN armor_defense INTEGER NOT NULL DEFAULT 0",
    ]
    for migration in migrations:
        try:
            await db.execute(migration)
        except aiosqlite.OperationalError:
            pass
    await db.commit()


async def get_player(user_id: int, username: str | None = None):
    assert db is not None
    await db.execute("INSERT OR IGNORE INTO players(user_id, username) VALUES (?, ?)", (user_id, username or "Adventurer"))
    if username:
        await db.execute("UPDATE players SET username=? WHERE user_id=?", (username, user_id))
    await db.commit()
    cur = await db.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
    return await cur.fetchone()


def menu():
    rows = [
        [InlineKeyboardButton(text="🗺️ Explore", callback_data="explore"),
         InlineKeyboardButton(text="👤 Profile", callback_data="profile")],
        [InlineKeyboardButton(text="🎒 Inventory", callback_data="inventory"),
         InlineKeyboardButton(text="📜 Quests", callback_data="quests")],
        [InlineKeyboardButton(text="🛒 Shop", callback_data="shop"),
         InlineKeyboardButton(text="🧙 Hero Class", callback_data="class_menu")],
        [InlineKeyboardButton(text="🎁 Daily Reward", callback_data="daily"),
         InlineKeyboardButton(text="🏆 Leaderboard", callback_data="leaderboard")],
    ]
    if WEBAPP_URL:
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
    return (f"👤 <b>{escape(p['username'] or 'Adventurer')}</b>\n"
            f"🧙 Class: <b>{p['hero_class']}</b>\n"
            f"⚔️ Weapon: <b>{p['weapon']}</b> (+{p['weapon_attack']} ATK)\n"
            f"🛡️ Armor: <b>{p['armor']}</b> (+{p['armor_defense']} DEF)\n"
            f"⭐ Level: <b>{p['level']}/100</b>\n"
            f"✨ XP: <b>{p['xp']}/{xp_needed(p['level'])}</b>\n"
            f"❤️ HP: <b>{p['hp']}/{p['max_hp']}</b>\n"
            f"🪙 Coins: <b>{p['coins']}</b>\n"
            f"🏆 Victories: <b>{p['wins']}</b>")


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
    if level in BOSS_LEVELS and not boss_defeated:
        monster_level = level
    else:
        candidates = [max(1, min(100, level + offset)) for offset in (-1, 0, 1)]
        candidates = [candidate for candidate in candidates if candidate not in BOSS_LEVELS]
        monster_level = random.choice(candidates or [max(1, level - 1)])
    m = MONSTER_BY_LEVEL[monster_level]
    await db.execute("UPDATE players SET skill_cd=0 WHERE user_id=?", (user_id,))
    await db.execute("INSERT INTO battles(user_id, monster_level, monster_hp) VALUES (?, ?, ?)",
                     (user_id, monster_level, m["hp"]))
    await db.commit()
    await send_battle(send_target, user_id, "🌲 <b>You enter the wilds...</b>")


async def start_battle(user_id: int, username: str | None, send_target):
    async with player_locks[user_id]:
        await _start_battle_unlocked(user_id, username, send_target)


async def claim_daily_reward(user_id: int) -> bool:
    assert db is not None
    async with player_locks[user_id]:
        today = datetime.now(timezone.utc).date().isoformat()
        cur = await db.execute("SELECT claimed_on FROM daily_claims WHERE user_id=?", (user_id,))
        previous = await cur.fetchone()
        if previous and previous["claimed_on"] == today:
            return False
        await db.execute("INSERT INTO daily_claims(user_id, claimed_on) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET claimed_on=excluded.claimed_on", (user_id, today))
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
        reply_markup=menu())


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
    p = await get_player(message.from_user.id)
    upper = min(100, p["level"] + 1)
    discovered = MONSTERS[:upper]
    lines = ["📚 <b>Monster Bestiary</b>"]
    for monster in discovered:
        marker = "👑" if monster["boss"] else "•"
        lines.append(f"{marker} Lv.{monster['level']} {monster['name']} · {monster['element']}")
    lines.append("\nUse /monster <code>level</code> for full details.")
    await message.answer("\n".join(lines))


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
        await message.answer("⏳ You have already claimed today's reward. Come back after the UTC day resets.")


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
        reply_markup=menu(),
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
    await call.message.answer(await player_text(p), reply_markup=menu())


@dp.callback_query(F.data == "inventory")
async def cb_inventory(call: CallbackQuery):
    await call.answer()
    p = await get_player(call.from_user.id)
    await call.message.answer(f"🎒 <b>Inventory</b>\n🧪 Potions: {p['potions']}\n🪙 Coins: {p['coins']}")


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
        await call.message.edit_text(result, reply_markup=menu())
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
        await db.execute("UPDATE players SET skill_cd=3 WHERE user_id=?", (user_id,))
        action_line = f"🔥 <b>{class_stats['skill']}!</b> You deal {damage} damage."
    else:
        damage = max(8, p["level"] * 10 + class_stats["attack"] + p["weapon_attack"] + random.randint(5, 18) - m["defense"] // 3)
        action_line = f"⚔️ You strike for {damage} damage."
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
    new_enemy_hp = max(0, b["monster_hp"] - damage)
    turn_count = b["turn_count"] + 1
    if new_enemy_hp > 0 and m["trait_effect"] == "regenerate":
        regen = max(1, m["hp"] // 50)
        new_enemy_hp = min(m["hp"], new_enemy_hp + regen)
    if new_enemy_hp == 0:
        await db.execute("UPDATE players SET hp=min(max_hp, hp+15), skill_cd=max(0, skill_cd-1) WHERE user_id=?", (user_id,))
        await db.commit()
        result = await finish_battle(user_id, True)
        await call.message.edit_text(f"{action_line}\n\n{result}", reply_markup=menu())
        return
    p = await get_player(user_id)
    enemy_damage = max(3, m["attack_power"] - p["level"] * 2 - p["armor_defense"] + class_stats["defense"] + m["speed"] // 12 + random.randint(-3, 6))
    if m["trait_effect"] == "fury" and new_enemy_hp <= int(m["hp"] * 0.3):
        enemy_damage = int(enemy_damage * 1.25)
    special_turn = turn_count % (2 if m["trait_effect"] == "swift" else 3) == 0
    if special_turn:
        enemy_damage = int(enemy_damage * 1.5)
    new_hp = max(0, p["hp"] - enemy_damage)
    if m["trait_effect"] == "drain":
        new_enemy_hp = min(m["hp"], new_enemy_hp + max(1, enemy_damage // 10))
    await db.execute("UPDATE battles SET monster_hp=?, turn_count=? WHERE user_id=?", (new_enemy_hp, turn_count, user_id))
    await db.execute("UPDATE players SET hp=?, skill_cd=max(0, skill_cd-1) WHERE user_id=?", (new_hp, user_id))
    await db.commit()
    if new_hp == 0:
        result = await finish_battle(user_id, False)
        await call.message.edit_text(f"{action_line}\n💥 {m['name']} hits you for {enemy_damage}.\n\n{result}", reply_markup=menu())
        return
    enemy_action = f"💥 {m['name']} uses {m['special_move']} and hits for {enemy_damage}!" if special_turn else f"💥 {m['name']} hits you for {enemy_damage}."
    await send_battle(call.message, user_id, f"{action_line}\n{enemy_action}", edit=True)


@dp.callback_query(F.data.startswith("battle:"))
async def battle_action(call: CallbackQuery):
    async with player_locks[call.from_user.id]:
        await _battle_action_unlocked(call)


async def api_state(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    user_id = user["id"]
    p = await get_player(user_id, user.get("username") or user.get("first_name") or "Adventurer")
    region_names = [
        "Whispering Meadow", "Ashen Desert", "Stormglass Highlands", "Hollow Kingdom",
        "Ember Abyss", "Frostfang Peaks", "Primordial Rift", "Celestial Ruins",
        "Eternal Hour", "Origin Realm",
    ]
    region_index = min(9, (p["level"] - 1) // 10)
    monster_level = p["level"]
    if p["level"] in BOSS_LEVELS:
        cur = await db.execute(
            "SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?",
            (user_id, p["level"]),
        )
        boss_is_defeated = await cur.fetchone() is not None
        if boss_is_defeated:
            monster_level = p["level"] - 1 if p["level"] == 100 else p["level"] + 1
    monster = MONSTER_BY_LEVEL[monster_level]
    return web.json_response({
        "first_name": user.get("first_name") or user.get("username") or "Adventurer",
        "class_selected": bool(p["class_selected"]),
        "hero_class": p["hero_class"],
        "weapon": p["weapon"],
        "level": p["level"],
        "xp": p["xp"],
        "xp_required": xp_needed(p["level"]),
        "hp": p["hp"],
        "max_hp": p["max_hp"],
        "coins": p["coins"],
        "region": region_names[region_index],
        "monster": {"name": monster["name"], "level": monster["level"], "element": monster["element"]},
    })


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", lambda request: web.FileResponse(WEB_DIR / "index.html"))
    app.router.add_get("/style.css", lambda request: web.FileResponse(WEB_DIR / "style.css"))
    app.router.add_get("/game.js", lambda request: web.FileResponse(WEB_DIR / "game.js"))
    app.router.add_get("/api/state", api_state)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    log.info("Mini App web server listening on %s:%s", WEB_HOST, WEB_PORT)
    return runner


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it to your .env file.")
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
