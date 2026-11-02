"""The Peak Adventure - Telegram turn-based RPG bot."""
import asyncio
import time
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
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, LabeledPrice, PreCheckoutQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv
from aiohttp import web
from aiogram.types import WebAppInfo

from game_rules import get_boss_phase, resolve_enemy_turn, resolve_player_attack, skill_cooldown_for_class, validate_monster_catalogue
from telegram_auth import validate_init_data
from friend_system import FriendError, init_friend_tables, list_friends, list_pending_friend_requests, remove_friend, respond_to_friend_request, search_players, send_friend_request
from party_system import PartyError, create_party, disband_party, get_party_info, init_party_tables, invite_to_party, leave_party, list_pending_party_invites, respond_to_party_invite, start_party_battle, attack_party_battle, get_party_battle, reward_party_battle
from group_system import GroupError, attack_group_raid, award_group_xp, claim_group_mission, get_group_missions, get_group_profile, group_raid_status, init_group_tables, is_group_admin, is_group_banned, list_group_players, record_group_activity, record_group_player, register_group, set_group_admin, set_group_ban, start_group_raid, top_groups
from admin_tools import AdminError, adjust_player_coins, dashboard_stats, export_player_data, init_admin_tables, parse_admin_ids, recent_admin_actions, record_admin_action
from character_system import AppearanceError, get_appearance, init_character_tables, save_appearance
from account_system import AccountError, delete_player_account, get_settings, init_account_tables, update_settings
from guild_system import GuildFeatureError, attack_guild_raid, claim_guild_mission, create_guild_invite, get_guild_announcement, get_guild_chat, get_guild_missions, init_guild_features, record_guild_activity, respond_guild_invite, set_guild_announcement, set_guild_role, start_guild_raid, guild_raid_status, declare_guild_war, get_guild_war, record_guild_war_duel, respond_guild_war, send_guild_message, list_pending_guild_invites
from world_system import WORLD_NAMES, WorldError, discover_world_landmark, get_current_world, get_world_choices, get_world_landmark, init_world_tables, travel_to_world, world_encounter_levels
from dungeon_system import DungeonError, abandon_dungeon, advance_dungeon, available_dungeons, claim_dungeon_reward, enter_dungeon, get_dungeon_state, init_dungeon_tables
from crafting_system import MATERIALS, CraftingError, award_material_drop, craft_item, get_materials, init_crafting_tables, list_recipes
from presence_system import count_online_players, init_presence_tables, list_online_friends, touch_presence
from story_system import CHAPTERS, StoryError, choose_story_path, claim_story_reward, get_story_chapters, init_story_tables
from auction_system import AuctionError, cancel_listing, create_listing, equip_stashed_item, init_auction_tables, list_active_auctions, list_stash, place_bid
from rate_limit import SlidingWindowRateLimiter
from db_backup import create_backup
from stamina_system import EXPLORE_COST, StaminaError, get_stamina, init_stamina_tables, consume_stamina
from report_system import ReportError, init_report_tables, list_open_reports, resolve_player_report, submit_player_report
from weekly_quest_system import WeeklyQuestError, claim_weekly_reward, get_weekly_quests, init_weekly_tables, record_weekly_progress
from daily_mission_system import DailyMissionError, claim_daily_mission, get_daily_missions, init_daily_mission_tables, record_daily_progress
from roaming_event_system import RoamingEventError, attack_roaming_event, claim_roaming_event_reward, get_or_create_roaming_event, init_roaming_event_tables
from moderation_system import ModerationError, ban_player, get_active_ban, init_moderation_tables, unban_player
from mana_system import ManaError, SKILL_MANA_COST, TURN_MANA_REGEN, consume_mana, get_mana, init_mana_tables, restore_mana
from elite_system import is_elite_spawn, scale_elite_monster
from security_system import get_security_events, get_suspicious_players, init_security_tables, record_security_event
from premium_system import PREMIUM_SHOP_ITEMS, PremiumError, buy_premium_item, consume_xp_boost, credit_premium_purchase, get_premium_balance, get_premium_packages, init_premium_tables, make_invoice_payload, parse_invoice_payload
from evolution_system import EvolutionError, get_evolution_state, init_evolution_tables, is_evolved_spawn, record_monster_defeat, scale_evolved_monster
from secret_area_system import SecretAreaError, discover_secret_area, get_secret_area_state, init_secret_area_tables

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
PREMIUM_PAYMENTS_ENABLED = os.getenv("ENABLE_TELEGRAM_STARS", "false").strip().lower() in {"1", "true", "yes", "on"}
ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))
DB_PATH = os.getenv("DATABASE_PATH", "peak_adventure.db")
BACKUP_DIR = os.getenv("BACKUP_DIR", str(Path(DB_PATH).parent / "backups"))
BACKUP_INTERVAL_SECONDS = max(3600, int(os.getenv("BACKUP_INTERVAL_SECONDS", "21600")))
BACKUP_RETENTION = max(1, int(os.getenv("BACKUP_RETENTION", "7")))
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

@dp.errors()
async def handle_unhandled_error(event):
    """Log unexpected Telegram update failures without exposing internals to players."""
    error = event.exception
    log.error(
        "Unhandled Telegram update error: %s",
        type(error).__name__,
        exc_info=(type(error), error, error.__traceback__),
    )
    return True


db: aiosqlite.Connection | None = None
db_lock = asyncio.Lock()
player_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


class DatabaseLockMiddleware:
    async def __call__(self, handler, event, data):
        async with db_lock:
            sender = getattr(event, "event_from_user", None) or getattr(event, "from_user", None)
            if db is not None and sender and sender.id not in ADMIN_IDS:
                ban = await get_active_ban(db, sender.id)
                if ban:
                    notice = "⛔ Your game account is suspended. Reason: " + escape(ban["reason"])
                    message = getattr(event, "message", None) or getattr(event, "edited_message", None)
                    callback = getattr(event, "callback_query", None)
                    if message is not None:
                        await message.answer(notice)
                    elif callback is not None:
                        await callback.answer("Your game account is suspended.", show_alert=True)
                    return None
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
      turn_count INTEGER NOT NULL DEFAULT 0, is_elite INTEGER NOT NULL DEFAULT 0, is_evolved INTEGER NOT NULL DEFAULT 0
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
        "ALTER TABLE battles ADD COLUMN is_elite INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE battles ADD COLUMN is_evolved INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE daily_claims ADD COLUMN claimed_at INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN hero_class TEXT NOT NULL DEFAULT 'Knight'",
        "ALTER TABLE players ADD COLUMN class_selected INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN weapon TEXT NOT NULL DEFAULT 'Rusty Sword'",
        "ALTER TABLE players ADD COLUMN weapon_attack INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN armor TEXT NOT NULL DEFAULT 'Traveler Clothes'",
        "ALTER TABLE players ADD COLUMN armor_defense INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN pvp_wins INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN pvp_losses INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE trades ADD COLUMN initiator_weapon TEXT",
        "ALTER TABLE trades ADD COLUMN initiator_weapon_attack INTEGER",
        "ALTER TABLE trades ADD COLUMN initiator_armor TEXT",
        "ALTER TABLE trades ADD COLUMN initiator_armor_defense INTEGER",
        "ALTER TABLE trades ADD COLUMN partner_weapon TEXT",
        "ALTER TABLE trades ADD COLUMN partner_weapon_attack INTEGER",
        "ALTER TABLE trades ADD COLUMN partner_armor TEXT",
        "ALTER TABLE trades ADD COLUMN partner_armor_defense INTEGER",
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
    await init_account_tables(db)
    await init_admin_tables(db)
    await init_guild_features(db)
    await init_world_tables(db)
    await init_dungeon_tables(db)
    await init_crafting_tables(db)
    await init_presence_tables(db)
    await init_story_tables(db)
    await init_auction_tables(db)
    await init_stamina_tables(db)
    await init_report_tables(db)
    await init_weekly_tables(db)
    await init_daily_mission_tables(db)
    await init_roaming_event_tables(db)
    await init_evolution_tables(db)
    await init_secret_area_tables(db)
    await init_security_tables(db)
    await init_premium_tables(db)
    await init_moderation_tables(db)
    await init_mana_tables(db)


async def get_player(user_id: int, username: str | None = None):
    """Read/update a player without committing a transaction owned by the caller."""
    assert db is not None
    nested = db.in_transaction
    if nested:
        await db.execute("SAVEPOINT get_player")
    try:
        await db.execute(
            "INSERT OR IGNORE INTO players(user_id, username) VALUES (?, ?)",
            (user_id, username or "Adventurer"),
        )
        if username:
            await db.execute("UPDATE players SET username=? WHERE user_id=?", (username, user_id))
        cur = await db.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
        player = await cur.fetchone()
        await touch_presence(db, user_id)
        if nested:
            await db.execute("RELEASE SAVEPOINT get_player")
        else:
            await db.commit()
        return player
    except Exception:
        if nested:
            await db.execute("ROLLBACK TO SAVEPOINT get_player")
            await db.execute("RELEASE SAVEPOINT get_player")
        else:
            await db.rollback()
        raise


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
        [InlineKeyboardButton(text="🏰 Guild", callback_data="guild_info"), InlineKeyboardButton(text="🌐 Online", callback_data="online")],
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


def build_battle_monster(battle):
    """Build the exact evolved/elite variant stored for this encounter."""
    monster = dict(MONSTER_BY_LEVEL[battle["monster_level"]])
    monster["is_evolved"] = bool(battle["is_evolved"])
    monster["is_elite"] = bool(battle["is_elite"])
    if monster["is_evolved"]:
        monster = scale_evolved_monster(monster)
    if monster["is_elite"]:
        monster = scale_elite_monster(monster)
    return monster


