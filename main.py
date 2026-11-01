"""The Peak Adventure - Telegram turn-based RPG bot."""
import asyncio
import json
import logging
import os
import random
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DATABASE_PATH", "peak_adventure.db")
MONSTERS = json.loads(Path(__file__).with_name("monsters.json").read_text(encoding="utf-8"))
MONSTER_BY_LEVEL = {m["level"]: m for m in MONSTERS}
BOSS_LEVELS = {10, 20, 30, 40, 50, 60, 70, 80, 90, 100}

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("peak-adventure")
dp = Dispatcher()
db: aiosqlite.Connection | None = None


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
      skill_cd INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS battles (
      user_id INTEGER PRIMARY KEY, monster_level INTEGER NOT NULL,
      monster_hp INTEGER NOT NULL, message_id INTEGER
    );
    """)
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺️ Explore", callback_data="explore"),
         InlineKeyboardButton(text="👤 Profile", callback_data="profile")],
        [InlineKeyboardButton(text="🎒 Inventory", callback_data="inventory"),
         InlineKeyboardButton(text="📜 Quests", callback_data="quests")],
        [InlineKeyboardButton(text="🎁 Daily Reward", callback_data="daily"),
         InlineKeyboardButton(text="🏆 Leaderboard", callback_data="leaderboard")],
    ])


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
    return (f"👤 <b>{p['username'] or 'Adventurer'}</b>\n"
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
        f"✨ Special: {m['special_move']}"
    )
    if edit:
        await target.edit_text(text, reply_markup=battle_keyboard())
    else:
        sent = await target.answer(text, reply_markup=battle_keyboard())
        await db.execute("UPDATE battles SET message_id=? WHERE user_id=?", (sent.message_id, user_id))
        await db.commit()


async def start_battle(user_id: int, username: str | None, send_target):
    assert db is not None
    p = await get_player(user_id, username)
    cur = await db.execute("SELECT 1 FROM battles WHERE user_id=?", (user_id,))
    if await cur.fetchone():
        await send_target.answer("⚔️ Tumhari battle pehle se chal rahi hai. Uske buttons use karo.")
        return
    if p["hp"] <= 0:
        await db.execute("UPDATE players SET hp=max_hp WHERE user_id=?", (user_id,))
        await db.commit()
        p = await get_player(user_id)
    level = p["level"]
    if level in BOSS_LEVELS:
        monster_level = level
    else:
        monster_level = max(1, min(100, level + random.choice([-1, 0, 0, 0, 1])))
    m = MONSTER_BY_LEVEL[monster_level]
    await db.execute("INSERT INTO battles(user_id, monster_level, monster_hp) VALUES (?, ?, ?)",
                     (user_id, monster_level, m["hp"]))
    await db.commit()
    await send_battle(send_target, user_id, "🌲 <b>You enter the wilds...</b>")


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
        await db.execute("UPDATE players SET hp=1 WHERE user_id=?", (user_id,))
        await db.commit()
        return "💀 You were defeated. You wake at the camp with 1 HP. Heal before exploring again."
    p = await get_player(user_id)
    reward_xp = 35 + m["level"] * 18 + (m["level"] * 30 if m["boss"] else 0)
    reward_coins = 15 + m["level"] * 7 + (m["level"] * 25 if m["boss"] else 0)
    new_xp, new_level = p["xp"] + reward_xp, p["level"]
    while new_level < 100 and new_xp >= xp_needed(new_level):
        new_xp -= xp_needed(new_level)
        new_level += 1
    new_max = 120 + (new_level - 1) * 20
    await db.execute("""UPDATE players SET xp=?, level=?, coins=coins+?, wins=wins+1,
        max_hp=?, hp=min(?, ?) WHERE user_id=?""",
        (new_xp, new_level, reward_coins, new_max, p["hp"] + 25, new_max, user_id))
    await db.commit()
    level_note = f"\n🌟 LEVEL UP! You reached level {new_level}." if new_level > p["level"] else ""
    boss_note = "\n👑 The boss seal has weakened. A fragment of the world's lost memory returns..." if m["boss"] else ""
    return f"🏆 <b>Victory!</b> {m['name']} defeated.\n✨ +{reward_xp} XP\n🪙 +{reward_coins} coins{level_note}{boss_note}"


@dp.message(Command("start"))
async def start(message: Message):
    await get_player(message.from_user.id, message.from_user.username or message.from_user.full_name)
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
        "/leaderboard - Top adventurers\n/heal - Restore HP (uses 30 coins)\n\n"
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
    await message.answer(f"🎒 <b>Inventory</b>\n🧪 Health Potions: {p['potions']}\n🪙 Coins: {p['coins']}\n\nUse /heal to restore HP for 30 coins.")


@dp.message(Command("heal"))
async def heal(message: Message):
    p = await get_player(message.from_user.id)
    if p["hp"] >= p["max_hp"]:
        await message.answer("❤️ Your HP is already full.")
    elif p["coins"] < 30:
        await message.answer("🪙 You need 30 coins to heal.")
    else:
        await db.execute("UPDATE players SET coins=coins-30, hp=max_hp WHERE user_id=?", (message.from_user.id,))
        await db.commit()
        await message.answer("✨ Your HP has been fully restored.")


@dp.message(Command("map"))
async def map_cmd(message: Message):
    p = await get_player(message.from_user.id)
    worlds = ["🌱 Whispering Meadow", "🌲 Gloomwood Forest", "🏜️ Ashen Desert", "❄️ Frostfang Peaks",
              "🌋 Ember Abyss", "🏰 Hollow Kingdom", "🌌 Celestial Ruins", "🕳️ The Primordial Rift",
              "👁️ Eternal Throne", "🌠 Alpha Realm"]
    idx = min(9, (p["level"] - 1) // 10)
    await message.answer(f"🗺️ <b>World Map</b>\nCurrent region: <b>{worlds[idx]}</b>\nProgress: Level {p['level']}/100\nBoss gates: levels 10, 20, 30 ... 100.")


@dp.message(Command("quests"))
async def quests(message: Message):
    p = await get_player(message.from_user.id)
    await message.answer(
        "📜 <b>Story Quests</b>\n"
        f"1. First Steps: reach level 2 ({'✅' if p['level'] >= 2 else '🔒'})\n"
        f"2. The First Seal: defeat the level 10 boss ({'✅' if p['wins'] >= 10 else '🔒'})\n"
        "3. A Fractured World: uncover the truth behind the changing monsters (story progression).\n"
        "Quest tracking will expand as the campaign is developed.")


@dp.message(Command("daily"))
async def daily(message: Message):
    # Daily cooldown is intentionally simple in this first playable version.
    p = await get_player(message.from_user.id)
    await db.execute("UPDATE players SET coins=coins+50, potions=potions+1 WHERE user_id=?", (message.from_user.id,))
    await db.commit()
    await message.answer("🎁 Daily starter reward: +50 coins and +1 potion. (Daily claim cooldown will be added in the next update.)")


@dp.message(Command("leaderboard"))
async def leaderboard(message: Message):
    cur = await db.execute("SELECT username, level, wins FROM players ORDER BY level DESC, wins DESC LIMIT 10")
    rows = await cur.fetchall()
    if not rows:
        await message.answer("No adventurers yet.")
        return
    lines = ["🏆 <b>Top Adventurers</b>"]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. {row['username'] or 'Adventurer'} · Lv.{row['level']} · {row['wins']} wins")
    await message.answer("\n".join(lines))


@dp.callback_query(F.data == "explore")
async def cb_explore(call: CallbackQuery):
    await call.answer()
    await start_battle(call.from_user.id, call.from_user.username, call.message)


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
    p = await get_player(call.from_user.id)
    await call.message.answer(f"📜 <b>Story Progress</b>\nCurrent level: {p['level']}/100\nNext milestone: boss level {min(100, ((p['level']//10)+1)*10)}")


@dp.callback_query(F.data == "daily")
async def cb_daily(call: CallbackQuery):
    await call.answer()
    await db.execute("UPDATE players SET coins=coins+50, potions=potions+1 WHERE user_id=?", (call.from_user.id,))
    await db.commit()
    await call.message.answer("🎁 +50 coins and +1 potion added. Daily cooldown is not yet enforced in this first playable version.")


@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    await call.answer()
    cur = await db.execute("SELECT username, level, wins FROM players ORDER BY level DESC, wins DESC LIMIT 10")
    rows = await cur.fetchall()
    await call.message.answer("🏆 <b>Leaderboard</b>\n" + "\n".join(
        f"{i}. {r['username'] or 'Adventurer'} · Lv.{r['level']} · {r['wins']} wins" for i, r in enumerate(rows, 1)))


@dp.callback_query(F.data.startswith("battle:"))
async def battle_action(call: CallbackQuery):
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
    action = call.data.split(":", 1)[1]
    if action == "flee":
        result = await finish_battle(user_id, False, escaped=True)
        await call.message.edit_text(result, reply_markup=menu())
        return
    if action == "potion":
        if p["potions"] <= 0:
            await call.answer("No potions left!", show_alert=True)
            return
        heal_amount = min(80, p["max_hp"] - p["hp"])
        if heal_amount <= 0:
            await call.answer("HP is already full.", show_alert=True)
            return
        await db.execute("UPDATE players SET potions=potions-1, hp=hp+? WHERE user_id=?", (heal_amount, user_id))
        damage = 0
        action_line = f"🧪 You recover {heal_amount} HP."
    elif action == "skill":
        if p["skill_cd"] > 0:
            await call.answer(f"Skill cooling down: {p['skill_cd']} turn(s).", show_alert=True)
            return
        damage = max(25, (p["level"] * 13 + 30) - m["defense"] // 2) * 2
        await db.execute("UPDATE players SET skill_cd=3 WHERE user_id=?", (user_id,))
        action_line = f"🔥 <b>Peak Strike!</b> You deal {damage} damage."
    else:
        damage = max(8, p["level"] * 10 + random.randint(5, 18) - m["defense"] // 3)
        action_line = f"⚔️ You strike for {damage} damage."
    new_enemy_hp = max(0, b["monster_hp"] - damage)
    if new_enemy_hp == 0:
        await db.execute("UPDATE players SET hp=min(max_hp, hp+15), skill_cd=max(0, skill_cd-1) WHERE user_id=?", (user_id,))
        await db.commit()
        result = await finish_battle(user_id, True)
        await call.message.edit_text(f"{action_line}\n\n{result}", reply_markup=menu())
        return
    p = await get_player(user_id)
    enemy_damage = max(3, m["attack_power"] - p["level"] * 2 + random.randint(-3, 6))
    new_hp = max(0, p["hp"] - enemy_damage)
    await db.execute("UPDATE battles SET monster_hp=? WHERE user_id=?", (new_enemy_hp, user_id))
    await db.execute("UPDATE players SET hp=?, skill_cd=max(0, skill_cd-1) WHERE user_id=?", (new_hp, user_id))
    await db.commit()
    if new_hp == 0:
        result = await finish_battle(user_id, False)
        await call.message.edit_text(f"{action_line}\n💥 {m['name']} hits you for {enemy_damage}.\n\n{result}", reply_markup=menu())
        return
    await send_battle(call.message, user_id, f"{action_line}\n💥 {m['name']} hits you for {enemy_damage}.")


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it to your .env file.")
    await init_db()
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    log.info("Starting The Peak Adventure bot")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        if db:
            await db.close()


if __name__ == "__main__":
    asyncio.run(main())
