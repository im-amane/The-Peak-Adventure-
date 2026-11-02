"""Persistent, abuse-resistant friend requests for The Peak Adventure."""
from __future__ import annotations

import aiosqlite
from functools import wraps


class FriendError(ValueError):
    """A friend operation cannot be completed."""


MAX_PENDING_FRIEND_REQUESTS = 10


async def _begin_atomic(db, savepoint):
    nested = db.in_transaction
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    else:
        await db.execute("BEGIN IMMEDIATE")
    return nested


async def _commit_atomic(db, nested, savepoint):
    if nested:
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.commit()


async def _rollback_atomic(db, nested, savepoint):
    if nested:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.rollback()


def _transactional(function):
    """Make friend mutations atomic without committing caller-owned work."""
    @wraps(function)
    async def wrapped(db, *args, **kwargs):
        savepoint = "friend_" + function.__name__
        nested = await _begin_atomic(db, savepoint)
        try:
            result = await function(db, *args, **kwargs)
            await _commit_atomic(db, nested, savepoint)
            return result
        except Exception:
            await _rollback_atomic(db, savepoint, nested) if False else await _rollback_atomic(db, nested, savepoint)
            raise
    return wrapped


@_transactional
async def init_friend_tables(db: aiosqlite.Connection) -> None:
    """Create friend storage without committing a caller-owned transaction."""
    statements = (
        """CREATE TABLE IF NOT EXISTS friend_requests (
          request_id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_low INTEGER NOT NULL,
          user_high INTEGER NOT NULL,
          requester_id INTEGER NOT NULL,
          target_id INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending', 'accepted', 'declined', 'removed')),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          responded_at TEXT,
          CHECK(user_low < user_high),
          CHECK(requester_id != target_id),
          UNIQUE(request_id)
        )""",
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_friend_active_pair
          ON friend_requests(user_low, user_high)
          WHERE status IN ('pending', 'accepted')""",
        """CREATE INDEX IF NOT EXISTS idx_friend_target_pending
          ON friend_requests(target_id, status, request_id)""",
        """CREATE INDEX IF NOT EXISTS idx_friend_requester_status
          ON friend_requests(requester_id, status)""",
    )
    for statement in statements:
        await db.execute(statement)


def _valid_user_id(user_id: int) -> bool:
    return isinstance(user_id, int) and not isinstance(user_id, bool) and user_id > 0


@_transactional
async def send_friend_request(db: aiosqlite.Connection, requester_id: int, target_id: int) -> int:
    if not _valid_user_id(requester_id) or not _valid_user_id(target_id):
        raise FriendError("Invalid player account.")
    if requester_id == target_id:
        raise FriendError("You cannot send a friend request to yourself.")
    low, high = sorted((requester_id, target_id))
    cur = await db.execute(
        "SELECT requester_id, status FROM friend_requests "
        "WHERE user_low=? AND user_high=? AND status IN ('pending','accepted')",
        (low, high),
    )
    existing = await cur.fetchone()
    if existing:
        if existing["status"] == "accepted":
            raise FriendError("You are already friends.")
        if existing["requester_id"] == requester_id:
            raise FriendError("Your friend request is already pending.")
        raise FriendError("This player has already sent you a request. Accept it instead.")
    cur = await db.execute(
        "SELECT COUNT(*) AS total FROM friend_requests WHERE requester_id=? AND status='pending'",
        (requester_id,),
    )
    if (await cur.fetchone())["total"] >= MAX_PENDING_FRIEND_REQUESTS:
        raise FriendError(f"You can have at most {MAX_PENDING_FRIEND_REQUESTS} outgoing friend requests pending.")
    try:
        cur = await db.execute(
            "INSERT INTO friend_requests(user_low,user_high,requester_id,target_id) VALUES(?,?,?,?)",
            (low, high, requester_id, target_id),
        )
    except aiosqlite.IntegrityError as exc:
        raise FriendError("A friend request for this player is already active.") from exc
    return int(cur.lastrowid)


@_transactional
async def respond_to_friend_request(
    db: aiosqlite.Connection, request_id: int, target_id: int, accept: bool
) -> None:
    if not _valid_user_id(request_id) or not _valid_user_id(target_id) or type(accept) is not bool:
        raise FriendError("Invalid friend request.")
    cur = await db.execute(
        "SELECT target_id,status FROM friend_requests WHERE request_id=?",
        (request_id,),
    )
    request = await cur.fetchone()
    if not request or request["status"] != "pending":
        raise FriendError("That friend request is no longer active.")
    if request["target_id"] != target_id:
        raise FriendError("Only the invited player can respond to this request.")
    status = "accepted" if accept else "declined"
    cur = await db.execute(
        "UPDATE friend_requests SET status=?,responded_at=CURRENT_TIMESTAMP "
        "WHERE request_id=? AND status='pending' AND target_id=?",
        (status, request_id, target_id),
    )
    if cur.rowcount != 1:
        raise FriendError("That friend request was already handled.")


async def list_friends(db: aiosqlite.Connection, user_id: int):
    if not _valid_user_id(user_id):
        raise FriendError("Invalid player account.")
    cur = await db.execute(
        """
        SELECT p.user_id,p.username,p.level
        FROM friend_requests f
        JOIN players p ON p.user_id = CASE
          WHEN f.user_low=? THEN f.user_high ELSE f.user_low END
        WHERE ? IN (f.user_low,f.user_high) AND f.status='accepted'
        ORDER BY p.level DESC, p.username COLLATE NOCASE
        """,
        (user_id, user_id),
    )
    return await cur.fetchall()


@_transactional
async def remove_friend(db: aiosqlite.Connection, user_id: int, friend_id: int) -> None:
    if not _valid_user_id(user_id) or not _valid_user_id(friend_id) or user_id == friend_id:
        raise FriendError("Invalid friend account.")
    low, high = sorted((user_id, friend_id))
    cur = await db.execute(
        "UPDATE friend_requests SET status='removed',responded_at=CURRENT_TIMESTAMP "
        "WHERE user_low=? AND user_high=? AND status='accepted'",
        (low, high),
    )
    if cur.rowcount == 0:
        raise FriendError("That player is not on your friend list.")
 


async def search_players(db: aiosqlite.Connection, searcher_id: int, query: str, limit: int = 10):
    """Search public profiles and friends-only profiles visible to accepted friends."""
    if not _valid_user_id(searcher_id):
        raise FriendError("Invalid player account.")
    clean = " ".join(str(query or "").strip().lstrip("@").split())
    if not 2 <= len(clean) <= 32:
        raise FriendError("Player search must be between 2 and 32 characters.")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise FriendError("Invalid player search limit.")
    escaped = clean.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    cur = await db.execute(
        """SELECT p.user_id,p.username,p.level
           FROM players p
           LEFT JOIN player_settings settings ON settings.user_id=p.user_id
           WHERE p.user_id!=?
             AND p.username IS NOT NULL
             AND p.username LIKE ? ESCAPE '\\'
             AND (
               COALESCE(settings.profile_visibility,'public')='public'
               OR (
                 settings.profile_visibility='friends'
                 AND EXISTS (
                   SELECT 1 FROM friend_requests f
                   WHERE f.status='accepted'
                     AND f.user_low=MIN(?,p.user_id)
                     AND f.user_high=MAX(?,p.user_id)
                 )
               )
             )
           ORDER BY p.level DESC,p.username COLLATE NOCASE
           LIMIT ?""",
        (searcher_id, f"%{escaped}%", searcher_id, searcher_id, limit),
    )
    return await cur.fetchall()


async def list_pending_friend_requests(db: aiosqlite.Connection, user_id: int):
    if not _valid_user_id(user_id):
        raise FriendError("Invalid player account.")
    cur = await db.execute(
        """SELECT f.request_id,f.requester_id,p.username,p.level,f.created_at
           FROM friend_requests f
           JOIN players p ON p.user_id=f.requester_id
           WHERE f.target_id=? AND f.status='pending'
           ORDER BY f.request_id DESC LIMIT 20""",
        (user_id,),
    )
    return await cur.fetchall()
