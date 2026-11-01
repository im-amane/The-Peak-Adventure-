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

    await db.executescript("""
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
    """)
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



async def start_party_battle(db, party_id, user_id, monster_level, monster_name, monster_hp):
    if not _valid_id(party_id) or not _valid_id(user_id):
        raise PartyError("Invalid party or player account.")
    if not isinstance(monster_level, int) or isinstance(monster_level, bool) or not 1 <= monster_level <= 100:
        raise PartyError("Invalid co-op monster level.")
    if not isinstance(monster_hp, int) or isinstance(monster_hp, bool) or not 1 <= monster_hp <= 10_000_000:
        raise PartyError("Invalid co-op monster health.")
    clean_name = " ".join(str(monster_name or "").split())[:80]
    if not clean_name:
        raise PartyError("A monster name is required.")
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute("SELECT leader_id FROM parties WHERE party_id=?", (party_id,))
        party = await cur.fetchone()
        if not party or party["leader_id"] != user_id:
            raise PartyError("Only the party leader can start a co-op battle.")
        cur = await db.execute("SELECT 1 FROM party_battles WHERE party_id=? AND status='active'", (party_id,))
        if await cur.fetchone():
            raise PartyError("Your party already has an active co-op battle.")
        cur = await db.execute(
            "INSERT INTO party_battles(party_id,monster_level,monster_name,max_hp,hp) VALUES(?,?,?,?,?)",
            (party_id, monster_level, clean_name, monster_hp, monster_hp),
        )
        battle_id = int(cur.lastrowid)
        await db.commit()
        return battle_id
    except Exception:
        await db.rollback()
        raise

async def attack_party_battle(db, party_id, user_id, damage):
    if not _valid_id(party_id) or not _valid_id(user_id):
        raise PartyError("Invalid party or player account.")
    if not isinstance(damage, int) or isinstance(damage, bool) or not 1 <= damage <= 10000:
        raise PartyError("Invalid co-op attack damage.")
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT 1 FROM party_members WHERE party_id=? AND user_id=?",
            (party_id, user_id),
        )
        if not await cur.fetchone():
            raise PartyError("Only party members can attack this monster.")
        cur = await db.execute(
            "SELECT * FROM party_battles WHERE party_id=? AND status='active' ORDER BY battle_id DESC LIMIT 1",
            (party_id,),
        )
        battle = await cur.fetchone()
        if not battle:
            raise PartyError("There is no active co-op battle.")
        cur = await db.execute(
            """SELECT 1 FROM party_battle_cooldowns
               WHERE battle_id=? AND user_id=?
               AND julianday(CURRENT_TIMESTAMP)-julianday(last_attack_at)<(5.0/86400)""",
            (battle["battle_id"], user_id),
        )
        if await cur.fetchone():
            raise PartyError("Co-op attack cooldown: wait 5 seconds.")
        hp = max(0, battle["hp"] - damage)
        dealt = battle["hp"] - hp
        status = "won" if hp == 0 else "active"
        await db.execute(
            "UPDATE party_battles SET hp=?,status=? WHERE battle_id=? AND status='active'",
            (hp, status, battle["battle_id"]),
        )
        await db.execute(
            """INSERT INTO party_battle_cooldowns(battle_id,user_id,last_attack_at)
               VALUES(?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(battle_id,user_id) DO UPDATE SET last_attack_at=CURRENT_TIMESTAMP""",
            (battle["battle_id"], user_id),
        )
        await db.execute(
            """INSERT INTO party_battle_contributions(battle_id,user_id,damage) VALUES(?,?,?)
               ON CONFLICT(battle_id,user_id) DO UPDATE SET damage=damage+excluded.damage""",
            (battle["battle_id"], user_id, dealt),
        )
        cur = await db.execute(
            "SELECT user_id FROM party_members WHERE party_id=? ORDER BY joined_at",
            (party_id,),
        )
        members = [row["user_id"] for row in await cur.fetchall()]
        await db.commit()
        return {
            "battle_id": battle["battle_id"], "monster_name": battle["monster_name"],
            "hp": hp, "max_hp": battle["max_hp"], "damage": dealt,
            "status": status, "members": members,
        }
    except Exception:
        await db.rollback()
        raise