async def send_battle(target, user_id: int, intro: str = "", edit: bool = False):
    assert db is not None
    cur = await db.execute("SELECT * FROM battles WHERE user_id=?", (user_id,))
    battle = await cur.fetchone()
    p = await get_player(user_id)
    if not battle:
        return
    m = build_battle_monster(battle)
    monster_flags = "👑 BOSS" if m["boss"] else " · ".join(
        label for label, enabled in (("💀 ELITE", battle["is_elite"]), ("✨ EVOLVED", battle["is_evolved"]))
        if enabled
    )
    text = (f"{intro}\n\n" if intro else "") + (
        f"⚔️ <b>ENCOUNTER: {m['name']}</b>\n"
        f"🏷️ Monster level: {m['level']} {monster_flags}\\n"
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
    try:
        await consume_stamina(db, user_id, EXPLORE_COST)
    except StaminaError as exc:
        state = await get_stamina(db, user_id)
        await send_target.answer("⚡ " + escape(str(exc)) + f"\\nStamina: {state['stamina']}/{state['max_stamina']}. Regeneration: 1 every 5 minutes.")
        return
    world_id = await get_current_world(db, user_id, p["level"])
    boss_level = world_id * 10
    boss_defeated = False
    if p["level"] >= boss_level and boss_level in BOSS_LEVELS:
        cur = await db.execute("SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?", (user_id, boss_level))
        boss_defeated = await cur.fetchone() is not None
    monster_level = random.choice(world_encounter_levels(p["level"], world_id, boss_defeated))
    m = MONSTER_BY_LEVEL[monster_level]
    mastery = await get_evolution_state(db, user_id, monster_level)
    evolved = is_evolved_spawn(mastery["evolved"] and not m["boss"], random.randint(1, 100))
    elite = is_elite_spawn(m["boss"], random.randint(1, 100))
    battle_monster = scale_evolved_monster(m) if evolved else m
    if elite:
        battle_monster = scale_elite_monster(battle_monster)
    await db.execute("UPDATE players SET skill_cd=0 WHERE user_id=?", (user_id,))
    await db.execute("INSERT INTO battles(user_id, monster_level, monster_hp, is_elite, is_evolved) VALUES (?, ?, ?, ?, ?)",
                     (user_id, monster_level, battle_monster["hp"], int(elite), int(evolved)))
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
    m = build_battle_monster(b)
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
    if b["is_elite"] or b["is_evolved"]:
        reward_xp = int(reward_xp * (1.5 if b["is_elite"] else 1.0) * (1.5 if b["is_evolved"] else 1.0))
        reward_coins = int(reward_coins * (1.5 if b["is_elite"] else 1.0) * (1.5 if b["is_evolved"] else 1.0))
    xp_boosted = await consume_xp_boost(db, user_id)
    if xp_boosted:
        reward_xp *= 2
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
    evolution = await record_monster_defeat(db, user_id, b["monster_level"])
    await advance_dungeon(db, user_id, m["level"])
    await award_material_drop(db, user_id, m)
    await record_weekly_progress(db, user_id, "wins")
    await record_daily_progress(db, user_id, "wins")
    if m["boss"]:
        await record_weekly_progress(db, user_id, "bosses")
    await record_player_guild_activity(user_id, "boss" if m["boss"] else "battle")
    await db.commit()
    await refresh_quest_progress(user_id)
    level_note = f"\\n🌟 LEVEL UP! You reached level {new_level}." if new_level > p["level"] else ""
    boss_note = "\\n👑 Boss seal broken! The next region is now within reach." if m["boss"] else ""
    evolution_note = (
        "\\n✨ Mastery complete! This monster's evolved form can now appear."
        if evolution["evolved"] and evolution["defeats"] == 5 else ""
    )
    xp_boost_note = "\\n💎 XP Charm doubled this victory's XP." if xp_boosted else ""
    return f"🏆 <b>Victory!</b> {m['name']} defeated.\\n✨ +{reward_xp} XP\\n🪙 +{reward_coins} coins{level_note}{boss_note}{evolution_note}{xp_boost_note}"


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


class TradeSettlementConflict(Exception):
    """Raised when a trade participant cannot be updated during settlement."""


async def settle_trade_assets(db, trade, initiator, partner):
    """Apply both sides of a trade atomically; never leave a one-sided transfer."""
    savepoint = "trade_settlement"
    await db.execute(f"SAVEPOINT {savepoint}")
    try:
        initiator_weapon = (
            (trade["partner_weapon"], trade["partner_weapon_attack"])
            if trade["initiator_weapon"] else (initiator["weapon"], initiator["weapon_attack"])
        )
        partner_weapon = (
            (trade["initiator_weapon"], trade["initiator_weapon_attack"])
            if trade["partner_weapon"] else (partner["weapon"], partner["weapon_attack"])
        )
        initiator_armor = (
            (trade["partner_armor"], trade["partner_armor_defense"])
            if trade["initiator_armor"] else (initiator["armor"], initiator["armor_defense"])
        )
        partner_armor = (
            (trade["initiator_armor"], trade["initiator_armor_defense"])
            if trade["partner_armor"] else (partner["armor"], partner["armor_defense"])
        )
        cur = await db.execute(
            """UPDATE players SET coins=coins-?+?,potions=potions-?+?,
               weapon=?,weapon_attack=?,armor=?,armor_defense=? WHERE user_id=?""",
            (trade["initiator_coins"],trade["partner_coins"],trade["initiator_potions"],trade["partner_potions"],
             initiator_weapon[0],initiator_weapon[1],initiator_armor[0],initiator_armor[1],trade["initiator_id"]),
        )
        if cur.rowcount != 1:
            raise TradeSettlementConflict("The initiating player account could not be updated.")
        cur = await db.execute(
            """UPDATE players SET coins=coins-?+?,potions=potions-?+?,
               weapon=?,weapon_attack=?,armor=?,armor_defense=? WHERE user_id=?""",
            (trade["partner_coins"],trade["initiator_coins"],trade["partner_potions"],trade["initiator_potions"],
             partner_weapon[0],partner_weapon[1],partner_armor[0],partner_armor[1],trade["partner_id"]),
        )
        if cur.rowcount != 1:
            raise TradeSettlementConflict("The receiving player account could not be updated.")
        cur = await db.execute(
            "UPDATE trades SET status='completed' WHERE trade_id=? AND status='open'",
            (trade["trade_id"],),
        )
        if cur.rowcount != 1:
            raise TradeSettlementConflict("The trade is no longer open for settlement.")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        return True
    except TradeSettlementConflict:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        await db.execute(
            """UPDATE trades SET initiator_confirmed=0,partner_confirmed=0
               WHERE trade_id=? AND status='open'""",
            (trade["trade_id"],),
        )
        return False
    except Exception:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise


async def trade_summary(trade):
    initiator = await get_player(trade["initiator_id"])
    partner = await get_player(trade["partner_id"])
    return (
        "🤝 <b>Trade #" + str(trade["trade_id"]) + "</b> · " + trade["status"].upper() + "\n"
        + "<b>" + escape(initiator["username"] or "Player 1") + "</b> offers: "
        + str(trade["initiator_coins"]) + " coins, " + str(trade["initiator_potions"]) + " potions, "
        + escape(trade["initiator_weapon"] or "no weapon") + ", " + escape(trade["initiator_armor"] or "no armor") + "\n"
        + "<b>" + escape(partner["username"] or "Player 2") + "</b> offers: "
        + str(trade["partner_coins"]) + " coins, " + str(trade["partner_potions"]) + " potions, "
        + escape(trade["partner_weapon"] or "no weapon") + ", " + escape(trade["partner_armor"] or "no armor") + "\n"
        + "Confirmations: " + ("✅" if trade["initiator_confirmed"] else "⌛") + " / "
        + ("✅" if trade["partner_confirmed"] else "⌛")
    )


@dp.message(Command("trade"))
async def create_trade(message: Message):
    if message.chat.type not in {"group", "supergroup"} or not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("Reply to another player's message in a group, then send /trade.")
        return
    initiator_id = message.from_user.id
    await expire_stale_trades()
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
    await expire_stale_trades()
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
    await expire_stale_trades()
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
    if len(message.command) not in {4, 5, 6} or not all(part.isdigit() for part in message.command[1:4]):
        await message.answer("Usage: /offer trade_id coins potions [weapon_name|none] [armor_name|none]. Use underscores for spaces.")
        return
    trade_id, coins, potions = map(int, message.command[1:4])
    await expire_stale_trades()
    weapon_token = message.command[4] if len(message.command) >= 5 else "none"
    armor_token = message.command[5] if len(message.command) >= 6 else "none"
    weapon = None if weapon_token.lower() == "none" else weapon_token.replace("_", " ")
    armor = None if armor_token.lower() == "none" else armor_token.replace("_", " ")
    cur = await db.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,))
    trade = await cur.fetchone()
    if not trade or trade["status"] != "open":
        await message.answer("That trade is not open.")
        return
    user_id = message.from_user.id
    if user_id not in {trade["initiator_id"], trade["partner_id"]}:
        await message.answer("You are not part of this trade.")
        return
    player = await get_player(user_id, message.from_user.username)
    if coins > player["coins"] or potions > player["potions"]:
        await message.answer("Your offer exceeds your current coins or potions.")
        return
    if weapon and weapon != player["weapon"]:
        await message.answer("You can only offer the weapon currently equipped by your hero.")
        return
    if armor and armor != player["armor"]:
        await message.answer("You can only offer the armor currently equipped by your hero.")
        return
    weapon_attack = player["weapon_attack"] if weapon else None
    armor_defense = player["armor_defense"] if armor else None
    if user_id == trade["initiator_id"]:
        await db.execute("""UPDATE trades SET initiator_coins=?,initiator_potions=?,
          initiator_weapon=?,initiator_weapon_attack=?,initiator_armor=?,initiator_armor_defense=?,
          initiator_confirmed=0,partner_confirmed=0 WHERE trade_id=?""",
          (coins,potions,weapon,weapon_attack,armor,armor_defense,trade_id))
    else:
        await db.execute("""UPDATE trades SET partner_coins=?,partner_potions=?,
          partner_weapon=?,partner_weapon_attack=?,partner_armor=?,partner_armor_defense=?,
          initiator_confirmed=0,partner_confirmed=0 WHERE trade_id=?""",
          (coins,potions,weapon,weapon_attack,armor,armor_defense,trade_id))
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
    await expire_stale_trades()
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

        if bool(trade["initiator_weapon"]) != bool(trade["partner_weapon"]) or bool(trade["initiator_armor"]) != bool(trade["partner_armor"]):
            await db.execute("UPDATE trades SET initiator_confirmed=0,partner_confirmed=0 WHERE trade_id=?", (trade_id,))
            await db.commit()
            await message.answer("Equipment must be exchanged slot-for-slot. Both players must offer a weapon or both leave weapon empty; same for armor.")
            return
        if (trade["initiator_weapon"] and (initiator["weapon"] != trade["initiator_weapon"] or initiator["weapon_attack"] != trade["initiator_weapon_attack"])) or (trade["partner_weapon"] and (partner["weapon"] != trade["partner_weapon"] or partner["weapon_attack"] != trade["partner_weapon_attack"])) or (trade["initiator_armor"] and (initiator["armor"] != trade["initiator_armor"] or initiator["armor_defense"] != trade["initiator_armor_defense"])) or (trade["partner_armor"] and (partner["armor"] != trade["partner_armor"] or partner["armor_defense"] != trade["partner_armor_defense"])):
            await db.execute("UPDATE trades SET initiator_confirmed=0,partner_confirmed=0 WHERE trade_id=?", (trade_id,))
            await db.commit()
            await message.answer("Trade paused: one equipped item changed. Update your offers and confirm again.")
            return
        if (initiator["coins"] < trade["initiator_coins"] or initiator["potions"] < trade["initiator_potions"]
                or partner["coins"] < trade["partner_coins"] or partner["potions"] < trade["partner_potions"]):
            await db.execute(
                "UPDATE trades SET initiator_confirmed=0, partner_confirmed=0 WHERE trade_id=?",
                (trade_id,),
            )
            await db.commit()
            await message.answer("Trade paused: one player's balance changed. Update your offers and confirm again.")
            return
        if not await settle_trade_assets(db, trade, initiator, partner):
            await db.commit()
            await message.answer("Trade paused because an account changed during settlement. Both offers remain intact; confirm again after checking the trade.")
            return
        await db.commit()
        if trade["chat_id"] < 0:
            try:
                await record_group_activity(db,trade["chat_id"],"trade")
                await award_group_xp(db,trade["chat_id"],10)
            except GroupError:
                pass
        await record_player_guild_activity(trade["initiator_id"], "trade")
        await record_player_guild_activity(trade["partner_id"], "trade")
        await message.answer(f"✅ Trade #{trade_id} completed. Items and coins have been exchanged.")
        return
    await message.answer((await trade_summary(trade)) + "\nWaiting for the other player to confirm.")


@dp.message(Command("canceltrade"))
async def cancel_trade(message: Message):
    if len(message.command) != 2 or not message.command[1].isdigit():
        await message.answer("Usage: <code>/canceltrade trade_id</code>.")
        return
    trade_id = int(message.command[1])
    await expire_stale_trades()
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


