"""Persistent party management for The Peak Adventure."""
from __future__ import annotations

import aiosqlite


MAX_PARTY_SIZE = 4


class PartyError(ValueError):
    """A party operation cannot be completed."""


def _valid_id(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


async def init_party_tables(db: aiosqlite.Connection) -> None:
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS parties (
      party_id INTEGER PRIMARY KEY AUTOINCREMENT,
      leader_id INTEGER NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS party_members (
      user_id INTEGER PRIMARY KEY,
      party_id INTEGER NOT NULL REFERENCES parties(party_id) ON DELETE CASCADE,
      joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS party_invites (
      invite_id INTEGER PRIMARY KEY AUTOINCREMENT,
      party_id INTEGER NOT NULL REFERENCES parties(party_id) ON DELETE CASCADE,
      inviter_id INTEGER NOT NULL,
      target_id INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','accepted','declined','cancelled')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      responded_at TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_party_pending_target
      ON party_invites(target_id) WHERE status='pending';
    CREATE INDEX IF NOT EXISTS idx_party_members_party
      ON party_members(party_id, joined_at);
    """)

    CREATE TABLE IF NOT EXISTS party_battles(
      battle_id INTEGER PRIMARY KEY AUTOINCREMENT,party_id INTEGER NOT NULL,monster_level INTEGER NOT NULL,
      monster_name TEXT NOT NULL,max_hp INTEGER NOT NULL,hp INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','won')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS party_battle_contributions(
      battle_id INTEGER NOT NULL,user_id INTEGER NOT NULL,damage INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(battle_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS party_battle_cooldowns(
      battle_id INTEGER NOT NULL,user_id INTEGER NOT NULL,last_attack_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(battle_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS party_battle_rewards(
      battle_id INTEGER NOT NULL,user_id INTEGER NOT NULL,claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(battle_id,user_id)
    );
    await db.commit()


async def create_party(db: aiosqlite.Connection, leader_id: int) -> int:
    if not _valid_id(leader_id):
        raise PartyError("Invalid player account.")
    cur = await db.execute("SELECT party_id FROM party_members WHERE user_id=?", (leader_id,))
    if await cur.fetchone():
        raise PartyError("You are already in a party. Leave it first.")
    cur = await db.execute("INSERT INTO parties(leader_id) VALUES(?)", (leader_id,))
    party_id = int(cur.lastrowid)
    await db.execute("INSERT INTO party_members(user_id,party_id) VALUES(?,?)", (leader_id, party_id))
    await db.commit()
    return party_id


async def invite_to_party(
    db: aiosqlite.Connection, party_id: int, inviter_id: int, target_id: int
) -> int:
    if not all(_valid_id(value) for value in (party_id, inviter_id, target_id)):
        raise PartyError("Invalid party or player account.")
    if inviter_id == target_id:
        raise PartyError("You cannot invite yourself.")
    cur = await db.execute("SELECT leader_id FROM parties WHERE party_id=?", (party_id,))
    party = await cur.fetchone()
    if not party:
        raise PartyError("Party not found.")
    if party["leader_id"] != inviter_id:
        raise PartyError("Only the party leader can invite players.")
    cur = await db.execute("SELECT 1 FROM party_members WHERE user_id=?", (target_id,))
    if await cur.fetchone():
        raise PartyError("That player is already in a party.")
    cur = await db.execute("SELECT COUNT(*) AS total FROM party_members WHERE party_id=?", (party_id,))
    if (await cur.fetchone())["total"] >= MAX_PARTY_SIZE:
        raise PartyError(f"Parties can have at most {MAX_PARTY_SIZE} players.")
    cur = await db.execute(
        "SELECT invite_id FROM party_invites WHERE target_id=? AND status='pending'",
        (target_id,),
    )
    if await cur.fetchone():
        raise PartyError("That player already has a pending party invitation.")
    try:
        cur = await db.execute(
            "INSERT INTO party_invites(party_id,inviter_id,target_id) VALUES(?,?,?)",
            (party_id, inviter_id, target_id),
        )
        await db.commit()
    except aiosqlite.IntegrityError as exc:
        await db.rollback()
        raise PartyError("That player already has a pending party invitation.") from exc
    return int(cur.lastrowid)


async def respond_to_party_invite(
    db: aiosqlite.Connection, invite_id: int, target_id: int, accept: bool
) -> None:
    if not _valid_id(invite_id) or not _valid_id(target_id):
        raise PartyError("Invalid party invitation.")
    cur = await db.execute(
        "SELECT party_id,target_id,status FROM party_invites WHERE invite_id=?",
        (invite_id,),
    )
    invite = await cur.fetchone()
    if not invite or invite["status"] != "pending":
        raise PartyError("That party invitation is no longer active.")
    if invite["target_id"] != target_id:
        raise PartyError("Only the invited player can respond.")
    if accept:
        cur = await db.execute("SELECT 1 FROM party_members WHERE user_id=?", (target_id,))
        if await cur.fetchone():
            raise PartyError("You are already in a party.")
        cur = await db.execute("SELECT COUNT(*) AS total FROM party_members WHERE party_id=?", (invite["party_id"],))
        if (await cur.fetchone())["total"] >= MAX_PARTY_SIZE:
            await db.execute(
                "UPDATE party_invites SET status='cancelled',responded_at=CURRENT_TIMESTAMP WHERE invite_id=?",
                (invite_id,),
            )
            await db.commit()
            raise PartyError("That party is already full.")
        await db.execute(
            "INSERT INTO party_members(user_id,party_id) VALUES(?,?)",
            (target_id, invite["party_id"]),
        )
        status = "accepted"
    else:
        status = "declined"
    await db.execute(
        "UPDATE party_invites SET status=?,responded_at=CURRENT_TIMESTAMP WHERE invite_id=? AND status='pending'",
        (status, invite_id),
    )
    await db.commit()


async def leave_party(db: aiosqlite.Connection, user_id: int) -> int | None:
    if not _valid_id(user_id):
        raise PartyError("Invalid player account.")
    cur = await db.execute("SELECT party_id FROM party_members WHERE user_id=?", (user_id,))
    membership = await cur.fetchone()
    if not membership:
        raise PartyError("You are not in a party.")
    party_id = membership["party_id"]
    cur = await db.execute("SELECT leader_id FROM parties WHERE party_id=?", (party_id,))
    party = await cur.fetchone()
    await db.execute("DELETE FROM party_members WHERE user_id=?", (user_id,))
    new_leader = None
    if party and party["leader_id"] == user_id:
        cur = await db.execute(
            "SELECT user_id FROM party_members WHERE party_id=? ORDER BY joined_at,user_id LIMIT 1",
            (party_id,),
        )
        successor = await cur.fetchone()
        if successor:
            new_leader = successor["user_id"]
            await db.execute("UPDATE parties SET leader_id=? WHERE party_id=?", (new_leader, party_id))
        else:
            await db.execute("UPDATE party_invites SET status='cancelled',responded_at=CURRENT_TIMESTAMP WHERE party_id=? AND status='pending'", (party_id,))
            await db.execute("DELETE FROM parties WHERE party_id=?", (party_id,))
    await db.commit()
    return new_leader


async def disband_party(db: aiosqlite.Connection, party_id: int, user_id: int) -> None:
    if not _valid_id(party_id) or not _valid_id(user_id):
        raise PartyError("Invalid party or player account.")
    cur = await db.execute("SELECT leader_id FROM parties WHERE party_id=?", (party_id,))
    party = await cur.fetchone()
    if not party:
        raise PartyError("Party not found.")
    if party["leader_id"] != user_id:
        raise PartyError("Only the party leader can disband it.")
    await db.execute("UPDATE party_invites SET status='cancelled',responded_at=CURRENT_TIMESTAMP WHERE party_id=? AND status='pending'", (party_id,))
    await db.execute("DELETE FROM party_members WHERE party_id=?", (party_id,))
    await db.execute("DELETE FROM parties WHERE party_id=?", (party_id,))
    await db.commit()


async def get_party_info(db: aiosqlite.Connection, user_id: int):
    if not _valid_id(user_id):
        raise PartyError("Invalid player account.")
    cur = await db.execute(
        """
        SELECT p.party_id,p.leader_id,COUNT(m.user_id) AS member_count
        FROM party_members mine
        JOIN parties p ON p.party_id=mine.party_id
        JOIN party_members m ON m.party_id=p.party_id
        WHERE mine.user_id=?
        GROUP BY p.party_id
        """,
        (user_id,),
    )
    party = await cur.fetchone()
    if not party:
        raise PartyError("You are not in a party.")
    cur = await db.execute(
        "SELECT p.user_id,p.username,p.level,pm.joined_at FROM party_members pm "
        "JOIN players p ON p.user_id=pm.user_id WHERE pm.party_id=? ORDER BY pm.joined_at,p.user_id",
        (party["party_id"],),
    )
    return party, await cur.fetchall()
