"""The Peak Music Bot: Telegram group voice-chat music player."""
import asyncio
import logging
import os
from collections import defaultdict, deque
from typing import Any

from dotenv import load_dotenv
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from yt_dlp import YoutubeDL

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("peak-music")

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
STRING_SESSION = os.environ["STRING_SESSION"]

bot = Client("peak_music_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
assistant = Client("peak_music_assistant", api_id=API_ID, api_hash=API_HASH, session_string=STRING_SESSION)
calls: PyTgCalls | None = None
queues: dict[int, deque[dict[str, Any]]] = defaultdict(deque)
playing: dict[int, dict[str, Any]] = {}


def extract_track(query: str) -> dict[str, Any]:
    options = {"format": "bestaudio/best", "quiet": True, "no_warnings": True, "noplaylist": True, "default_search": "ytsearch"}
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            info = next((item for item in info["entries"] if item), None)
        if not info:
            raise ValueError("No playable result found.")
        return {"title": info.get("title") or "Unknown title", "url": info["url"], "duration": info.get("duration")}


def duration_text(seconds: int | None) -> str:
    if not seconds:
        return "Live / unknown"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


async def start_track(chat_id: int, track: dict[str, Any]) -> None:
    assert calls is not None
    await calls.play(chat_id, MediaStream(track["url"]))
    playing[chat_id] = track


@bot.on_message(filters.command(["start", "help"]))
async def help_command(_: Client, message: Message) -> None:
    await message.reply_text(
        "🎧 **The Peak Music Bot**\n\n"
        "Add the assistant account to your group and start a voice chat first.\n\n"
        "**Commands**\n"
        "/play <song name or YouTube URL> - Play or add to queue\n"
        "/queue - Show upcoming songs\n"
        "/skip - Skip current song\n"
        "/pause - Pause playback\n"
        "/resume - Resume playback\n"
        "/stop - Stop and clear queue\n"
        "/help - Show help\n\n"
        "Voice playback requires a Linux server, FFmpeg, and an assistant user session."
    )


@bot.on_message(filters.command("play") & filters.group)
async def play_command(_: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text("Usage: /play <song name or YouTube URL>")
        return
    status = await message.reply_text("🔎 Finding your track...")
    try:
        track = await asyncio.to_thread(extract_track, message.text.split(maxsplit=1)[1].strip())
        chat_id = message.chat.id
        if chat_id in playing:
            queues[chat_id].append(track)
            await status.edit_text(f"➕ **Added to queue**\n🎵 {track['title']}\n📋 Position: {len(queues[chat_id])}")
        else:
            await start_track(chat_id, track)
            await status.edit_text(f"▶️ **Now playing**\n🎵 {track['title']}\n⏱ {duration_text(track['duration'])}")
    except Exception as exc:
        log.exception("Could not play requested track")
        await status.edit_text(f"❌ Couldn't start the track. Check that a voice chat is active, the assistant is in the group, and FFmpeg is installed.\nError: {type(exc).__name__}")


@bot.on_message(filters.command("queue") & filters.group)
async def queue_command(_: Client, message: Message) -> None:
    chat_id = message.chat.id
    current, upcoming = playing.get(chat_id), list(queues[chat_id])
    if not current and not upcoming:
        await message.reply_text("📭 The queue is empty.")
        return
    lines = ["🎶 **Music Queue**"]
    if current:
        lines.append(f"\n▶️ **Now:** {current['title']}")
    for i, track in enumerate(upcoming[:10], 1):
        lines.append(f"\n{i}. {track['title']}")
    if len(upcoming) > 10:
        lines.append(f"\n...and {len(upcoming) - 10} more.")
    await message.reply_text("".join(lines))


@bot.on_message(filters.command("skip") & filters.group)
async def skip_command(_: Client, message: Message) -> None:
    chat_id = message.chat.id
    if chat_id not in playing:
        await message.reply_text("Nothing is playing right now.")
        return
    try:
        assert calls is not None
        await calls.leave_call(chat_id)
        playing.pop(chat_id, None)
        if queues[chat_id]:
            track = queues[chat_id].popleft()
            await start_track(chat_id, track)
            await message.reply_text(f"⏭️ Skipped. Now playing: **{track['title']}**")
        else:
            await message.reply_text("⏭️ Track skipped. Queue is empty.")
    except Exception:
        log.exception("Skip failed")
        await message.reply_text("Couldn't skip the current track.")


@bot.on_message(filters.command("pause") & filters.group)
async def pause_command(_: Client, message: Message) -> None:
    try:
        assert calls is not None
        await calls.pause_stream(message.chat.id)
        await message.reply_text("⏸️ Playback paused.")
    except Exception:
        await message.reply_text("Nothing is playing, or pause isn't available.")


@bot.on_message(filters.command("resume") & filters.group)
async def resume_command(_: Client, message: Message) -> None:
    try:
        assert calls is not None
        await calls.resume_stream(message.chat.id)
        await message.reply_text("▶️ Playback resumed.")
    except Exception:
        await message.reply_text("Nothing is paused right now.")


@bot.on_message(filters.command("stop") & filters.group)
async def stop_command(_: Client, message: Message) -> None:
    chat_id = message.chat.id
    try:
        assert calls is not None
        await calls.leave_call(chat_id)
    except Exception:
        log.exception("Leave call failed")
    playing.pop(chat_id, None)
    queues[chat_id].clear()
    await message.reply_text("⏹️ Playback stopped and queue cleared.")


async def main() -> None:
    global calls
    log.info("Starting The Peak Music Bot...")
    await assistant.start()
    calls = PyTgCalls(assistant)
    await calls.start()
    await bot.start()
    log.info("The Peak Music Bot is online.")
    try:
        await idle()
    finally:
        await bot.stop()
        await calls.stop()
        await assistant.stop()


if __name__ == "__main__":
    asyncio.run(main())