@dp.message(Command("players"))
async def search_players_command(message: Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /players username\\nOnly public profiles and profiles visible to your friends appear.")
        return
    try:
        rows = await search_players(db, message.from_user.id, args[1])
    except FriendError as exc:
        await message.answer(escape(str(exc)))
        return
    if not rows:
        await message.answer("No visible players matched that search.")
        return
    lines = ["🔎 <b>Player Search</b>"]
    for row in rows:
        lines.append(
            f"👤 <b>{escape(row['username'] or 'Adventurer')}</b> · Lv.{row['level']} · "
            f"ID <code>{row['user_id']}</code>"
        )
    lines.append("To add someone, reply to their message in a shared group and use /friend request.")
    await message.answer("\\n".join(lines))


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
    if action in {"create", "invite", "accept", "battle", "explore"} and not player["class_selected"]:
        await message.answer("Choose your hero class with /class before joining a party.")
        return
    try:

        if action == "explore":
            party, members = await get_party_info(db, user_id)
            if party["leader_id"] != user_id:
                raise PartyError("Only the party leader can start a shared exploration.")
            world_id = await get_current_world(db, user_id, player["level"])
            boss_level = world_id * 10
            boss_defeated = False
            if player["level"] >= boss_level and boss_level in BOSS_LEVELS:
                cur = await db.execute(
                    "SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?",
                    (user_id, boss_level),
                )
                boss_defeated = await cur.fetchone() is not None
            monster_level = random.choice(world_encounter_levels(player["level"], world_id, boss_defeated))
            monster = MONSTER_BY_LEVEL[monster_level]
            existing_battle = await get_party_battle(db, party["party_id"])
            if existing_battle and existing_battle["status"] == "active":
                raise PartyError("Your party already has an active co-op encounter.")
            try:
                await consume_stamina(db, user_id, EXPLORE_COST)
            except StaminaError as exc:
                state = await get_stamina(db, user_id)
                await message.answer(escape(str(exc)) + f"\\nStamina: {state['stamina']}/{state['max_stamina']}.")
                return
            battle_id = await start_party_battle(
                db, party["party_id"], user_id, monster_level, monster["name"],
                monster["hp"] * max(2, len(members) * 2),
            )
            notice = (
                f"🧭 <b>Party expedition #{battle_id}</b>\\n"
                f"{escape(monster['name'])} · Lv.{monster_level} · World {world_id}\\n"
                "The party has found a shared encounter. Use /party battle attack to fight."
            )
            await message.answer(notice)
            for member in members:
                if member["user_id"] == user_id:
                    continue
                try:
                    await message.bot.send_message(member["user_id"], notice)
                except Exception:
                    pass
            return

        if action.startswith("battle"):
            parts = (message.text or "").split()
            sub = parts[2].lower() if len(parts) > 2 else "status"
            party, members = await get_party_info(db, user_id)
            party_id = party["party_id"]
            if sub == "start":
                level = min(100, max(10, ((player["level"] + 9) // 10) * 10))
                boss = MONSTER_BY_LEVEL[level]
                battle_id = await start_party_battle(db, party_id, user_id, level, boss["name"], boss["hp"] * max(2, len(members) * 2))
                await message.answer(f"🐉 <b>Co-op Raid #{battle_id}</b>\n{escape(boss['name'])} · Lv.{level}\nAll party members can use /party battle attack.")
                return
            if sub == "attack":
                result = await attack_party_battle(db, party_id, user_id, max(1, player["level"] * 5 + player["weapon_attack"]))
                if result["status"] == "won":
                    for member_id in result["members"]:
                        try:
                            member_player = await get_player(member_id)
                            coins = max(20, member_player["level"] * 10)
                            xp = max(40, member_player["level"] * 20)
                            reward = await reward_party_battle(db, result["battle_id"], member_id, coins, xp)
                            try:
                                await message.bot.send_message(member_id, "🏆 Party raid cleared! You received +" + str(reward["coins"]) + " coins and +" + str(reward["xp"]) + " XP.")
                            except Exception:
                                pass
                        except PartyError:
                            pass
                await message.answer("⚔️ " + escape(result["monster_name"]) + ": " + str(result["hp"]) + "/" + str(result["max_hp"]) + " HP. Damage: " + str(result["damage"]) + ("\n🏆 PARTY RAID CLEARED! Rewards sent to party members." if result["status"] == "won" else ""))
                return
            battle = await get_party_battle(db, party_id)
            await message.answer("No co-op battle yet. Party leader can use /party battle start." if not battle else "🐉 " + escape(battle["monster_name"]) + ": " + str(battle["hp"]) + "/" + str(battle["max_hp"]) + " HP · " + battle["status"].upper())
            return
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
        "<code>/party info</code>, <code>/party explore</code>, <code>/party battle start|status|attack</code>, <code>/party leave</code>, <code>/party disband</code>."
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

async def verify_live_group_admin(message: Message) -> bool:
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        member = await message.bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    if member.status not in {"creator", "administrator"}:
        await db.execute("DELETE FROM group_admins WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await db.commit()
        return False
    return True


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
            if not await verify_live_group_admin(message): raise GroupError("Your Telegram administrator role is no longer active.")
            coins,xp=await claim_group_mission(db,cid,uid,args[2].lower())
            await db.execute("UPDATE players SET coins=coins+? WHERE user_id=?",(coins,uid)); await db.commit()
            await message.answer(f"🎁 Claimed {coins} coins and {xp} group XP.")
        except GroupError as exc: await message.answer(escape(str(exc)))
        return
    if action=="raid":
        parts=(message.text or "").split(); sub=parts[2].lower() if len(parts)>2 else "status"
        if sub=="start":
            try:
                if not await verify_live_group_admin(message) or not await is_group_admin(db,cid,uid): raise GroupError("Only current, verified Telegram group admins can start a raid.")
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
            if not await verify_live_group_admin(message): raise GroupError("Only current Telegram group admins can moderate players.")
            await set_group_ban(db,cid,uid,int(args[2]),action=="ban"," ".join(args[3:]))
            await message.answer("Player blocked from group game features." if action=="ban" else "Player unblocked.")
        except GroupError as exc: await message.answer(escape(str(exc)))
        return
    await message.answer("Commands: /group register, info, members, missions, claim ID, raid start|status|attack, ban|unban ID, top.")


async def record_player_guild_activity(user_id: int, kind: str):
    cur = await db.execute("SELECT guild_id FROM guild_members WHERE user_id=?", (user_id,))
    membership = await cur.fetchone()
    if membership:
        try:
            await record_guild_activity(db, membership["guild_id"], user_id, kind)
        except GuildFeatureError:
            pass


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

    announcement = await get_guild_announcement(db, guild_id)
    if announcement:
        lines.append(f"📢 <b>Guild Announcement</b>\n{escape(announcement['message'])}")
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


    if action == "invite":
        if not membership or len(args) < 3 or not args[2].isdigit():
            await message.answer("Usage: /guild invite player_id")
            return
        try:
            invite_id = await create_guild_invite(db, membership["guild_id"], user_id, int(args[2]))
            await message.answer(f"✉️ Guild invitation #{invite_id} sent to player {args[2]}. They can use /guild accept {invite_id}.")
        except GuildFeatureError as exc:
            await message.answer(escape(str(exc)))
        return

    if action in {"accept", "decline"}:
        if len(args) < 3 or not args[2].isdigit():
            await message.answer("Usage: /guild accept|decline invite_id")
            return
        try:
            guild_id = await respond_guild_invite(db, int(args[2]), user_id, action == "accept")
            await message.answer("✅ You joined the guild." if action == "accept" else "Guild invitation declined.")
        except GuildFeatureError as exc:
            await message.answer(escape(str(exc)))
        return

    if action == "role":
        if not membership or len(args) < 3:
            await message.answer("Usage: /guild role player_id officer|member")
            return
        parts = args[2].split()
        if len(parts) != 2 or not parts[0].isdigit():
            await message.answer("Usage: /guild role player_id officer|member")
            return
        try:
            await set_guild_role(db, membership["guild_id"], user_id, int(parts[0]), parts[1].lower())
            await message.answer("Guild role updated.")
        except GuildFeatureError as exc:
            await message.answer(escape(str(exc)))
        return

    if action == "chat":
        if not membership or len(args) < 3:
            await message.answer("Usage: /guild chat your message")
            return
        try:
            text_value = " ".join(args[2].split())
            message_id = await send_guild_message(db, membership["guild_id"], user_id, text_value)
            cur = await db.execute("SELECT user_id FROM guild_members WHERE guild_id=?", (membership["guild_id"],))
            recipients = [row["user_id"] for row in await cur.fetchall() if row["user_id"] != user_id]
            delivered = 0
            for recipient in recipients:
                try:
                    await message.bot.send_message(recipient, "💬 <b>Guild Chat</b>\n" + escape(p["username"] or "Adventurer") + ": " + escape(text_value))
                    delivered += 1
                except Exception:
                    pass
            await message.answer(f"💬 Message #{message_id} saved. Delivered to {delivered} guild members.")
        except GuildFeatureError as exc:
            await message.answer(escape(str(exc)))
        return

    if action == "history":
        if not membership:
            await message.answer("Join a guild first.")
            return
        try:
            rows = await get_guild_chat(db, membership["guild_id"], user_id, 10)
            lines = ["💬 <b>Recent Guild Chat</b>"]
            lines.extend(f"{escape(row['username'] or 'Adventurer')}: {escape(row['message'])}" for row in rows)
            await message.answer("\n".join(lines) if rows else "No guild chat messages yet.")
        except GuildFeatureError as exc:
            await message.answer(escape(str(exc)))
        return

    if action == "announce":
        if not membership or len(args) < 3:
            await message.answer("Usage: /guild announce your message")
            return
        try:
            text_value = await set_guild_announcement(db, membership["guild_id"], user_id, args[2])
            cur = await db.execute("SELECT user_id FROM guild_members WHERE guild_id=?", (membership["guild_id"],))
            recipients = [row["user_id"] for row in await cur.fetchall()]
            delivered = 0
            for recipient in recipients:
                if recipient == user_id:
                    continue
                try:
                    await message.bot.send_message(recipient, "📢 <b>Guild Announcement</b>\n" + escape(text_value))
                    delivered += 1
                except Exception:
                    pass
            await message.answer(f"📢 Announcement saved and delivered to {delivered} guild members.")
        except GuildFeatureError as exc:
            await message.answer(escape(str(exc)))
        return

    if action == "missions":
        if not membership:
            await message.answer("Join a guild first.")
            return
        missions = await get_guild_missions(db, membership["guild_id"])
        lines = ["📜 <b>Daily Guild Missions</b>"]
        for mission in missions:
            marker = "✅" if mission["completed"] else "▫️"
            lines.append(f"{marker} {mission['title']}: {mission['progress']}/{mission['target']} · {mission['xp']} guild XP")
        await message.answer("\n".join(lines))
        return

    if action == "claim":
        if not membership or len(args) < 3:
            await message.answer("Usage: /guild claim battles|boss|trades")
            return
        try:
            xp = await claim_guild_mission(db, membership["guild_id"], user_id, args[2].lower())
            await message.answer(f"🎁 Guild mission claimed. +{xp} guild XP.")
        except GuildFeatureError as exc:
            await message.answer(escape(str(exc)))
        return

    if action == "raid":
        if not membership:
            await message.answer("Join a guild first.")
            return
        parts = (message.text or "").split()
        sub = parts[2].lower() if len(parts) > 2 else "status"
        if sub == "start":
            try:
                guild_cur = await db.execute("SELECT guild_level FROM guilds WHERE guild_id=?", (membership["guild_id"],))
                guild_row = await guild_cur.fetchone()
                level = min(100, max(10, ((guild_row["guild_level"] + 9) // 10) * 10))
                boss = MONSTER_BY_LEVEL[level]
                raid_id = await start_guild_raid(db, membership["guild_id"], user_id, level, boss["name"], boss["hp"] * 5)
                await message.answer(f"🐉 <b>GUILD RAID #{raid_id}</b>\n{escape(boss['name'])} · Lv.{level} · {boss['hp']*5} HP")
            except GuildFeatureError as exc:
                await message.answer(escape(str(exc)))
            return
        if sub == "attack":
            try:
                result = await attack_guild_raid(db, membership["guild_id"], user_id, max(1, p["level"] * 5 + p["weapon_attack"]))
                await record_guild_activity(db, membership["guild_id"], user_id, "boss" if result["status"] == "won" else "battle")
                await message.answer(f"⚔️ You deal {result['damage']} damage.\n{escape(result['boss_name'])}: {result['hp']}/{result['max_hp']} HP\n" + ("🏆 GUILD RAID CLEARED!" if result["status"] == "won" else "The raid continues."))
            except GuildFeatureError as exc:
                await message.answer(escape(str(exc)))
            return
        raid = await guild_raid_status(db, membership["guild_id"])
        await message.answer("No guild raid is active." if not raid else f"🐉 {escape(raid['boss_name'])}: {raid['hp']}/{raid['max_hp']} HP · {raid['status'].upper()}")
        return


    if action == "war":
        if not membership or len(args) < 3:
            await message.answer("Usage: /guild war challenge guild_id | accept war_id | decline war_id | status war_id")
            return
        parts = args[2].split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Usage: /guild war challenge guild_id | accept war_id | decline war_id | status war_id")
            return
        sub, identifier = parts[0].lower(), int(parts[1])
        try:
            if sub == "challenge":
                war_id = await declare_guild_war(db, membership["guild_id"], user_id, identifier)
                target_cur = await db.execute("SELECT name,leader_id FROM guilds WHERE guild_id=?", (identifier,))
                target = await target_cur.fetchone()
                try:
                    await message.bot.send_message(target["leader_id"], "⚔️ Your guild has received a war challenge. Use /guild war accept " + str(war_id) + " or /guild war decline " + str(war_id) + ".")
                    delivery = "The target leader was notified."
                except Exception:
                    delivery = "The target leader must start the bot to receive the invitation."
                await message.answer("⚔️ War challenge #" + str(war_id) + " sent to " + escape(target["name"]) + ". " + delivery)
            elif sub in {"accept", "decline"}:
                status = await respond_guild_war(db, identifier, user_id, sub == "accept")
                await message.answer("Guild war is now active." if status == "active" else "Guild war challenge declined.")
            elif sub == "status":
                war = await get_guild_war(db, identifier)
                if not war or membership["guild_id"] not in {war["challenger_guild"], war["target_guild"]}:
                    await message.answer("Guild war not found.")
                    return
                await message.answer("⚔️ <b>Guild War #" + str(identifier) + "</b>\nScore: " + str(war["challenger_score"]) + " - " + str(war["target_score"]) + "\nStatus: " + war["status"].upper())
            else:
                await message.answer("Use challenge, accept, decline or status.")
        except GuildFeatureError as exc:
            await message.answer(escape(str(exc)))
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
    await message.answer("Guild commands: /guild create|join|leave|info|top|disband, invite|accept|decline, role, announce, missions|claim, raid start|status|attack.")


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
    war_result = None
    if duel["status"] == "finished" and duel["winner_id"]:
        await record_player_guild_activity(duel["winner_id"], "battle")
        war_result = await record_guild_war_duel(db, duel["challenger_id"], duel["opponent_id"], duel["winner_id"])
    duel_message = await duel_text(duel)
    if war_result:
        duel_message += "\n\n⚔️ Guild War score: " + str(war_result["challenger_score"]) + " - " + str(war_result["target_score"])
        if war_result["status"] == "completed": duel_message += "\n🏆 Guild War completed! Winning guild ID: " + str(war_result["winner_guild"])
    markup = duel_keyboard(duel_id) if duel["status"] == "active" else None
    await call.message.edit_text(duel_message, reply_markup=markup)


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






@dp.callback_query(F.data == "online")
async def online_callback(call: CallbackQuery):
    await call.answer()
    count = await count_online_players(db)
    friends = await list_online_friends(db, call.from_user.id)
    lines = ["🌐 <b>Adventure Presence</b>", "Active players in the last 5 minutes: " + str(count), "Your online friends:"]
    lines.extend([escape(row["username"] or "Adventurer") + " · Lv." + str(row["level"]) for row in friends] if friends else ["No friends are currently online."])
    await call.message.answer("\n".join(lines))


@dp.message(Command("online"))
async def online_command(message: Message):
    count = await count_online_players(db)
    friends = await list_online_friends(db, message.from_user.id)
    lines = ["🌐 <b>Adventure Presence</b>", "Active players in the last 5 minutes: " + str(count), "Your online friends:"]
    if friends:
        lines.extend([escape(row["username"] or "Adventurer") + " · Lv." + str(row["level"]) for row in friends])
    else:
        lines.append("No friends are currently online.")
    await message.answer("\n".join(lines))


@dp.message(Command("settings"))
async def settings_command(message: Message):
    user_id = message.from_user.id
    args = (message.text or "").split(maxsplit=2)
    if len(args) == 1:
        settings = await get_settings(db, user_id)
        notifications = "ON" if settings["notifications_enabled"] else "OFF"
        await message.answer("Player Settings\nNotifications: " + notifications + "\nProfile visibility: " + settings["profile_visibility"].upper() + "\nUse /settings notifications on|off or /settings privacy public|friends.")
        return
    if len(args) < 3:
        await message.answer("Usage: /settings notifications on|off or /settings privacy public|friends")
        return
    key, value = args[1].lower(), args[2].lower()
    try:
        if key == "notifications" and value in {"on", "off"}:
            settings = await update_settings(db, user_id, notifications_enabled=(value == "on"))
        elif key == "privacy" and value in {"public", "friends"}:
            settings = await update_settings(db, user_id, profile_visibility=value)
        else:
            raise AccountError("Choose notifications on/off or privacy public/friends.")
        notifications = "ON" if settings["notifications_enabled"] else "OFF"
        await message.answer("Settings saved. Notifications: " + notifications + " · Profile: " + settings["profile_visibility"] + ".")
    except AccountError as exc:
        await message.answer(escape(str(exc)))


@dp.message(Command("deleteaccount"))
async def request_account_deletion(message: Message):
    if message.chat.type != "private":
        await message.answer("For account safety, request deletion in the bot private chat.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Permanently delete account", callback_data="account_delete_confirm"),
        InlineKeyboardButton(text="Cancel", callback_data="account_delete_cancel")
    ]])
    await message.answer(
        "Delete your account permanently?\n"
        "This removes your character, inventory, progress, quests, achievements, friends, trades and social records. "
        "Guild leadership or group ownership will be transferred when possible. "
        "Any unused Peak Gems, premium items and purchase history will also be deleted; this command does not issue refunds. "
        "This cannot be undone.\n\n"
        "Your Telegram account is not affected.",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.in_({"account_delete_confirm", "account_delete_cancel"}))
async def account_deletion_callback(call: CallbackQuery):
    await call.answer()
    if call.message.chat.type != "private":
        await call.message.edit_text("Account deletion can only be confirmed in a private chat.")
        return
    if call.data == "account_delete_cancel":
        await call.message.edit_text("Account deletion cancelled. Your adventure remains intact.")
        return
    try:
        await delete_player_account(db, call.from_user.id)
        await call.message.edit_text("Your Peak Adventure player account and associated game data have been deleted.")
    except AccountError as exc:
        await call.message.edit_text(escape(str(exc)))


@dp.message(Command("event"))
async def roaming_event_command(message: Message):
    args = (message.text or "").split(maxsplit=2)
    action = args[1].lower() if len(args) > 1 else "status"
    user_id = message.from_user.id
    if action == "claim":
        if len(args) < 3 or not args[2].isdigit():
            await message.answer("Usage: /event claim EVENT_ID")
            return
        try:
            reward = await claim_roaming_event_reward(db, int(args[2]), user_id)
            await message.answer(
                f"🏆 Roaming event reward claimed: +{reward['coins']} coins · "
                f"+{reward['xp']} XP. Your level is now {reward['level']}."
            )
        except RoamingEventError as exc:
            await message.answer(escape(str(exc)))
        return
    if action not in {"status", "attack"}:
        await message.answer("Usage: /event, /event attack, or /event claim EVENT_ID")
        return
    player = await get_player(user_id, message.from_user.username or message.from_user.full_name)
    if not player["class_selected"]:
        await message.answer("Choose your hero class with /class before joining a roaming event.")
        return
    world_id = await get_current_world(db, user_id, player["level"])
    boss_level = world_id * 10
    boss_defeated = False
    if player["level"] >= boss_level and boss_level in BOSS_LEVELS:
        cur = await db.execute(
            "SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?",
            (user_id, boss_level),
        )
        boss_defeated = await cur.fetchone() is not None
    monster_level = random.choice(world_encounter_levels(player["level"], world_id, boss_defeated))
    monster = MONSTER_BY_LEVEL[monster_level]
    try:
        event = await get_or_create_roaming_event(
            db, world_id, monster_level, monster["name"], monster["hp"]
        )
        if action == "attack":
            result = await attack_roaming_event(
                db, event["event_id"], user_id,
                max(1, player["level"] * 5 + player["weapon_attack"]),
            )
            status_line = "🌟 EVENT DEFEATED!" if result["status"] == "completed" else "⚔️ Hit landed."
            await message.answer(
                f"{status_line} <b>{escape(event['monster_name'])}</b> · "
                f"{result['hp']}/{result['max_hp']} HP · Your damage: {result['damage']}\\n"
                f"Participants: {result['participants']}\\n"
                + ("Claim with /event claim " + str(event["event_id"]) if result["status"] == "completed"
                   else "Next attack in 30 seconds. Use /event to check progress.")
            )
        else:
            await message.answer(
                f"🌍 <b>Roaming World Event #{event['event_id']}</b>\\n"
                f"World {event['world_id']} · {escape(event['monster_name'])} · Lv.{event['monster_level']}\\n"
                f"❤️ HP: {event['hp']}/{event['max_hp']}\\n"
                f"⏳ Ends: {max(0, event['ends_at'] - int(time.time()))} seconds\\n"
                "Use /event attack to help defeat it. Contributors can claim rewards after victory."
            )
    except RoamingEventError as exc:
        await message.answer(escape(str(exc)))


@dp.message(Command("missions"))
async def daily_missions_command(message: Message):
    args = (message.text or "").split(maxsplit=2)
    user_id = message.from_user.id
    if len(args) >= 3 and args[1].lower() == "claim":
        try:
            reward = await claim_daily_mission(db, user_id, args[2].strip().lower())
            await message.answer(
                f"🎁 <b>{escape(reward['title'])}</b> reward claimed: "
                f"+{reward['coins']} coins and +{reward['potions']} potions."
            )
        except DailyMissionError as exc:
            await message.answer(escape(str(exc)))
        return
    try:
        rows = await get_daily_missions(db, user_id)
    except DailyMissionError as exc:
        await message.answer(escape(str(exc)))
        return
    lines = ["📆 <b>Daily Missions</b> · Reset at 00:00 UTC"]
    for mission in rows:
        marker = "✅" if mission["claimed"] else ("🎁" if mission["completed"] else "🔹")
        lines.append(
            f"{marker} <b>{escape(mission['title'])}</b> · "
            f"{mission['progress']}/{mission['target']}\\n"
            f"{escape(mission['description'])}\\n"
            f"Reward: {mission['coins']} coins · {mission['potions']} potions"
        )
        if mission["completed"] and not mission["claimed"]:
            lines.append(f"Claim: /missions claim {mission['id']}")
    await message.answer("\\n\\n".join(lines))


@dp.message(Command("weekly"))
async def weekly_command(message: Message):
    args=(message.text or "").split(maxsplit=2)
    user_id=message.from_user.id
    if len(args)>=3 and args[1].lower()=="claim":
        try:
            reward=await claim_weekly_reward(db,user_id,args[2].strip().lower())
            await message.answer(f"🎁 <b>{escape(reward['title'])}</b> reward claimed: +{reward['coins']} coins and +{reward['potions']} potions.")
        except WeeklyQuestError as exc:
            await message.answer(escape(str(exc)))
        return
    rows=await get_weekly_quests(db,user_id)
    lines=["📅 <b>Weekly Objectives</b> · Reset every Monday (UTC)"]
    for quest in rows:
        marker="✅" if quest["claimed"] else ("🎁" if quest["completed"] else "🔹")
        lines.append(f"{marker} <b>{escape(quest['title'])}</b> · {quest['progress']}/{quest['target']}\\n{escape(quest['description'])}\\nReward: {quest['coins']} coins · {quest['potions']} potions")
        if quest["completed"] and not quest["claimed"]:
            lines.append(f"Claim: /weekly claim {quest['id']}")
    await message.answer("\\n\\n".join(lines))


@dp.message(Command("report"))
async def report_player(message: Message):
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 3 or not args[1].isdigit():
        await message.answer("Usage: /report player_id reason (10–500 characters)")
        return
    try:
        report_id = await submit_player_report(db, message.from_user.id, int(args[1]), args[2])
        await message.answer(f"✅ Report #{report_id} submitted. An administrator will review it.")
    except ReportError as exc:
        await message.answer(escape(str(exc)))


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
            f"Active PvP duels: {stats['active_duels']}\n"
            f"Suspicious events (24h): {stats['security_events_24h']}\n"
            f"Telegram Stars received: {stats['stars_received']} · Gems issued: {stats['premium_gems_issued']}\n\n"
            "Commands: /admin player ID, /admin coins ID +/-AMOUNT, /admin ban ID reason, /admin unban ID, /admin reports, /admin resolve ID reviewed|dismissed, /admin security [PLAYER_ID], /admin announce MESSAGE."
        )
        return
    if action=="ban":
        if len(args)<3:
            await message.answer("Usage: /admin ban PLAYER_ID reason"); return
        parts=args[2].split(maxsplit=1)
        if not parts[0].isdigit() or len(parts)<2:
            await message.answer("Usage: /admin ban PLAYER_ID reason"); return
        try:
            await ban_player(db,message.from_user.id,int(parts[0]),parts[1])
            await record_admin_action(db,message.from_user.id,"player_ban",int(parts[0]),parts[1])
            await message.answer(f"⛔ Player <code>{parts[0]}</code> has been suspended.")
        except ModerationError as exc:
            await message.answer(escape(str(exc)))
        return
    if action=="unban":
        if len(args)<3 or not args[2].strip().isdigit():
            await message.answer("Usage: /admin unban PLAYER_ID"); return
        target=int(args[2].strip())
        try:
            await unban_player(db,message.from_user.id,target)
            await record_admin_action(db,message.from_user.id,"player_unban",target)
            await message.answer(f"✅ Player <code>{target}</code> has been reinstated.")
        except ModerationError as exc:
            await message.answer(escape(str(exc)))
        return
    if action=="reports":
        reports=await list_open_reports(db,25)
        lines=["🚩 <b>Open Player Reports</b>"]
        for row in reports:
            lines.append(f"#{row['report_id']} · reporter <code>{row['reporter_id']}</code> → target <code>{row['target_id']}</code>\\n{escape(row['reason'])}")
        lines.append("Resolve with /admin resolve REPORT_ID reviewed|dismissed [note].")
        await message.answer("\\n\\n".join(lines) if reports else "No open player reports.")
        return
    if action=="resolve":
        if len(args)<3:
            await message.answer("Usage: /admin resolve REPORT_ID reviewed|dismissed [note]"); return
        parts=args[2].split(maxsplit=2)
        if len(parts)<2 or not parts[0].isdigit():
            await message.answer("Usage: /admin resolve REPORT_ID reviewed|dismissed [note]"); return
        try:
            await resolve_player_report(db,int(parts[0]),message.from_user.id,parts[1].lower(),parts[2] if len(parts)>2 else "")
            await record_admin_action(db,message.from_user.id,"report_"+parts[1].lower(),int(parts[0]),parts[2] if len(parts)>2 else "")
            await message.answer("✅ Report resolved.")
        except ReportError as exc:
            await message.answer(escape(str(exc)))
        return
    if action=="security":
        if len(args)>2 and args[2].isdigit():
            target=int(args[2])
            events=await get_security_events(db,target,20)
            lines=[f"🛡️ <b>Security Events · Player {target}</b>"]
            for row in events:
                lines.append(f"#{row['event_id']} · severity {row['severity']} · {escape(row['event_type'])}\\n{escape(row['details'])} · {row['created_at']}")
            await message.answer("\\n\\n".join(lines) if len(lines)>1 else "No security events for this player.")
        else:
            rows=await get_suspicious_players(db,1440,20)
            lines=["🛡️ <b>Suspicious Activity · Last 24 Hours</b>"]
            for row in rows:
                lines.append(f"Player <code>{row['user_id']}</code> · {row['event_count']} events · risk {row['risk_score']} · max severity {row['max_severity']} · last {row['last_seen']}")
            await message.answer("\\n".join(lines) if len(lines)>1 else "No suspicious activity recorded.")
        return
    if action=="logs":
        logs=await recent_admin_actions(db,20)
        lines=["🧾 <b>Recent Admin Actions</b>"]
        for row in logs:
            lines.append("#"+str(row["log_id"])+" · "+row["action"]+" · actor "+str(row["actor_id"])+" · target "+str(row["target_id"] or "-")+" · "+row["details"])
        await message.answer("\n".join(lines) if len(lines)>1 else "No admin actions have been recorded.")
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
            balance=await adjust_player_coins(db,int(parts[0]),int(parts[1]),message.from_user.id)
            await message.answer(f"✅ Player <code>{parts[0]}</code> coin balance is now {balance}.")
        except AdminError as exc: await message.answer(escape(str(exc)))
        return
    if action=="announce":
        if len(args)<3 or not args[2].strip():
            await message.answer("Usage: /admin announce your announcement"); return
        cur=await db.execute("SELECT p.user_id FROM players p LEFT JOIN player_settings s ON s.user_id=p.user_id WHERE s.notifications_enabled IS NULL OR s.notifications_enabled=1")
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
        await record_admin_action(db,message.from_user.id,"broadcast",None,"sent="+str(sent)+", failed="+str(failed))
        await message.answer(f"📢 Broadcast finished. Sent: {sent}. Failed: {failed}.")
        return
    await message.answer("Admin commands: /admin stats, /admin player ID, /admin coins ID +/-AMOUNT, /admin ban ID reason, /admin unban ID, /admin reports, /admin resolve ID reviewed|dismissed, /admin security [PLAYER_ID], /admin announce MESSAGE.")


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
        "/start - Main menu\n/profile - Your hero stats\n/stamina - Check stamina\n/explore - Find a monster (10 stamina)\n"
        "/inventory - Potions and items\n/map - World and boss milestones\n"
        "/quests - Current objectives\n/missions - Daily objectives and rewards\n/weekly - Weekly objectives and rewards\n/event - Shared roaming world event\n/daily - Daily coins and potion\n"
        "/leaderboard - Top adventurers\n/players username - Search visible players\n/heal - Restore HP (uses 30 coins)\n"
        "/class - View hero classes\n/shop - Buy weapons, armor and potions\n"
        "/claimquest quest_id - Claim a completed quest reward\n"
        "/achievements - View achievements\n/claimachievement achievement_id - Claim an achievement\n"
        "/duel - Challenge a player by replying to their message in a group\n/pvprank - PvP rankings\n"
        "/friend request|accept|decline|list|remove - Friend list\n/online - Recent online friends\n"
        "/party create|invite|accept|decline|info|leave|disband - Party management\n/party battle start|status|attack - Co-op boss fights\n"
        "/guild create|join|leave|info|top|disband|chat|history - Guild management\n"
        "/group register|info|members|missions|claim|raid|ban|unban|top - Telegram group features\n"
        "/report player_id reason - Report a player\n/admin - Bot administration (authorized IDs only; includes report review)\n/export - Download your account data\n"
        "/trade - Start a trade by replying to a player\n/offer, /confirmtrade, /canceltrade - Manage trades\n"
                "/auction - Browse; /auction sell weapon|armor price [hours]\n/auction cancel ID; /bid ID amount\n/auction stash; /auction equip ID\n"
        "/premium - Peak Gems wallet and Telegram Stars packages\n/premium shop; /premium buy ITEM_ID - Spend gems\n"
        "/monster level - Inspect a monster\n/bestiary - View discovered monsters\n"
        "/map - View your current region\n/travel - View unlocked worlds and fast travel\n"
        "/dungeons - View dungeons\n/dungeon enter|status|abandon|claim - Dungeon controls\n"
        "/settings - Privacy and notification settings\n/deleteaccount - Permanently delete your player account\n\n"
        "During battle use Attack, Special Skill, Potion or Escape buttons.")


@dp.message(Command("profile"))
async def profile(message: Message):
    p = await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(await player_text(p))


@dp.message(Command("mana"))
async def mana_command(message: Message):
    state=await get_mana(db,message.from_user.id)
    bars="🔷"*(state["mana"]//10)+"⬛"*(10-state["mana"]//10)
    await message.answer(
        f"🔮 <b>Mana</b>\\n{bars}\\n{state['mana']}/{state['max_mana']}\\n"
        f"Skill cost: {SKILL_MANA_COST} · Regen: 1 per minute · Battle turn restore: {TURN_MANA_REGEN}"
    )


@dp.message(Command("stamina"))
async def stamina_command(message: Message):
    state = await get_stamina(db, message.from_user.id)
    bars = "🟩" * (state["stamina"] // 10) + "⬛" * (10 - state["stamina"] // 10)
    regen = "Full" if state["stamina"] >= state["max_stamina"] else f"{state['next_regen_seconds']} seconds"
    await message.answer(
        f"⚡ <b>Stamina</b>\\n{bars}\\n"
        f"{state['stamina']}/{state['max_stamina']}\\n"
        f"Explore cost: {EXPLORE_COST} stamina\\n"
        f"Next regeneration: {regen}\\n"
        "Regeneration: 1 stamina every 5 minutes."
    )


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



@dp.message(Command("auction"))
async def auction_command(message: Message):
    args = (message.text or "").split()
    action = args[1].lower() if len(args) > 1 else "list"
    user_id = message.from_user.id
    try:
        if action == "sell":
            if len(args) not in {4, 5} or args[2].lower() not in {"weapon", "armor"} or not args[3].isdigit():
                await message.answer("Usage: /auction sell weapon|armor starting_bid [hours]")
                return
            hours = int(args[4]) if len(args) == 5 and args[4].isdigit() else (24 if len(args) == 4 else 0)
            listing_id = await create_listing(db, user_id, args[2].lower(), int(args[3]), hours)
            await message.answer(f"🔨 Auction #{listing_id} created. Your item is held safely until it sells, expires or is cancelled.")
            return
        if action == "cancel":
            if len(args) != 3 or not args[2].isdigit():
                await message.answer("Usage: /auction cancel listing_id")
                return
            await cancel_listing(db, user_id, int(args[2]))
            await message.answer("Auction cancelled. Your item has been returned.")
            return
        if action == "stash":
            rows = await list_stash(db, user_id)
            if not rows:
                await message.answer("Your equipment stash is empty.")
                return
            lines = ["🎒 <b>Stored Equipment</b>"]
            lines.extend(f"#{row['stash_id']} · {escape(row['item_name'])} ({row['slot']}, +{row['item_stat']})" for row in rows)
            lines.append("Equip an item with /auction equip ID. Your currently equipped item will be stored.")
            await message.answer("\n".join(lines))
            return
        if action == "equip":
            if len(args) != 3 or not args[2].isdigit():
                await message.answer("Usage: /auction equip stash_id")
                return
            item_name, slot, stat = await equip_stashed_item(db, user_id, int(args[2]))
            await message.answer(f"✅ Equipped {escape(item_name)} ({slot}, +{stat}). Previous gear moved to your stash.")
            return
        rows = await list_active_auctions(db)
        if not rows:
            await message.answer("🔨 No active auctions. List an equipped weapon or armor with /auction sell.")
            return
        lines = ["🔨 <b>Peak Auction House</b>"]
        for row in rows:
            bid = row["current_bid"] or row["start_price"]
            lines.append(f"\n<b>#{row['listing_id']} · {escape(row['item_name'])}</b> ({row['slot']}, +{row['item_stat']})\nCurrent minimum: {bid} coins · Ends: {datetime.fromtimestamp(row['ends_at'], timezone.utc).strftime('%d %b %H:%M UTC')}")
        lines.append("\nBid with /bid listing_id amount. Seller cannot bid; bids are escrowed and outbid players are refunded.")
        await message.answer("\n".join(lines))
    except (AuctionError, ValueError) as exc:
        await message.answer(escape(str(exc)))


@dp.message(Command("bid"))
async def auction_bid_command(message: Message):
    args = (message.text or "").split()
    if len(args) != 3 or not args[1].isdigit() or not args[2].isdigit():
        await message.answer("Usage: /bid listing_id amount")
        return
    try:
        _, amount = await place_bid(db, message.from_user.id, int(args[1]), int(args[2]))
        await message.answer(f"🔨 Bid of {amount} coins placed. Your coins are held in escrow until you are outbid or the auction settles.")
    except AuctionError as exc:
        await message.answer(escape(str(exc)))


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





@dp.message(Command("materials"))
async def materials_command(message: Message):
    materials = await get_materials(db, message.from_user.id)
    lines = ["🧱 <b>Crafting Materials</b>"]
    if not materials or not any(materials.values()):
        lines.append("No materials yet. Defeat monsters to collect crafting resources.")
    else:
        for material_id, quantity in materials.items():
            lines.append(MATERIALS.get(material_id, material_id) + " x" + str(quantity))
    await message.answer("\n".join(lines))


@dp.message(Command("craft"))
async def craft_command(message: Message):
    player = await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    args = (message.text or "").split(maxsplit=1)
    if len(args) == 1:
        recipes = await list_recipes(player["level"])
        lines = ["⚒️ <b>Crafting Recipes</b>"]
        for recipe in recipes:
            status = "🔓" if recipe["unlocked"] else "🔒"
            costs = ", ".join(MATERIALS[key] + " x" + str(value) for key,value in recipe["cost"].items())
            lines.append(status + " <b>" + recipe["id"] + "</b> · " + recipe["name"] + " · Lv." + str(recipe["level"]) + "\n" + costs)
        lines.append("Craft with /craft recipe_id. View supplies with /materials.")
        await message.answer("\n".join(lines))
        return
    try:
        recipe = await craft_item(db, message.from_user.id, player["level"], args[1].strip().lower())
        await record_weekly_progress(db, message.from_user.id, "crafts")
        await record_daily_progress(db, message.from_user.id, "crafts")
        stat = "+" + str(recipe["attack"]) + " ATK" if recipe["slot"] == "weapon" else "+" + str(recipe["defense"]) + " DEF"
        await message.answer("⚒️ Crafted <b>" + recipe["name"] + "</b> and equipped it. " + stat)
    except CraftingError as exc:
        await message.answer(escape(str(exc)))


@dp.message(Command("dungeons"))
async def dungeons_command(message: Message):
    player = await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    rows = available_dungeons(player["level"])
    lines = ["🗝️ <b>Dungeon Atlas</b>"]
    for dungeon in rows:
        marker = "🔓" if dungeon["unlocked"] else "🔒"
        lines.append(marker + " " + str(dungeon["id"]) + ". " + dungeon["name"] + " · World " + str(dungeon["world"]) + " · Lv." + str(dungeon["min_level"]))
    lines.append("Enter with /dungeon enter ID.")
    await message.answer("\n".join(lines))


@dp.message(Command("dungeon"))
async def dungeon_command(message: Message):
    player = await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    args = (message.text or "").split(maxsplit=2)
    action = args[1].lower() if len(args) > 1 else "status"
    try:
        if action == "enter":
            if len(args) < 3 or not args[2].isdigit():
                await message.answer("Usage: /dungeon enter ID")
                return
            dungeon_id = int(args[2])
            if not 1 <= dungeon_id <= 10:
                raise DungeonError("Dungeon ID must be between 1 and 10.")
            state = await enter_dungeon(db, message.from_user.id, player["level"], dungeon_id)
            await travel_to_world(db, message.from_user.id, player["level"], dungeon_id)
            await message.answer("🗝️ Entered <b>" + escape(state["name"]) + "</b>. Room 1/3: defeat a level " + str(state["target_level"]) + " or stronger monster.")
        elif action == "status":
            state = await get_dungeon_state(db, message.from_user.id)
            if not state:
                await message.answer("No dungeon run. Use /dungeons to choose one.")
                return
            await message.answer("🗝️ <b>" + escape(state["name"]) + "</b>\nRoom: " + str(state["room"]) + "/3 · Target monster level " + str(state["target_level"]) + "\nStatus: " + state["status"].upper())
        elif action == "abandon":
            await abandon_dungeon(db, message.from_user.id)
            await message.answer("Dungeon run abandoned.")
        elif action == "claim":
            coins, potions = await claim_dungeon_reward(db, message.from_user.id)
            await message.answer("🏆 Dungeon reward claimed: +" + str(coins) + " coins and +" + str(potions) + " potions.")
        else:
            await message.answer("Commands: /dungeon enter ID, /dungeon status, /dungeon abandon, /dungeon claim.")
    except DungeonError as exc:
        await message.answer(escape(str(exc)))




@dp.message(Command("story"))
async def story_command(message: Message):
    player = await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    args = (message.text or "").split(maxsplit=3)
    action = args[1].lower() if len(args) > 1 else "list"
    try:
        chapters = await get_story_chapters(db, message.from_user.id, player["level"])
        if action in {"list", "chapters"}:
            lines = ["📖 <b>The Peak Chronicle</b>"]
            for chapter in chapters:
                marker = "✅" if chapter["completed"] else ("🔓" if chapter["unlocked"] else "🔒")
                lines.append(marker + " " + str(chapter["id"]) + ". " + chapter["title"] + " · Lv." + str(chapter["level"]))
            lines.append("Read: /story chapter ID")
            await message.answer("\n".join(lines))
            return
        if action == "chapter":
            if len(args) < 3 or not args[2].isdigit():
                await message.answer("Usage: /story chapter ID")
                return
            chapter_id = int(args[2])
            if not 1 <= chapter_id <= len(chapters):
                raise StoryError("Story chapter not found.")
            chapter = chapters[chapter_id-1]
            if not chapter["unlocked"] and not chapter["completed"]:
                raise StoryError("This chapter is locked. Complete earlier chapters and reach its level requirement.")
            lines = ["🎬 <b>Chapter " + str(chapter_id) + ": " + escape(chapter["title"]) + "</b>",
                     "<i>" + escape(chapter["npc"]) + "</i>", escape(chapter["scene"])]
            if chapter["completed"]:
                lines.append("Your choice: " + escape(chapter["choices"][chapter["choice"]]))
                lines.append("Claim reward: /story claim " + str(chapter_id))
            else:
                lines.append("<b>Choose your path:</b>")
                for choice_id, description in chapter["choices"].items():
                    lines.append("/story choose " + str(chapter_id) + " " + choice_id + " · " + escape(description))
            await message.answer("\n\n".join(lines))
            return
        if action == "choose":
            if len(args) < 4 or not args[2].isdigit():
                await message.answer("Usage: /story choose CHAPTER choice_id")
                return
            result = await choose_story_path(db, message.from_user.id, player["level"], int(args[2]), args[3].lower())
            await message.answer("📜 <b>Choice recorded.</b>\n" + escape(result["choice"]) + "\nUse /story claim " + str(result["chapter"]["id"]) + " to claim +" + str(result["reward"]) + " coins.")
            return
        if action == "claim":
            if len(args) < 3 or not args[2].isdigit():
                await message.answer("Usage: /story claim CHAPTER")
                return
            reward = await claim_story_reward(db, message.from_user.id, int(args[2]))
            await message.answer("✨ Story reward claimed: +" + str(reward) + " coins.")
            return
        await message.answer("Use /story, /story chapter ID, /story choose CHAPTER choice_id or /story claim CHAPTER.")
    except StoryError as exc:
        await message.answer(escape(str(exc)))


@dp.message(Command("landmarks"))
async def landmarks_command(message: Message):
    player = await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    worlds = await get_world_choices(db, message.from_user.id, player["level"])
    lines = ["🗿 <b>World Landmarks</b>"]
    for world in worlds:
        if not world["unlocked"]:
            continue
        landmark = await get_world_landmark(db, message.from_user.id, world["id"])
        marker = "✅" if landmark["discovered"] else "✨"
        lines.append(marker + " " + str(world["id"]) + ". " + landmark["landmark"] + " · " + world["name"])
    lines.append("Use /discover to explore the landmark in your current world.")
    await message.answer("\n".join(lines))


@dp.message(Command("discover"))
async def discover_command(message: Message):
    player = await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    world_id = await get_current_world(db, message.from_user.id, player["level"])
    try:
        reward = await discover_world_landmark(db, message.from_user.id, player["level"], world_id)
        await record_weekly_progress(db, message.from_user.id, "landmarks")
        await record_daily_progress(db, message.from_user.id, "landmarks")
        await message.answer("✨ <b>Landmark discovered!</b>\n" + escape(reward["landmark"]) + "\n🪙 +" + str(reward["coins"]) + " coins · 🧪 +" + str(reward["potions"]) + " potions.")
    except WorldError as exc:
        await message.answer(escape(str(exc)))


@dp.message(Command("travel"))
async def travel_command(message: Message):
    player = await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
    args = (message.text or "").split(maxsplit=1)
    if len(args) == 1:
        worlds = await get_world_choices(db, message.from_user.id, player["level"])
        lines = ["🌀 <b>Fast Travel</b>"]
        for world in worlds:
            marker = "📍" if world["current"] else ("🔓" if world["unlocked"] else "🔒")
            lines.append(marker + " " + str(world["id"]) + ". " + world["name"] + " · Lv." + str(world["min_level"]))
        lines.append("Use /travel world_number to move to an unlocked region.")
        await message.answer("\n".join(lines))
        return
    target = args[1].strip()
    if target.isdigit():
        world_id = int(target)
    else:
        matches = [index + 1 for index, name in enumerate(WORLD_NAMES) if name.casefold() == target.casefold()]
        if not matches:
            await message.answer("World not found. Use /travel to view the map.")
            return
        world_id = matches[0]
    try:
        world = await travel_to_world(db, message.from_user.id, player["level"], world_id)
        await message.answer("🌀 Fast travel complete. You are now in <b>" + escape(world["name"]) + "</b>.")
    except WorldError as exc:
        await message.answer(escape(str(exc)))


@dp.message(Command("map"))
async def map_cmd(message: Message):
    p = await get_player(message.from_user.id)
    worlds = ["🌱 Whispering Meadow", "🏜️ Ashen Desert", "🌩️ Stormglass Highlands", "🏰 Hollow Kingdom",
              "🌋 Ember Abyss", "❄️ Frostfang Peaks", "🕳️ Primordial Rift", "🌌 Celestial Ruins",
              "⌛ Eternal Hour", "🌠 Origin Realm"]
    world_id = await get_current_world(db, message.from_user.id, p["level"])
    await message.answer("🗺️ <b>World Map</b>\nCurrent region: <b>" + worlds[world_id-1] + "</b>\nProgress: Level " + str(p["level"]) + "/100\nUse /travel to view unlocked regions and fast travel.")


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


@dp.message(Command("premium"))
async def premium_command(message: Message):
    if message.chat.type != "private":
        await message.answer("Open a private chat with the bot to manage your premium wallet.")
        return
    args = (message.text or "").split(maxsplit=2)
    action = args[1].lower() if len(args) > 1 else "balance"
    user_id = message.from_user.id
    async with db_lock:
        balance = await get_premium_balance(db, user_id)
    if action == "shop":
        from premium_system import PREMIUM_SHOP_ITEMS
        lines = ["🛍️ <b>Peak Gems Shop</b>", f"Wallet: {balance} gems"]
        for item_id, item in PREMIUM_SHOP_ITEMS.items():
            lines.append(f"<code>{item_id}</code> · {item['title']} · {item['cost']} gems\\n{item['description']}")
        lines.append("Buy with /premium buy ITEM_ID.")
        await message.answer("\\n\\n".join(lines))
        return
    if action == "buy":
        if len(args) < 3:
            await message.answer("Usage: /premium buy stamina_crystal|potion_bundle|xp_charm")
            return
        try:
            async with db_lock:
                async with player_locks[user_id]:
                    purchase = await buy_premium_item(db, user_id, args[2].strip().lower())
                    balance = await get_premium_balance(db, user_id)
            await message.answer(
                f"✅ Purchased <b>{escape(purchase['title'])}</b> for {purchase['cost']} gems. "
                f"Remaining balance: {balance} gems."
            )
        except PremiumError as exc:
            await message.answer(escape(str(exc)))
        return
    if action not in {"balance", "buy"}:
        await message.answer("Use /premium, /premium balance, /premium shop or /premium buy ITEM_ID.")
        return
    if not PREMIUM_PAYMENTS_ENABLED:
        await message.answer(
            f"💎 <b>Peak Gems</b>\\nWallet: {balance} gems\\n"
            "Stars purchases are disabled by the bot owner. Use /premium shop to spend existing gems."
        )
        return
    packages = get_premium_packages()
    rows = [[InlineKeyboardButton(
        text=f"{item['title']} · {item['stars']} ⭐ → {item['gems']} gems",
        callback_data=f"premium:buy:{package_id}",
    )] for package_id, item in packages.items()]
    await message.answer(
        f"💎 <b>Peak Gems</b>\\nWallet: {balance} gems\\n"
        "Choose a Telegram Stars package. Purchases are credited once per Telegram charge.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("premium:buy:"))
async def premium_buy_callback(callback: CallbackQuery):
    if not PREMIUM_PAYMENTS_ENABLED:
        await callback.answer("Premium purchases are disabled.", show_alert=True)
        return
    package_id = callback.data.rsplit(":", 1)[-1]
    package = get_premium_packages().get(package_id)
    if not package:
        await callback.answer("Unknown premium package.", show_alert=True)
        return
    async with db_lock:
        cur = await db.execute("SELECT 1 FROM players WHERE user_id=?", (callback.from_user.id,))
        registered = await cur.fetchone() is not None
    if not registered:
        await callback.answer("Start the bot with /start before buying Peak Gems.", show_alert=True)
        return
    try:
        payload = make_invoice_payload(package_id, callback.from_user.id)
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=package["title"],
            description=f"Receive {package['gems']} Peak Gems for your adventure account.",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"{package['gems']} Peak Gems", amount=package["stars"])],
            start_parameter=f"peak-gems-{package_id}",
        )
        await callback.answer("Your Stars invoice was sent in private chat.")
    except Exception:
        log.exception("Unable to send premium Stars invoice")
        await callback.answer("Could not send the invoice. Start a private chat with the bot first.", show_alert=True)


@dp.pre_checkout_query()
async def premium_pre_checkout(query: PreCheckoutQuery):
    if not PREMIUM_PAYMENTS_ENABLED:
        await query.answer(ok=False, error_message="Premium purchases are currently disabled.")
        return
    try:
        package_id, owner_id = parse_invoice_payload(query.invoice_payload)
        package = get_premium_packages()[package_id]
        valid = (
            owner_id == query.from_user.id
            and query.currency == "XTR"
            and query.total_amount == package["stars"]
        )
        if not valid:
            async with db_lock:
                await record_security_event(db, query.from_user.id, "invalid_premium_payment", "invoice validation mismatch", 4)
            await query.answer(ok=False, error_message="This invoice is invalid or belongs to another player.")
            return
    except PremiumError as exc:
        async with db_lock:
            await record_security_event(db, query.from_user.id, "invalid_premium_payment", str(exc), 3)
        await query.answer(ok=False, error_message="This premium invoice is invalid.")
        return
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def premium_successful_payment(message: Message):
    payment = message.successful_payment
    # A successful Telegram charge must be credited even if new purchases were
    # disabled after the invoice was issued or after Telegram completed checkout.
    try:
        package_id, owner_id = parse_invoice_payload(payment.invoice_payload)
        package = get_premium_packages()[package_id]
        if owner_id != message.from_user.id or payment.currency != "XTR" or payment.total_amount != package["stars"]:
            async with db_lock:
                await record_security_event(db, message.from_user.id, "invalid_premium_payment", "successful payment validation mismatch", 5)
            await message.answer("Payment validation failed. Contact the bot administrator with your Telegram payment receipt.")
            return
        async with db_lock:
            result = await credit_premium_purchase(
                db, message.from_user.id, package_id, payment.total_amount,
                payment.telegram_payment_charge_id, payment.provider_payment_charge_id,
            )
        if result["credited"]:
            await message.answer(
                f"💎 Payment confirmed! {result['gems']} Peak Gems added. "
                f"Wallet balance: {result['balance']} gems."
            )
        else:
            await message.answer(f"This payment was already credited. Wallet balance: {result['balance']} gems.")
    except PremiumError as exc:
        async with db_lock:
            await record_security_event(db, message.from_user.id, "invalid_premium_payment", str(exc), 4)
        await message.answer("The payment could not be credited automatically. Contact the bot administrator.")
    except Exception:
        log.exception("Premium payment credit failed for user %s", message.from_user.id)
        await message.answer("Payment received, but crediting failed. Contact the bot administrator; do not pay again.")


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
    cur = await db.execute("SELECT p.username,p.level,p.wins FROM players p LEFT JOIN player_settings s ON s.user_id=p.user_id WHERE s.profile_visibility IS NULL OR s.profile_visibility = ? ORDER BY p.level DESC,p.wins DESC LIMIT 10", ("public",))
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
    cur = await db.execute("SELECT p.username,p.level,p.wins FROM players p LEFT JOIN player_settings s ON s.user_id=p.user_id WHERE s.profile_visibility IS NULL OR s.profile_visibility = ? ORDER BY p.level DESC,p.wins DESC LIMIT 10", ("public",))
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
    m = build_battle_monster(b)
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
    else:
        if action == "skill":
            if p["skill_cd"] > 0:
                await call.message.answer(f"⏳ Skill cooling down: {p['skill_cd']} turn(s).")
                return
            try:
                await consume_mana(db, user_id, SKILL_MANA_COST, commit=False)
            except ManaError as exc:
                await call.message.answer("🔮 " + escape(str(exc)))
                return
            await db.execute("UPDATE players SET skill_cd=? WHERE user_id=?", (skill_cooldown_for_class(p["hero_class"]), user_id))
        damage, damage_effects = resolve_player_attack(
            action,
            player_level=p["level"],
            class_attack=class_stats["attack"],
            weapon_attack=p["weapon_attack"],
            monster_defense=m["defense"],
            class_element=class_stats["element"],
            monster_element=m["element"],
            monster_weakness=m["weakness"],
            trait_effect=m["trait_effect"],
            next_turn=b["turn_count"] + 1,
            random_bonus=random.randint(5, 18) if action == "attack" else 0,
        )
        if action == "skill":
            action_line = f"🔥 <b>{class_stats['skill']}!</b> You deal {damage} damage."
        else:
            action_line = f"⚔️ You strike for {damage} damage."
        for effect in damage_effects:
            action_line += {
                "weakness": f" ✨ Super effective! {class_stats['element']} exploits its weakness.",
                "resisted": f" 🧱 {m['element']} resists your matching element.",
                "armored": " 🛡️ Its armor absorbs part of the hit.",
                "shield": " 🔰 Its shield blocks part of this strike.",
            }[effect]
    new_enemy_hp = max(0, b["monster_hp"] - damage)
    turn_count = b["turn_count"] + 1
    if new_enemy_hp > 0 and m["trait_effect"] == "regenerate":
        regen = max(1, m["hp"] // 50)
        new_enemy_hp = min(m["hp"], new_enemy_hp + regen)
    if new_enemy_hp == 0:
        await restore_mana(db, user_id, TURN_MANA_REGEN, commit=False)
        await db.execute("UPDATE players SET hp=min(max_hp, hp+15), skill_cd=max(0, skill_cd-1) WHERE user_id=?", (user_id,))
        result = await finish_battle(user_id, True)
        await call.message.edit_text(f"{action_line}\n\n{result}", reply_markup=menu(include_webapp=call.message.chat.type == "private"))
        return
    p = await get_player(user_id)
    combat_result = resolve_enemy_turn(
        trait_effect=m["trait_effect"],
        turn_count=turn_count,
        monster_hp_before=b["monster_hp"],
        monster_hp_after_action=new_enemy_hp,
        monster_max_hp=m["hp"],
        monster_attack_power=m["attack_power"],
        monster_speed=m["speed"],
        player_hp=p["hp"],
        player_max_hp=p["max_hp"],
        player_level=p["level"],
        armor_defense=p["armor_defense"],
        class_defense=class_stats["defense"],
        class_speed=class_stats["speed"],
        player_damage=damage,
        action=action,
        random_bonus=random.randint(-3, 6),
        dodge_roll=random.randint(1, 100),
        is_boss=m["boss"],
        boss_name=m["name"],
        hero_class=p["hero_class"],
    )
    new_enemy_hp = combat_result["monster_hp"]
    enemy_damage = combat_result["enemy_damage"]
    evaded = combat_result["evaded"]
    special_turn = combat_result["special_turn"]
    reflect_damage = combat_result["reflect_damage"]
    poison_damage = combat_result["poison_damage"]
    new_hp = combat_result["player_hp"]
    effect_notes = combat_result["effect_notes"]
    effect_text = " " + " ".join(effect_notes) if effect_notes else ""
    await db.execute("UPDATE battles SET monster_hp=?, turn_count=? WHERE user_id=?", (new_enemy_hp, turn_count, user_id))
    await db.execute("UPDATE players SET hp=?, skill_cd=max(0, skill_cd-1) WHERE user_id=?", (new_hp, user_id))
    await restore_mana(db, user_id, TURN_MANA_REGEN, commit=False)
    if new_hp == 0:
        result = await finish_battle(user_id, False)
        await call.message.edit_text(f"{action_line}\n💥 {m['name']} hits you for {enemy_damage}.{effect_text}\n\n{result}", reply_markup=menu(include_webapp=call.message.chat.type == "private"))
        return
    await db.commit()
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
    world_id = await get_current_world(db, user_id, p["level"])
    region_index = world_id - 1
    boss_level = world_id * 10
    boss_defeated = False
    if p["level"] >= boss_level and boss_level in BOSS_LEVELS:
        cur = await db.execute(
            "SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?",
            (user_id, boss_level),
        )
        boss_defeated = await cur.fetchone() is not None
    nearby_levels = world_encounter_levels(p["level"], world_id, boss_defeated)
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
        active_monster = build_battle_monster(battle_row)
        battle = {
            "elite": bool(battle_row["is_elite"]),
            "evolved": bool(battle_row["is_evolved"]),
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

    friend_rows = await list_friends(db, user_id)
    social_friends = [{"user_id":row["user_id"],"username":row["username"] or "Adventurer","level":row["level"]} for row in friend_rows]
    friend_requests = [
        {"request_id":row["request_id"],"requester_id":row["requester_id"],
         "username":row["username"] or "Adventurer","level":row["level"]}
        for row in await list_pending_friend_requests(db, user_id)
    ]
    party_invites = [
        {"invite_id":row["invite_id"],"party_id":row["party_id"],"inviter_id":row["inviter_id"],
         "username":row["username"] or "Adventurer","level":row["level"]}
        for row in await list_pending_party_invites(db, user_id)
    ]
    social_party = None
    try:
        party_info, party_members = await get_party_info(db, user_id)
        social_party = {"party_id":party_info["party_id"],"leader_id":party_info["leader_id"],
            "members":[{"user_id":row["user_id"],"username":row["username"] or "Adventurer","level":row["level"]} for row in party_members]}
    except PartyError:
        pass
    guild_cur = await db.execute("SELECT g.guild_id,g.name,g.guild_level,g.guild_xp,gm.role FROM guild_members gm JOIN guilds g ON g.guild_id=gm.guild_id WHERE gm.user_id=?", (user_id,))
    guild_row = await guild_cur.fetchone()
    social_guild = None
    if guild_row:
        guild_members_cur = await db.execute("SELECT p.user_id,p.username,p.level,gm.role FROM guild_members gm JOIN players p ON p.user_id=gm.user_id WHERE gm.guild_id=? ORDER BY gm.role DESC,p.level DESC", (guild_row["guild_id"],))
        guild_members_rows = await guild_members_cur.fetchall()
        social_guild = {"guild_id":guild_row["guild_id"],"name":guild_row["name"],"level":guild_row["guild_level"],
            "xp":guild_row["guild_xp"],"role":guild_row["role"],
            "members":[{"user_id":row["user_id"],"username":row["username"] or "Adventurer","level":row["level"],"role":row["role"]} for row in guild_members_rows]}
    pending_guild_invites = await list_pending_guild_invites(db, user_id)
    social_guild_invites = [
        {"invite_id":row["invite_id"],"guild_id":row["guild_id"],"guild_name":row["guild_name"],
         "inviter_id":row["inviter_id"],"inviter_name":row["inviter_name"] or "Adventurer",
         "inviter_level":row["inviter_level"]}
        for row in pending_guild_invites
    ]
    trade_cur = await db.execute(
        """SELECT t.trade_id,t.initiator_id,t.partner_id,t.created_at,
                  p.username AS other_username
           FROM trades t
           JOIN players p ON p.user_id=CASE WHEN t.initiator_id=? THEN t.partner_id ELSE t.initiator_id END
           WHERE t.status='pending' AND (t.initiator_id=? OR t.partner_id=?)
           ORDER BY t.created_at DESC,t.trade_id DESC LIMIT 10""",
        (user_id,user_id,user_id),
    )
    pending_trade_rows = await trade_cur.fetchall()
    pending_trades = [
        {"trade_id":row["trade_id"],"incoming":row["partner_id"] == user_id,
         "other_username":row["other_username"] or "Adventurer","created_at":row["created_at"]}
        for row in pending_trade_rows
    ]
    trade_count_cur = await db.execute(
        "SELECT COUNT(*) AS total FROM trades WHERE status='pending' AND (initiator_id=? OR partner_id=?)",
        (user_id,user_id),
    )
    pending_trade_count = (await trade_count_cur.fetchone())["total"]
    open_trade_cur = await db.execute(
        """SELECT t.*,p.username AS other_username
           FROM trades t
           JOIN players p ON p.user_id=CASE WHEN t.initiator_id=? THEN t.partner_id ELSE t.initiator_id END
           WHERE t.status='open' AND (t.initiator_id=? OR t.partner_id=?)
           ORDER BY t.created_at DESC,t.trade_id DESC LIMIT 10""",
        (user_id,user_id,user_id),
    )
    open_trade_rows = await open_trade_cur.fetchall()
    open_trades = [
        {
            "trade_id":row["trade_id"],
            "other_username":row["other_username"] or "Adventurer",
            "my_coins":row["initiator_coins"] if row["initiator_id"] == user_id else row["partner_coins"],
            "my_potions":row["initiator_potions"] if row["initiator_id"] == user_id else row["partner_potions"],
            "their_coins":row["partner_coins"] if row["initiator_id"] == user_id else row["initiator_coins"],
            "their_potions":row["partner_potions"] if row["initiator_id"] == user_id else row["initiator_potions"],
            "my_weapon":row["initiator_weapon"] if row["initiator_id"] == user_id else row["partner_weapon"],
            "my_armor":row["initiator_armor"] if row["initiator_id"] == user_id else row["partner_armor"],
            "their_weapon":row["partner_weapon"] if row["initiator_id"] == user_id else row["initiator_weapon"],
            "their_armor":row["partner_armor"] if row["initiator_id"] == user_id else row["initiator_armor"],
            "my_confirmed":bool(row["initiator_confirmed"] if row["initiator_id"] == user_id else row["partner_confirmed"]),
            "their_confirmed":bool(row["partner_confirmed"] if row["initiator_id"] == user_id else row["initiator_confirmed"]),
        }
        for row in open_trade_rows
    ]
    dungeon_state = await get_dungeon_state(db, user_id)
    dungeon_choices = available_dungeons(p["level"])
    claimed_cur = await db.execute("SELECT dungeon_id FROM dungeon_rewards WHERE user_id=?", (user_id,))
    claimed_dungeons = {row["dungeon_id"] for row in await claimed_cur.fetchall()}
    for dungeon_choice in dungeon_choices:
        dungeon_choice["claimed"] = dungeon_choice["id"] in claimed_dungeons
    material_state = await get_materials(db, user_id)
    story_state = await get_story_chapters(db, user_id, p["level"])
    await refresh_quest_progress(user_id)
    quest_cur = await db.execute("SELECT quest_id,progress,completed,claimed FROM quest_progress WHERE user_id=?", (user_id,))
    quest_progress = {row["quest_id"]: row for row in await quest_cur.fetchall()}
    quest_state = [
        {**quest, "progress": quest_progress[quest["id"]]["progress"],
         "completed": bool(quest_progress[quest["id"]]["completed"]),
         "claimed": bool(quest_progress[quest["id"]]["claimed"])}
        for quest in QUESTS if quest["id"] in quest_progress
    ]
    return {
        "first_name": user.get("first_name") or user.get("username") or "Adventurer",
        "class_selected": bool(p["class_selected"]),
        "battle_active": battle is not None,
        "hero_class": p["hero_class"],
        "appearance": appearance,
        "quests": quest_state,
        "social": {"friends": social_friends, "friend_requests": friend_requests, "party_invites": party_invites,
                    "pending_guild_invites": social_guild_invites, "party": social_party, "guild": social_guild,
                    "pending_trades": pending_trades, "pending_trade_count": pending_trade_count,
                    "open_trades": open_trades},
        "dungeon": dungeon_state,
        "dungeons": dungeon_choices,
        "materials": material_state,
        "story": story_state,
        "weekly_quests": await get_weekly_quests(db, user_id),
        "daily_missions": await get_daily_missions(db, user_id),
        "online_count": await count_online_players(db),
        "settings": await get_settings(db, user_id),
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
        "stamina": await get_stamina(db, user_id),
        "mana": await get_mana(db, user_id),
        "potions": p["potions"],
        "skill_cd": p["skill_cd"],
        "coins": p["coins"],
        "premium_gems": await get_premium_balance(db, user_id),
        "premium_shop": [{"item_id":key,**value} for key,value in PREMIUM_SHOP_ITEMS.items()],
        "world_id": world_id,
        "worlds": await get_world_choices(db, user_id, p["level"]),
        "landmark": await get_world_landmark(db, user_id, world_id),
        "secret_area": await get_secret_area_state(db, user_id, p["level"], world_id),
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
        await expire_stale_trades()
        return web.json_response(await miniapp_state(user))


async def api_dungeon(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    if request.content_length is not None and request.content_length > 4096:
        return web.json_response({"error": "Dungeon request is too large."}, status=413)
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "Dungeon payload must be valid JSON."}, status=400)
    if not isinstance(payload, dict) or not isinstance(payload.get("action"), str) or payload["action"] not in {"enter", "abandon", "claim"}:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_dungeon_action", "unsupported action", 2)
        return web.json_response({"error": "Choose enter, abandon or claim."}, status=400)
    action = payload["action"]
    expected_fields = {"action", "dungeon_id"} if action == "enter" else {"action"}
    if set(payload) != expected_fields:
        return web.json_response({"error": "Unsupported dungeon request fields."}, status=400)
    dungeon_id = payload.get("dungeon_id")
    if action == "enter" and (not isinstance(dungeon_id, int) or isinstance(dungeon_id, bool) or not 1 <= dungeon_id <= 10):
        return web.json_response({"error": "A valid dungeon ID is required."}, status=400)
    user_id = user["id"]
    try:
        async with db_lock:
            async with player_locks[user_id]:
                player = await get_player(user_id, user.get("username") or user.get("first_name"))
                if action == "enter":
                    if not player["class_selected"]:
                        return web.json_response({"error": "Choose a hero class in the Telegram chat first."}, status=409)
                    cur = await db.execute("SELECT 1 FROM battles WHERE user_id=?", (user_id,))
                    if await cur.fetchone():
                        return web.json_response({"error": "Finish your active battle before entering a dungeon."}, status=409)
                    state = await enter_dungeon(db, user_id, player["level"], dungeon_id)
                    message = "Dungeon entered. Defeat the room guardians to progress."
                elif action == "abandon":
                    await abandon_dungeon(db, user_id)
                    state = None
                    message = "Dungeon run abandoned."
                else:
                    coins, potions = await claim_dungeon_reward(db, user_id)
                    state = None
                    message = f"Dungeon reward claimed: +{coins} coins and +{potions} potions."
                player_state = await miniapp_state(user)
    except DungeonError as exc:
        return web.json_response({"error": str(exc)}, status=409)
    return web.json_response({"message": message, "result": state, "state": player_state})


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
    if set(payload) - {"monster_level"}:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_monster_request", "unexpected exploration fields", 2)
        return web.json_response({"error": "Unsupported exploration request fields."}, status=400)
    requested_monster_level = payload.get("monster_level")
    if requested_monster_level is not None and (type(requested_monster_level) is not int or not 1 <= requested_monster_level <= 100):
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_monster_request", str(requested_monster_level)[:80], 3)
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
            world_id = await get_current_world(db, user_id, p["level"])
            boss_level = world_id * 10
            boss_defeated = False
            if p["level"] >= boss_level and boss_level in BOSS_LEVELS:
                cur = await db.execute(
                    "SELECT 1 FROM boss_defeats WHERE user_id=? AND monster_level=?",
                    (user_id, boss_level),
                )
                boss_defeated = await cur.fetchone() is not None
            available_monster_levels = world_encounter_levels(p["level"], world_id, boss_defeated)
            if requested_monster_level is not None and requested_monster_level not in available_monster_levels:
                return web.json_response({"error": "That monster is not available at your current level."}, status=409)
            monster_level = requested_monster_level if requested_monster_level is not None else random.choice(available_monster_levels)
            monster = MONSTER_BY_LEVEL[monster_level]
            mastery = await get_evolution_state(db, user_id, monster_level)
            evolved = is_evolved_spawn(mastery["evolved"] and not monster["boss"], random.randint(1, 100))
            elite = is_elite_spawn(monster["boss"], random.randint(1, 100))
            battle_monster = scale_evolved_monster(monster) if evolved else monster
            if elite:
                battle_monster = scale_elite_monster(battle_monster)
            # The Mini App must pay the same exploration cost as Telegram /explore.
            # Existing battles are checked above, so refreshing the active battle is free.
            try:
                await consume_stamina(db, user_id, EXPLORE_COST)
            except StaminaError as exc:
                stamina_state = await get_stamina(db, user_id)
                return web.json_response(
                    {"error": str(exc), "stamina": stamina_state},
                    status=409,
                )
            await db.execute("UPDATE players SET skill_cd=0 WHERE user_id=?", (user_id,))
            await db.execute(
                "INSERT INTO battles(user_id, monster_level, monster_hp, is_elite, is_evolved) VALUES (?, ?, ?, ?, ?)",
                (user_id, monster_level, battle_monster["hp"], int(elite), int(evolved)),
            )
            await db.execute(
                "INSERT OR IGNORE INTO monster_discoveries(user_id, monster_level) VALUES (?, ?)",
                (user_id, monster_level),
            )
            await db.commit()
    return web.json_response({"message": "A monster approaches!", "state": await miniapp_state(user)})


async def api_quest_claim(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "Invalid JSON body."}, status=400)
    if not isinstance(payload, dict) or not isinstance(payload.get("quest_id"), str) or len(payload["quest_id"]) > 64:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_reward_claim", "invalid quest claim payload", 2)
        return web.json_response({"error": "A valid quest_id is required."}, status=400)
    async with db_lock:
        result = await claim_quest_reward(user["id"], payload["quest_id"])
        state = await miniapp_state(user)
    return web.json_response({"message": result, "state": state})




async def api_daily_mission_claim(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    if request.content_length is not None and request.content_length > 2048:
        return web.json_response({"error": "Daily mission request is too large."}, status=413)
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "Daily mission payload must be valid JSON."}, status=400)
    if not isinstance(payload, dict) or set(payload) != {"mission_id"}:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_reward_claim", "invalid daily mission claim payload", 2)
        return web.json_response({"error": "A mission_id is required."}, status=400)
    mission_id = payload.get("mission_id")
    if not isinstance(mission_id, str) or len(mission_id) > 64:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_reward_claim", "invalid daily mission ID", 2)
        return web.json_response({"error": "Invalid daily mission ID."}, status=400)
    try:
        async with db_lock:
            async with player_locks[user["id"]]:
                reward = await claim_daily_mission(db, user["id"], mission_id)
                state = await miniapp_state(user)
    except DailyMissionError as exc:
        return web.json_response({"error": str(exc)}, status=409)
    return web.json_response({
        "message": f"Daily mission claimed: +{reward['coins']} coins and +{reward['potions']} potions.",
        "state": state,
    })


async def api_weekly_quest_claim(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    if request.content_length is not None and request.content_length > 2048:
        return web.json_response({"error": "Weekly quest request is too large."}, status=413)
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "Weekly quest payload must be valid JSON."}, status=400)
    if not isinstance(payload, dict) or set(payload) != {"quest_id"}:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_reward_claim", "invalid weekly quest claim payload", 2)
        return web.json_response({"error": "A quest_id is required."}, status=400)
    quest_id = payload.get("quest_id")
    if not isinstance(quest_id, str) or len(quest_id) > 64:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_reward_claim", "invalid weekly quest ID", 2)
        return web.json_response({"error": "Invalid weekly quest ID."}, status=400)
    try:
        async with db_lock:
            async with player_locks[user["id"]]:
                reward = await claim_weekly_reward(db, user["id"], quest_id)
                state = await miniapp_state(user)
    except WeeklyQuestError as exc:
        return web.json_response({"error": str(exc)}, status=409)
    return web.json_response({
        "message": f"Weekly quest claimed: +{reward['coins']} coins and +{reward['potions']} potions.",
        "state": state,
    })


async def api_world(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    if request.content_length is not None and request.content_length > 2048:
        return web.json_response({"error": "World request is too large."}, status=413)
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "World payload must be valid JSON."}, status=400)
    if not isinstance(payload, dict):
        return web.json_response({"error": "World payload must be a JSON object."}, status=400)
    action = payload.get("action")
    if not isinstance(action, str) or action not in {"travel", "discover", "secret"}:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_world_action", "unsupported action", 2)
        return web.json_response({"error": "Unsupported world action."}, status=400)
    user_id = user["id"]
    try:
        async with db_lock:
            async with player_locks[user_id]:
                player = await get_player(user_id, user.get("username") or user.get("first_name"))
                if action == "travel":
                    if set(payload) != {"action", "world_id"}:
                        return web.json_response({"error": "A world_id is required."}, status=400)
                    world_id = payload.get("world_id")
                    if not isinstance(world_id, int) or isinstance(world_id, bool):
                        return web.json_response({"error": "Invalid world ID."}, status=400)
                    cur = await db.execute("SELECT 1 FROM battles WHERE user_id=?", (user_id,))
                    if await cur.fetchone():
                        return web.json_response({"error": "Finish or escape your active battle before travelling."}, status=409)
                    world = await travel_to_world(db, user_id, player["level"], world_id)
                    message = "Fast travel complete. You are now in " + world["name"] + "."
                elif action == "discover":
                    if set(payload) != {"action"}:
                        return web.json_response({"error": "Unexpected fields in landmark request."}, status=400)
                    world_id = await get_current_world(db, user_id, player["level"])
                    reward = await discover_world_landmark(db, user_id, player["level"], world_id)
                    await record_weekly_progress(db, user_id, "landmarks")
                    await record_daily_progress(db, user_id, "landmarks")
                    message = f"Landmark discovered: {reward['landmark']}. +{reward['coins']} coins and +{reward['potions']} potions."
                else:
                    if set(payload) != {"action"}:
                        return web.json_response({"error": "Unexpected fields in secret area request."}, status=400)
                    world_id = await get_current_world(db, user_id, player["level"])
                    reward = await discover_secret_area(db, user_id, player["level"], world_id)
                    message = f"Hidden area discovered: {reward['name']}. +{reward['coins']} coins and +{reward['potions']} potions."
                state = await miniapp_state(user)
    except (WorldError, SecretAreaError) as exc:
        return web.json_response({"error": str(exc)}, status=409)
    return web.json_response({"message": message, "state": state})


async def api_story(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    if request.content_length is not None and request.content_length > 4096:
        return web.json_response({"error": "Story request is too large."}, status=413)
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "Story payload must be valid JSON."}, status=400)
    if not isinstance(payload, dict) or not isinstance(payload.get("action"), str) or payload["action"] not in {"choose", "claim"}:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_story_action", "unsupported story action", 2)
        return web.json_response({"error": "Unsupported story action."}, status=400)
    expected_fields = {"action", "chapter_id", "choice_id"} if payload["action"] == "choose" else {"action", "chapter_id"}
    if set(payload) != expected_fields:
        return web.json_response({"error": "Unsupported story request fields."}, status=400)
    chapter_id = payload.get("chapter_id")
    if not isinstance(chapter_id, int) or isinstance(chapter_id, bool):
        return web.json_response({"error": "Invalid chapter ID."}, status=400)
    try:
        async with db_lock:
            player = await get_player(user["id"])
            if payload["action"] == "choose":
                choice_id = payload.get("choice_id")
                if not isinstance(choice_id, str) or len(choice_id)>40:
                    return web.json_response({"error":"Invalid story choice."},status=400)
                result = await choose_story_path(db,user["id"],player["level"],chapter_id,choice_id)
                message = "Story choice recorded."
            else:
                reward = await claim_story_reward(db,user["id"],chapter_id)
                result = {"reward":reward}
                message = "Story reward claimed."
            state = await miniapp_state(user)
    except StoryError as exc:
        return web.json_response({"error":str(exc)},status=400)
    return web.json_response({"message":message,"result":result,"state":state})


