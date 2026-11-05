"""Ambient monster encounters triggered by ordinary Telegram group chat activity."""
from __future__ import annotations

import random
import uuid

MESSAGE_MIN = 150
MESSAGE_MAX = 200
COOLDOWN_MIN_SECONDS = 10 * 60
COOLDOWN_MAX_SECONDS = 20 * 60
EVENT_LIFETIME_SECONDS = 20 * 60
ATTACK_COOLDOWN_SECONDS = 10


class GroupChatEventError(ValueError):
    """Raised when a group chat event action is invalid or unavailable."""


def _valid_id(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value == 0:
        raise GroupChatEventError(f"Invalid {label}.")
    return value


async def init_group_chat_event_tables(connection) -> None:
    """Create portable SQLite/PostgreSQL tables for persistent ambient encounters."""
    user_id_type = "BIGINT" if getattr(connection, "dialect", "sqlite") == "postgres" else "INTEGER"
    await connection.execute(
        f"""CREATE TABLE IF NOT EXISTS group_chat_event_state (
            chat_id {user_id_type} PRIMARY KEY,
            message_count INTEGER NOT NULL DEFAULT 0,
            target_messages INTEGER NOT NULL,
            next_spawn_at BIGINT NOT NULL,
            active_event_id TEXT,
            enabled INTEGER NOT NULL DEFAULT 1
        )"""
    )
    await connection.execute(
        f"""CREATE TABLE IF NOT EXISTS group_chat_events (
            event_id TEXT PRIMARY KEY,
            chat_id {user_id_type} NOT NULL,
            monster_level INTEGER NOT NULL,
            monster_name TEXT NOT NULL,
            hp INTEGER NOT NULL,
            max_hp INTEGER NOT NULL,
            status TEXT NOT NULL,
            spawned_at BIGINT NOT NULL,
            expires_at BIGINT NOT NULL
        )"""
    )
    await connection.execute(
        f"""CREATE TABLE IF NOT EXISTS group_chat_event_participants (
            event_id TEXT NOT NULL,
            user_id {user_id_type} NOT NULL,
            damage INTEGER NOT NULL DEFAULT 0,
            last_attack_at BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY(event_id, user_id)
        )"""
    )
    await connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_group_chat_events_chat_status "
        "ON group_chat_events(chat_id, status)"
    )
    await connection.commit()


async def _registered_group_level(connection, chat_id: int):
    cursor = await connection.execute(
        "SELECT group_level FROM group_profiles WHERE chat_id=?",
        (chat_id,),
    )
    return await cursor.fetchone()


async def _ensure_state(connection, chat_id: int, now: int, rng) -> None:
    cursor = await connection.execute(
        "SELECT chat_id FROM group_chat_event_state WHERE chat_id=?",
        (chat_id,),
    )
    if await cursor.fetchone() is not None:
        return
    await connection.execute(
        """INSERT INTO group_chat_event_state
           (chat_id,message_count,target_messages,next_spawn_at,active_event_id,enabled)
           VALUES(?,0,?,?,NULL,1) ON CONFLICT(chat_id) DO NOTHING""",
        (
            chat_id,
            rng.randint(MESSAGE_MIN, MESSAGE_MAX),
            now + rng.randint(COOLDOWN_MIN_SECONDS, COOLDOWN_MAX_SECONDS),
        ),
    )