async def get_party_battle(db,party_id):
    cur=await db.execute("SELECT * FROM party_battles WHERE party_id=? ORDER BY battle_id DESC LIMIT 1",(party_id,))
    return await cur.fetchone()


async def reward_party_battle(db, battle_id, user_id, coins, xp):
    if not _valid_id(battle_id) or not _valid_id(user_id):
        raise PartyError("Invalid co-op battle or player account.")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in (coins, xp)):
        raise PartyError("Invalid co-op reward.")
    try:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT party_id,status FROM party_battles WHERE battle_id=?",
            (battle_id,),
        )
        battle = await cur.fetchone()
        if not battle or battle["status"] != "won":
            raise PartyError("This co-op battle has not been won.")
        cur = await db.execute(
            "SELECT 1 FROM party_members WHERE party_id=? AND user_id=?",
            (battle["party_id"], user_id),
        )
        if not await cur.fetchone():
            raise PartyError("Only party members can claim co-op rewards.")
        await db.execute(
            "INSERT INTO party_battle_rewards(battle_id,user_id) VALUES(?,?)",
            (battle_id, user_id),
        )
        cur = await db.execute("SELECT level,xp FROM players WHERE user_id=?", (user_id,))
        player = await cur.fetchone()
        if not player:
            raise PartyError("Player account not found.")
        from game_rules import xp_required
        level, xp_total = player["level"], player["xp"] + xp
        while level < 100 and xp_total >= xp_required(level):
            xp_total -= xp_required(level)
            level += 1
        await db.execute(
            "UPDATE players SET coins=coins+?,level=?,xp=? WHERE user_id=?",
            (coins, level, xp_total, user_id),
        )
        await db.commit()
        return {"coins": coins, "xp": xp, "level": level}
    except aiosqlite.IntegrityError as exc:
        await db.rollback()
        raise PartyError("Co-op reward already claimed.") from exc
    except Exception:
        await db.rollback()
        raise

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
    await db.execute("DELETE FROM party_battle_contributions WHERE user_id=?", (user_id,))
    await db.execute("DELETE FROM party_battle_cooldowns WHERE user_id=?", (user_id,))
    await db.execute("DELETE FROM party_battle_rewards WHERE user_id=?", (user_id,))
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
            await db.execute("DELETE FROM party_battle_contributions WHERE battle_id IN (SELECT battle_id FROM party_battles WHERE party_id=?)", (party_id,))
            await db.execute("DELETE FROM party_battle_cooldowns WHERE battle_id IN (SELECT battle_id FROM party_battles WHERE party_id=?)", (party_id,))
            await db.execute("DELETE FROM party_battle_rewards WHERE battle_id IN (SELECT battle_id FROM party_battles WHERE party_id=?)", (party_id,))
            await db.execute("DELETE FROM party_battles WHERE party_id=?", (party_id,))
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
    await db.execute("DELETE FROM party_battle_contributions WHERE battle_id IN (SELECT battle_id FROM party_battles WHERE party_id=?)", (party_id,))
    await db.execute("DELETE FROM party_battle_cooldowns WHERE battle_id IN (SELECT battle_id FROM party_battles WHERE party_id=?)", (party_id,))
    await db.execute("DELETE FROM party_battle_rewards WHERE battle_id IN (SELECT battle_id FROM party_battles WHERE party_id=?)", (party_id,))
    await db.execute("DELETE FROM party_battles WHERE party_id=?", (party_id,))
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


async def list_pending_party_invites(db: aiosqlite.Connection, user_id: int):
    if not _valid_id(user_id):
        raise PartyError("Invalid player account.")
    cur = await db.execute(
        """SELECT i.invite_id,i.party_id,i.inviter_id,p.username,p.level
           FROM party_invites i
           JOIN players p ON p.user_id=i.inviter_id
           WHERE i.target_id=? AND i.status='pending'
           ORDER BY i.invite_id DESC LIMIT 20""",
        (user_id,),
    )
    return await cur.fetchall()