async def api_premium_shop(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    if request.content_length is not None and request.content_length > 2048:
        return web.json_response({"error": "Premium shop request is too large."}, status=413)
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "Premium shop payload must be valid JSON."}, status=400)
    if not isinstance(payload, dict) or set(payload) != {"item_id"} or not isinstance(payload["item_id"], str):
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_reward_claim", "invalid premium shop payload", 2)
        return web.json_response({"error": "A valid premium item_id is required."}, status=400)
    try:
        async with db_lock:
            async with player_locks[user["id"]]:
                purchase = await buy_premium_item(db, user["id"], payload["item_id"])
                state = await miniapp_state(user)
    except PremiumError as exc:
        return web.json_response({"error": str(exc)}, status=409)
    return web.json_response({"message": f"Purchased {purchase['title']}.", "purchase": purchase, "state": state})


async def expire_stale_trades():
    """Expire abandoned trades without committing a transaction owned by the caller."""
    if db is None:
        return 0
    nested = db.in_transaction
    savepoint = "expire_stale_trades"
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    else:
        await db.execute("BEGIN IMMEDIATE")
    try:
        cur = await db.execute(
            """UPDATE trades
               SET status='expired',initiator_confirmed=0,partner_confirmed=0
               WHERE status IN ('pending','open')
                 AND datetime(created_at) <= datetime('now','-24 hours')"""
        )
        expired_count = cur.rowcount
        if nested:
            await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        else:
            await db.commit()
        return expired_count
    except Exception:
        if nested:
            await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            await db.execute(f"RELEASE SAVEPOINT {savepoint}")
        else:
            await db.rollback()
        raise