async def record_group_chat_message(
    connection,
    chat_id: int,
    user_id: int,
    monsters: list[dict],
    *,
    now: int | None = None,
    rng=random,
):
    """Count one eligible human message and spawn an encounter when both gates pass."""
    chat_id = _valid_id(chat_id, "chat")
    user_id = _valid_id(user_id, "user")
    stamp = int(__import__("time").time()) if now is None else now
    if not isinstance(stamp, int) or isinstance(stamp, bool) or stamp < 0:
        raise GroupChatEventError("Invalid event timestamp.")

    group = await _registered_group_level(connection, chat_id)
    if group is None:
        return None
    await _ensure_state(connection, chat_id, stamp, rng)

    cursor = await connection.execute(
        "SELECT * FROM group_chat_event_state WHERE chat_id=?",
        (chat_id,),
    )
    state = await cursor.fetchone()
    if not state or not state["enabled"]:
        return None

    if state["active_event_id"]:
        cursor = await connection.execute(
            "SELECT status,expires_at FROM group_chat_events WHERE event_id=? AND chat_id=?",
            (state["active_event_id"], chat_id),
        )
        active = await cursor.fetchone()
        if active and active["status"] == "active" and active["expires_at"] > stamp:
            await connection.commit()
            return None
        if active and active["status"] == "active":
            await connection.execute(
                "UPDATE group_chat_events SET status='expired' WHERE event_id=?",
                (state["active_event_id"],),
            )
        await connection.execute(
            """UPDATE group_chat_event_state SET active_event_id=NULL,message_count=1,
               target_messages=?,next_spawn_at=? WHERE chat_id=?""",
            (
                rng.randint(MESSAGE_MIN, MESSAGE_MAX),
                stamp + rng.randint(COOLDOWN_MIN_SECONDS, COOLDOWN_MAX_SECONDS),
                chat_id,
            ),
        )
        await connection.commit()
        return None

    message_count = state["message_count"] + 1
    await connection.execute(
        "UPDATE group_chat_event_state SET message_count=? WHERE chat_id=?",
        (message_count, chat_id),
    )
    if message_count < state["target_messages"] or stamp < state["next_spawn_at"]:
        await connection.commit()
        return None

    eligible = [
        monster for monster in monsters
        if isinstance(monster, dict)
        and isinstance(monster.get("level"), int)
        and monster["level"] <= max(10, int(group["group_level"] or 1) * 5)
    ]
    if not eligible:
        eligible = [monster for monster in monsters if isinstance(monster, dict)]
    if not eligible:
        await connection.commit()
        return None

    monster = rng.choice(eligible)
    monster_name = str(monster.get("name") or "Wandering Horror")[:80]
    monster_level = max(1, int(monster.get("level", 1)))
    base_hp = max(30, int(monster.get("hp", 30)))
    max_hp = min(100000, base_hp * 3)
    event_id = uuid.uuid4().hex
    await connection.execute(
        """INSERT INTO group_chat_events
           (event_id,chat_id,monster_level,monster_name,hp,max_hp,status,spawned_at,expires_at)
           VALUES(?,?,?,?,?,?,'active',?,?)""",
        (event_id, chat_id, monster_level, monster_name, max_hp, max_hp, stamp, stamp + EVENT_LIFETIME_SECONDS),
    )
    await connection.execute(
        """UPDATE group_chat_event_state SET message_count=0,target_messages=?,
           next_spawn_at=?,active_event_id=? WHERE chat_id=?""",
        (
            rng.randint(MESSAGE_MIN, MESSAGE_MAX),
            stamp + rng.randint(COOLDOWN_MIN_SECONDS, COOLDOWN_MAX_SECONDS),
            event_id,
            chat_id,
        ),
    )
    await connection.commit()
    return {
        "event_id": event_id,
        "monster_name": monster_name,
        "monster_level": monster_level,
        "hp": max_hp,
        "max_hp": max_hp,
        "expires_at": stamp + EVENT_LIFETIME_SECONDS,
    }


async def get_active_group_chat_event(connection, chat_id: int, *, now: int | None = None):
    chat_id = _valid_id(chat_id, "chat")
    stamp = int(__import__("time").time()) if now is None else now
    cursor = await connection.execute(
        """SELECT e.* FROM group_chat_event_state s
           JOIN group_chat_events e ON e.event_id=s.active_event_id
           WHERE s.chat_id=? AND s.enabled=1 AND e.status='active'""",
        (chat_id,),
    )
    event = await cursor.fetchone()
    if event and event["expires_at"] <= stamp:
        await connection.execute(
            "UPDATE group_chat_events SET status='expired' WHERE event_id=? AND status='active'",
            (event["event_id"],),
        )
        await connection.execute(
            "UPDATE group_chat_event_state SET active_event_id=NULL,message_count=0 WHERE chat_id=?",
            (chat_id,),
        )
        await connection.commit()
        return None
    if not event:
        return None
    cursor = await connection.execute(
        """SELECT p.user_id,p.damage,pl.username FROM group_chat_event_participants p
           LEFT JOIN players pl ON pl.user_id=p.user_id
           WHERE p.event_id=? ORDER BY p.damage DESC,p.user_id ASC""",
        (event["event_id"],),
    )
    participants = await cursor.fetchall()
    return {**dict(event), "participants": [dict(row) for row in participants]}