async def api_social(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    if request.content_length is not None and request.content_length > 4096:
        return web.json_response({"error": "Social request is too large."}, status=413)
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "Social payload must be valid JSON."}, status=400)
    if not isinstance(payload, dict) or not isinstance(payload.get("action"), str):
        return web.json_response({"error": "A social action is required."}, status=400)
    action = payload["action"]
    user_id = user["id"]
    try:
        async with db_lock:
            await expire_stale_trades()
            async with player_locks[user_id]:
                player = await get_player(user_id, user.get("username") or user.get("first_name"))
                if action == "friend_search":
                    if set(payload) != {"action", "query"} or not isinstance(payload["query"], str):
                        return web.json_response({"error": "A player search query is required."}, status=400)
                    rows = await search_players(db, user_id, payload["query"], limit=10)
                    result = {"players": [{"user_id":row["user_id"],"username":row["username"] or "Adventurer","level":row["level"]} for row in rows]}
                elif action == "friend_request":
                    if set(payload) != {"action", "target_id"} or type(payload["target_id"]) is not int:
                        return web.json_response({"error": "A valid target_id is required."}, status=400)
                    target_id = payload["target_id"]
                    cur = await db.execute(
                        """SELECT p.user_id,COALESCE(s.profile_visibility,'public') AS visibility
                           FROM players p LEFT JOIN player_settings s ON s.user_id=p.user_id
                           WHERE p.user_id=?""", (target_id,),
                    )
                    target = await cur.fetchone()
                    if not target or target["visibility"] != "public":
                        raise FriendError("That player's profile is not publicly available.")
                    result = {"request_id": await send_friend_request(db, user_id, target_id)}
                elif action in {"friend_accept", "friend_decline"}:
                    if set(payload) != {"action", "request_id"} or type(payload["request_id"]) is not int:
                        return web.json_response({"error": "A valid request_id is required."}, status=400)
                    await respond_to_friend_request(db, payload["request_id"], user_id, action == "friend_accept")
                    result = {"accepted": action == "friend_accept"}
                elif action == "friend_remove":
                    if set(payload) != {"action", "friend_id"} or type(payload["friend_id"]) is not int:
                        return web.json_response({"error": "A valid friend_id is required."}, status=400)
                    await remove_friend(db, user_id, payload["friend_id"])
                    result = {"removed": True}
                elif action == "party_create":
                    if set(payload) != {"action"}:
                        return web.json_response({"error": "Unexpected party creation fields."}, status=400)
                    if not player["class_selected"]:
                        raise PartyError("Choose a hero class before creating a party.")
                    result = {"party_id": await create_party(db, user_id)}
                elif action == "party_invite":
                    if set(payload) != {"action", "target_id"} or type(payload["target_id"]) is not int:
                        return web.json_response({"error": "A valid target_id is required."}, status=400)
                    party, _ = await get_party_info(db, user_id)
                    cur = await db.execute(
                        "SELECT class_selected FROM players WHERE user_id=?",
                        (payload["target_id"],),
                    )
                    target = await cur.fetchone()
                    if not target:
                        raise PartyError("That player has not joined the adventure yet.")
                    if not target["class_selected"]:
                        raise PartyError("That player must choose a hero class first.")
                    cur = await db.execute(
                        """SELECT 1 FROM friend_requests
                           WHERE user_low=MIN(?,?) AND user_high=MAX(?,?) AND status='accepted'""",
                        (user_id,payload["target_id"],user_id,payload["target_id"]),
                    )
                    if not await cur.fetchone():
                        raise PartyError("You can invite accepted friends to your party.")
                    result = {"invite_id": await invite_to_party(db, party["party_id"], user_id, payload["target_id"])}
                elif action in {"party_accept", "party_decline"}:
                    if set(payload) != {"action", "invite_id"} or type(payload["invite_id"]) is not int:
                        return web.json_response({"error": "A valid invite_id is required."}, status=400)
                    await respond_to_party_invite(db, payload["invite_id"], user_id, action == "party_accept")
                    result = {"accepted": action == "party_accept"}
                elif action == "party_leave":
                    if set(payload) != {"action"}:
                        return web.json_response({"error": "Unexpected party leave fields."}, status=400)
                    result = {"new_leader_id": await leave_party(db, user_id)}
                elif action in {"guild_accept", "guild_decline"}:
                    if set(payload) != {"action", "invite_id"} or type(payload["invite_id"]) is not int:
                        return web.json_response({"error": "A valid guild invite_id is required."}, status=400)
                    await respond_guild_invite(db, payload["invite_id"], user_id, action == "guild_accept")
                    result = {"accepted": action == "guild_accept"}
                elif action == "trade_create":
                    if set(payload) != {"action", "target_id"} or type(payload["target_id"]) is not int or payload["target_id"] <= 0:
                        return web.json_response({"error": "A valid target_id is required."}, status=400)
                    target_id = payload["target_id"]
                    if target_id == user_id:
                        return web.json_response({"error": "You cannot trade with yourself."}, status=400)
                    low_id, high_id = sorted((user_id, target_id))
                    friend_cur = await db.execute(
                        "SELECT 1 FROM friend_requests WHERE user_low=? AND user_high=? AND status='accepted'",
                        (low_id, high_id),
                    )
                    if not await friend_cur.fetchone():
                        return web.json_response({"error": "You can only start trades with accepted friends."}, status=409)
                    target_cur = await db.execute(
                        "SELECT class_selected FROM players WHERE user_id=?", (target_id,)
                    )
                    target = await target_cur.fetchone()
                    if not target or not target["class_selected"] or not player["class_selected"]:
                        return web.json_response({"error": "Both players must finish character registration before trading."}, status=409)
                    active_cur = await db.execute(
                        """SELECT 1 FROM trades WHERE status IN ('pending','open')
                           AND (initiator_id IN (?,?) OR partner_id IN (?,?)) LIMIT 1""",
                        (user_id,target_id,user_id,target_id),
                    )
                    if await active_cur.fetchone():
                        return web.json_response({"error": "One of these players already has an active trade."}, status=409)
                    trade_cur = await db.execute(
                        "INSERT INTO trades(chat_id,initiator_id,partner_id,status) VALUES(0,?,?,'pending')",
                        (user_id,target_id),
                    )
                    result = {"trade_id": trade_cur.lastrowid, "status": "pending"}
                elif action in {"trade_accept", "trade_decline"}:
                    if set(payload) != {"action", "trade_id"} or type(payload["trade_id"]) is not int or payload["trade_id"] <= 0:
                        return web.json_response({"error": "A valid trade_id is required."}, status=400)
                    trade_status = "open" if action == "trade_accept" else "declined"
                    trade_cur = await db.execute(
                        """UPDATE trades SET status=?
                           WHERE trade_id=? AND partner_id=? AND status='pending'""",
                        (trade_status,payload["trade_id"],user_id),
                    )
                    if trade_cur.rowcount != 1:
                        return web.json_response({"error": "This trade invitation is no longer available to you."}, status=409)
                    result = {"trade_id":payload["trade_id"],"status":trade_status}
                elif action == "trade_offer":
                    if (set(payload) != {"action", "trade_id", "coins", "potions", "offer_weapon", "offer_armor"}
                            or type(payload["trade_id"]) is not int or payload["trade_id"] <= 0
                            or type(payload["coins"]) is not int or payload["coins"] < 0
                            or type(payload["potions"]) is not int or payload["potions"] < 0
                            or type(payload["offer_weapon"]) is not bool
                            or type(payload["offer_armor"]) is not bool):
                        return web.json_response({"error": "A valid trade_id, non-negative balances and equipment choices are required."}, status=400)
                    trade_cur = await db.execute(
                        "SELECT * FROM trades WHERE trade_id=? AND status='open'", (payload["trade_id"],)
                    )
                    trade = await trade_cur.fetchone()
                    if not trade or user_id not in {trade["initiator_id"], trade["partner_id"]}:
                        return web.json_response({"error": "This trade is not open for your account."}, status=409)
                    if payload["coins"] > player["coins"] or payload["potions"] > player["potions"]:
                        return web.json_response({"error": "Your offer exceeds your current coins or potions."}, status=409)
                    weapon = player["weapon"] if payload["offer_weapon"] else None
                    weapon_attack = player["weapon_attack"] if payload["offer_weapon"] else None
                    armor = player["armor"] if payload["offer_armor"] else None
                    armor_defense = player["armor_defense"] if payload["offer_armor"] else None
                    if user_id == trade["initiator_id"]:
                        await db.execute(
                            """UPDATE trades SET initiator_coins=?,initiator_potions=?,
                               initiator_weapon=?,initiator_weapon_attack=?,initiator_armor=?,initiator_armor_defense=?,
                               initiator_confirmed=0,partner_confirmed=0 WHERE trade_id=? AND status='open'""",
                            (payload["coins"],payload["potions"],weapon,weapon_attack,armor,armor_defense,payload["trade_id"]),
                        )
                    else:
                        await db.execute(
                            """UPDATE trades SET partner_coins=?,partner_potions=?,
                               partner_weapon=?,partner_weapon_attack=?,partner_armor=?,partner_armor_defense=?,
                               initiator_confirmed=0,partner_confirmed=0 WHERE trade_id=? AND status='open'""",
                            (payload["coins"],payload["potions"],weapon,weapon_attack,armor,armor_defense,payload["trade_id"]),
                        )
                    await db.commit()
                    result = {"trade_id":payload["trade_id"],"status":"open","offer_updated":True}
                elif action == "trade_confirm":
                    if set(payload) != {"action", "trade_id"} or type(payload["trade_id"]) is not int or payload["trade_id"] <= 0:
                        return web.json_response({"error": "A valid trade_id is required."}, status=400)
                    trade_cur = await db.execute(
                        "SELECT * FROM trades WHERE trade_id=? AND status='open'", (payload["trade_id"],)
                    )
                    trade = await trade_cur.fetchone()
                    if not trade or user_id not in {trade["initiator_id"], trade["partner_id"]}:
                        return web.json_response({"error": "This trade is not open for your account."}, status=409)
                    if user_id == trade["initiator_id"]:
                        await db.execute("UPDATE trades SET initiator_confirmed=1 WHERE trade_id=? AND status='open'", (payload["trade_id"],))
                    else:
                        await db.execute("UPDATE trades SET partner_confirmed=1 WHERE trade_id=? AND status='open'", (payload["trade_id"],))
                    trade_cur = await db.execute("SELECT * FROM trades WHERE trade_id=?", (payload["trade_id"],))
                    trade = await trade_cur.fetchone()
                    if trade["initiator_confirmed"] and trade["partner_confirmed"]:
                        initiator = await get_player(trade["initiator_id"])
                        partner = await get_player(trade["partner_id"])
                        invalid_equipment = (
                            bool(trade["initiator_weapon"]) != bool(trade["partner_weapon"])
                            or bool(trade["initiator_armor"]) != bool(trade["partner_armor"])
                            or (trade["initiator_weapon"] and (
                                initiator["weapon"] != trade["initiator_weapon"]
                                or initiator["weapon_attack"] != trade["initiator_weapon_attack"]
                            ))
                            or (trade["partner_weapon"] and (
                                partner["weapon"] != trade["partner_weapon"]
                                or partner["weapon_attack"] != trade["partner_weapon_attack"]
                            ))
                            or (trade["initiator_armor"] and (
                                initiator["armor"] != trade["initiator_armor"]
                                or initiator["armor_defense"] != trade["initiator_armor_defense"]
                            ))
                            or (trade["partner_armor"] and (
                                partner["armor"] != trade["partner_armor"]
                                or partner["armor_defense"] != trade["partner_armor_defense"]
                            ))
                        )
                        invalid_balance = (
                            initiator["coins"] < trade["initiator_coins"]
                            or initiator["potions"] < trade["initiator_potions"]
                            or partner["coins"] < trade["partner_coins"]
                            or partner["potions"] < trade["partner_potions"]
                        )
                        if invalid_equipment or invalid_balance:
                            await db.execute(
                                "UPDATE trades SET initiator_confirmed=0,partner_confirmed=0 WHERE trade_id=? AND status='open'",
                                (payload["trade_id"],),
                            )
                            await db.commit()
                            return web.json_response({
                                "error": "Trade paused because an offered item or balance changed. Update offers and confirm again."
                            }, status=409)
                        if not await settle_trade_assets(db, trade, initiator, partner):
                            await db.commit()
                            return web.json_response({
                                "error": "Trade settlement was interrupted safely. No items or currency were transferred; both players must confirm again."
                            }, status=409)
                        result = {"trade_id":payload["trade_id"],"status":"completed"}
                    else:
                        result = {"trade_id":payload["trade_id"],"status":"open","waiting_for_other_player":True}
                    await db.commit()
                elif action == "trade_cancel":
                    if set(payload) != {"action", "trade_id"} or type(payload["trade_id"]) is not int or payload["trade_id"] <= 0:
                        return web.json_response({"error": "A valid trade_id is required."}, status=400)
                    trade_cur = await db.execute(
                        """UPDATE trades SET status='cancelled',initiator_confirmed=0,partner_confirmed=0
                           WHERE trade_id=? AND (initiator_id=? OR partner_id=?) AND status IN ('pending','open')""",
                        (payload["trade_id"],user_id,user_id),
                    )
                    if trade_cur.rowcount != 1:
                        return web.json_response({"error": "This trade cannot be cancelled by you."}, status=409)
                    result = {"trade_id":payload["trade_id"],"status":"cancelled"}
                elif action in {"guild_chat", "guild_send"}:
                    expected = {"action", "message"} if action == "guild_send" else {"action"}
                    if set(payload) != expected:
                        return web.json_response({"error": "Invalid guild chat request fields."}, status=400)
                    if action == "guild_send" and (not isinstance(payload.get("message"), str) or len(payload["message"]) > 500):
                        return web.json_response({"error": "Guild messages must contain 1 to 500 characters."}, status=400)
                    cur = await db.execute("SELECT guild_id FROM guild_members WHERE user_id=?", (user_id,))
                    membership = await cur.fetchone()
                    if not membership:
                        raise GuildFeatureError("Join a guild before using guild chat.")
                    if action == "guild_send":
                        await send_guild_message(db, membership["guild_id"], user_id, payload["message"])
                    rows = await get_guild_chat(db, membership["guild_id"], user_id, limit=30)
                    result = {"messages": [
                        {"message_id":row["message_id"],"user_id":row["user_id"],
                         "username":row["username"] or "Adventurer","message":row["message"],
                         "created_at":row["created_at"]}
                        for row in rows
                    ]}
                else:
                    await record_security_event(db, user_id, "invalid_social_action", action[:80], 2)
                    return web.json_response({"error": "Unsupported social action."}, status=400)
                await db.commit()
                state = await miniapp_state(user)
    except (FriendError, PartyError, GuildFeatureError) as exc:
        return web.json_response({"error": str(exc)}, status=409)
    return web.json_response({"message": "Social action completed.", "result": result, "state": state})


async def api_settings(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    if request.method == "GET":
        async with db_lock:
            return web.json_response(await get_settings(db, user["id"]))
    if request.content_length is not None and request.content_length > 4096:
        return web.json_response({"error": "Settings request is too large."}, status=413)
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "Settings payload must be valid JSON."}, status=400)
    if not isinstance(payload, dict) or set(payload)-{"notifications_enabled","profile_visibility","sound_enabled"}:
        return web.json_response({"error": "Unsupported settings fields."}, status=400)
    try:
        async with db_lock:
            settings = await update_settings(
                db,user["id"],
                notifications_enabled=payload.get("notifications_enabled"),
                profile_visibility=payload.get("profile_visibility"),
                sound_enabled=payload.get("sound_enabled"),
            )
            state = await miniapp_state(user)
    except AccountError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response({"message":"Settings saved.","settings":settings,"state":state})


async def api_appearance(request: web.Request):
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=401)
    if request.content_length is not None and request.content_length > 4096:
        return web.json_response({"error": "Appearance request is too large."}, status=413)
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "Appearance payload must be valid JSON."}, status=400)
    async with db_lock:
        try:
            await save_appearance(db, user["id"], payload)
            state = await miniapp_state(user)
        except AppearanceError as exc:
            return web.json_response({"error": str(exc)}, status=400)
    return web.json_response({"message": "Character appearance saved.", "state": state})

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
    if set(payload) != {"action"}:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_battle_action", "unexpected action fields", 2)
        return web.json_response({"error": "Unsupported battle action fields."}, status=400)
    if not isinstance(action, str) or action not in {"attack", "skill", "potion", "flee"}:
        async with db_lock:
            await record_security_event(db, user["id"], "invalid_battle_action", str(action)[:80], 2)
        return web.json_response({"error": "Unknown battle action."}, status=400)
    user_id = user["id"]
    async with db_lock:
      async with player_locks[user_id]:
        cur = await db.execute("SELECT * FROM battles WHERE user_id=?", (user_id,))
        battle = await cur.fetchone()
        if not battle:
            return web.json_response({"error": "There is no active battle."}, status=409)
        p = await get_player(user_id, user.get("username"))
        monster = build_battle_monster(battle)
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
        else:
            if action == "skill":
                if p["skill_cd"] > 0:
                    return web.json_response({"error": f"Skill cooling down: {p['skill_cd']} turn(s)."}, status=409)
                try:
                    await consume_mana(db, user_id, SKILL_MANA_COST, commit=False)
                except ManaError as exc:
                    return web.json_response({"error": str(exc)}, status=409)
                await db.execute("UPDATE players SET skill_cd=? WHERE user_id=?", (skill_cooldown_for_class(p["hero_class"]), user_id))
            damage, damage_effects = resolve_player_attack(
                action,
                player_level=p["level"],
                class_attack=class_stats["attack"],
                weapon_attack=p["weapon_attack"],
                monster_defense=monster["defense"],
                class_element=class_stats["element"],
                monster_element=monster["element"],
                monster_weakness=monster["weakness"],
                trait_effect=monster["trait_effect"],
                next_turn=battle["turn_count"] + 1,
                random_bonus=random.randint(5, 18) if action == "attack" else 0,
            )
            if action == "skill":
                action_line = f"{class_stats['skill']} deals {damage} damage."
            else:
                action_line = f"You strike for {damage} damage."
            for effect in damage_effects:
                action_line += {
                    "weakness": f" Super effective: {class_stats['element']} hits its weakness.",
                    "resisted": f" {monster['element']} resists your matching element.",
                    "armored": " Its armor absorbs part of the hit.",
                    "shield": " Its shield blocks part of this strike.",
                }[effect]
        new_enemy_hp = max(0, battle["monster_hp"] - damage)
        turn_count = battle["turn_count"] + 1
        if new_enemy_hp > 0 and monster["trait_effect"] == "regenerate":
            new_enemy_hp = min(monster["hp"], new_enemy_hp + max(1, monster["hp"] // 50))
        if new_enemy_hp == 0:
            await restore_mana(db, user_id, TURN_MANA_REGEN, commit=False)
            await db.execute(
                "UPDATE players SET hp=min(max_hp, hp+15), skill_cd=max(0, skill_cd-1) WHERE user_id=?",
                (user_id,),
            )
            message = await finish_battle(user_id, True)
            return web.json_response({"message": f"{action_line} {message}", "state": await miniapp_state(user)})
        p = await get_player(user_id)
        combat_result = resolve_enemy_turn(
            trait_effect=monster["trait_effect"],
            turn_count=turn_count,
            monster_hp_before=battle["monster_hp"],
            monster_hp_after_action=new_enemy_hp,
            monster_max_hp=monster["hp"],
            monster_attack_power=monster["attack_power"],
            monster_speed=monster["speed"],
            player_hp=p["hp"],
            player_max_hp=p["max_hp"],
            player_level=p["level"],
            armor_defense=p["armor_defense"],
            class_defense=class_stats["defense"],
            class_speed=class_stats["speed"],
            player_damage=damage,
            action=action,
            random_bonus=random.randint(-3, 6),
            dodge_roll=random.randint(1, 100),
            is_boss=monster["boss"],
            boss_name=monster["name"],
            hero_class=p["hero_class"],
        )
        new_enemy_hp = combat_result["monster_hp"]
        enemy_damage = combat_result["enemy_damage"]
        evaded = combat_result["evaded"]
        special_turn = combat_result["special_turn"]
        reflect_damage = combat_result["reflect_damage"]
        poison_damage = combat_result["poison_damage"]
        new_hp = combat_result["player_hp"]
        effect_notes = combat_result["effect_notes"]
        effect_text = " " + " ".join(effect_notes) if effect_notes else ""
        await db.execute(
            "UPDATE battles SET monster_hp=?, turn_count=? WHERE user_id=?",
            (new_enemy_hp, turn_count, user_id),
        )
        await db.execute(
            "UPDATE players SET hp=?, skill_cd=max(0, skill_cd-1) WHERE user_id=?",
            (new_hp, user_id),
        )
        await restore_mana(db, user_id, TURN_MANA_REGEN, commit=False)
        if new_hp == 0:
            message = await finish_battle(user_id, False)
            return web.json_response({
                "message": f"{action_line} {monster['name']} hits you for {enemy_damage}.{effect_text} {message}",
                "state": await miniapp_state(user),
            })
        await db.commit()
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


async def database_backup_loop():
    """Take a verified SQLite snapshot on startup and every configured interval."""
    while True:
        try:
            backup_path = await asyncio.to_thread(
                create_backup, DB_PATH, BACKUP_DIR, BACKUP_RETENTION
            )
            log.info("Verified database backup created: %s", backup_path)
        except Exception:
            log.exception("Database backup failed; live game database remains untouched")
        await asyncio.sleep(BACKUP_INTERVAL_SECONDS)


async def database_healthcheck() -> bool:
    if db is None:
        return False
    try:
        async with db_lock:
            cur = await db.execute("SELECT 1")
            return await cur.fetchone() is not None
    except Exception:
        log.exception("Health check database probe failed")
        return False


api_rate_limiter = SlidingWindowRateLimiter(window_seconds=60)
api_route_rate_limiter = SlidingWindowRateLimiter(window_seconds=60)
rate_limit_event_limiter = SlidingWindowRateLimiter(window_seconds=60)
API_ROUTE_LIMITS = {
    "/api/action": 20,
    "/api/explore": 15,
    "/api/social": 20,
    "/api/premium-shop": 6,
    "/api/world": 15,
    "/api/dungeon": 15,
}


@web.middleware
async def miniapp_rate_limit(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    try:
        user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), TOKEN)
    except ValueError:
        # The route returns the canonical authentication error.
        return await handler(request)
    if db is not None and user["id"] not in ADMIN_IDS:
        async with db_lock:
            ban = await get_active_ban(db, user["id"])
        if ban:
            return web.json_response({"error": "Game account suspended.", "reason": ban["reason"]}, status=403)
    global_limit = 120 if request.method == "GET" else 40
    allowed, retry_after = api_rate_limiter.allow(
        f"telegram:{user['id']}:{request.method}", global_limit
    )
    route_limit = API_ROUTE_LIMITS.get(request.path)
    if allowed and route_limit is not None:
        allowed, retry_after = api_route_rate_limiter.allow(
            f"telegram:{user['id']}:{request.path}", route_limit
        )
    if not allowed:
        # Do not turn every blocked retry into another database write.
        should_log, _ = rate_limit_event_limiter.allow(f"rate-event:{user['id']}", 1)
        if should_log and db is not None:
            try:
                async with db_lock:
                    await record_security_event(
                        db, user["id"], "repeated_rate_limit", request.path, 2
                    )
            except Exception:
                log.exception("Unable to record Mini App rate-limit event")
        return web.json_response(
            {"error": "Too many requests. Please slow down and try again."},
            status=429,
            headers={"Retry-After": str(retry_after)},
        )
    return await handler(request)


async def start_web_server():
    async def serve_index(request: web.Request):
        return web.FileResponse(WEB_DIR / "index.html")

    async def serve_css(request: web.Request):
        return web.FileResponse(WEB_DIR / "style.css")

    async def serve_js(request: web.Request):
        return web.FileResponse(WEB_DIR / "game.js")

    async def healthz(request: web.Request):
        if not await database_healthcheck():
            return web.json_response({"ok": False, "database": "unavailable"}, status=503)
        return web.json_response(
            {"ok": True, "service": "peak-adventure", "database": "ok"},
            headers={"Cache-Control": "no-store"},
        )

    app = web.Application(client_max_size=4096, middlewares=[miniapp_rate_limit])
    app.router.add_get("/", serve_index)
    app.router.add_get("/style.css", serve_css)
    app.router.add_get("/game.js", serve_js)
    app.router.add_get("/api/state", api_state)
    app.router.add_post("/api/dungeon", api_dungeon)
    app.router.add_post("/api/explore", api_explore)
    app.router.add_post("/api/action", api_action)
    app.router.add_post("/api/appearance", api_appearance)
    app.router.add_route("*", "/api/settings", api_settings)
    app.router.add_post("/api/story", api_story)
    app.router.add_post("/api/quest/claim", api_quest_claim)
    app.router.add_post("/api/daily-mission/claim", api_daily_mission_claim)
    app.router.add_post("/api/weekly-quest/claim", api_weekly_quest_claim)
    app.router.add_post("/api/world", api_world)
    app.router.add_post("/api/social", api_social)
    app.router.add_post("/api/premium-shop", api_premium_shop)
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
    backup_task = asyncio.create_task(database_backup_loop(), name="database-backups")
    runner = None
    try:
        runner = await start_web_server()
        log.info("Starting The Peak Adventure bot")
        await dp.start_polling(bot)
    finally:
        backup_task.cancel()
        try:
            await backup_task
        except asyncio.CancelledError:
            pass
        if runner is not None:
            await runner.cleanup()
        await bot.session.close()
        if db:
            await db.close()


if __name__ == "__main__":
    asyncio.run(main())