async def attack_group_chat_event(
    connection,
    chat_id: int,
    user_id: int,
    damage: int,
    *,
    now: int | None = None,
    rng=random,
):
    """Apply a shared-HP hit with per-player cooldown and return victory contributors."""
    chat_id = _valid_id(chat_id, "chat")
    user_id = _valid_id(user_id, "user")
    if not isinstance(damage, int) or isinstance(damage, bool) or damage <= 0:
        raise GroupChatEventError("Damage must be a positive integer.")
    stamp = int(__import__("time").time()) if now is None else now
    cursor = await connection.execute(
        """SELECT e.* FROM group_chat_event_state s
           JOIN group_chat_events e ON e.event_id=s.active_event_id
           WHERE s.chat_id=? AND s.enabled=1 AND e.status='active'""",
        (chat_id,),
    )
    event = await cursor.fetchone()
    if not event:
        raise GroupChatEventError("There is no active group monster. Keep chatting until one appears.")
    if event["expires_at"] <= stamp:
        await connection.execute(
            "UPDATE group_chat_events SET status='expired' WHERE event_id=?",
            (event["event_id"],),
        )
        await connection.execute(
            "UPDATE group_chat_event_state SET active_event_id=NULL,message_count=0 WHERE chat_id=?",
            (chat_id,),
        )
        await connection.commit()
        raise GroupChatEventError("The monster escaped before your attack.")
    cursor = await connection.execute(
        "SELECT last_attack_at FROM group_chat_event_participants WHERE event_id=? AND user_id=?",
        (event["event_id"], user_id),
    )
    previous = await cursor.fetchone()
    if previous and stamp - previous["last_attack_at"] < ATTACK_COOLDOWN_SECONDS:
        raise GroupChatEventError("Attack cooldown: wait a few seconds before attacking again.")
    new_hp = max(0, event["hp"] - damage)
    await connection.execute(
        """INSERT INTO group_chat_event_participants(event_id,user_id,damage,last_attack_at)
           VALUES(?,?,?,?) ON CONFLICT(event_id,user_id) DO UPDATE SET
           damage=group_chat_event_participants.damage+excluded.damage,
           last_attack_at=excluded.last_attack_at""",
        (event["event_id"], user_id, min(damage, event["hp"]), stamp),
    )
    status = "won" if new_hp == 0 else "active"
    await connection.execute(
        "UPDATE group_chat_events SET hp=?,status=? WHERE event_id=?",
        (new_hp, status, event["event_id"]),
    )
    contributors = []
    if status == "won":
        cursor = await connection.execute(
            """SELECT p.user_id,p.damage,pl.username FROM group_chat_event_participants p
               LEFT JOIN players pl ON pl.user_id=p.user_id
               WHERE p.event_id=? ORDER BY p.damage DESC,p.user_id ASC""",
            (event["event_id"],),
        )
        contributors = [dict(row) for row in await cursor.fetchall()]
        await connection.execute(
            """UPDATE group_chat_event_state SET active_event_id=NULL,message_count=0,
               target_messages=?,next_spawn_at=? WHERE chat_id=?""",
            (
                rng.randint(MESSAGE_MIN, MESSAGE_MAX),
                stamp + rng.randint(COOLDOWN_MIN_SECONDS, COOLDOWN_MAX_SECONDS),
                chat_id,
            ),
        )
    await connection.commit()
    return {
        "event_id": event["event_id"],
        "monster_name": event["monster_name"],
        "monster_level": event["monster_level"],
        "hp": new_hp,
        "max_hp": event["max_hp"],
        "damage": min(damage, event["hp"]),
        "status": status,
        "participants": contributors,
    }
