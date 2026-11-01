"""Persistent, abuse-resistant friend requests for The Peak Adventure."""
from __future__ import annotations

import aiosqlite


class FriendError(ValueError):
    """A friend operation cannot be completed."""


MAX_PENDING_FRIEND_REQUESTS = 10


async def init_friend_tables(db: aiosqlite.Connection) -> None:
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS friend_requests (
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
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_friend_active_pair
      ON friend_requests(user_low, user_high)
      WHERE status IN ('pending', 'accepted');
    CREATE INDEX IF NOT EXISTS idx_friend_target_pending
      ON friend_requests(target_id, status, request_id);
    CREATE INDEX IF NOT EXISTS idx_friend_requester_status
      ON friend_requests(requester_id, status);
    """)
    await db.commit()


def _valid_user_id(user_id: int) -> bool:
    return isinstance(user_id, int) and not isinstance(user_id, bool) and user_id > 0


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
        await db.commit()
    except aiosqlite.IntegrityError as exc:
        await db.rollback()
        raise FriendError("A friend request for this player is already active.") from exc
    return int(cur.lastrowid)


async def respond_to_friend_request(
    db: aiosqlite.Connection, request_id: int, target_id: int, accept: bool
) -> None:
    if not _valid_user_id(request_id) or not _valid_user_id(target_id):
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
    await db.execute(
        "UPDATE friend_requests SET status=?,responded_at=CURRENT_TIMESTAMP "
        "WHERE request_id=? AND status='pending' AND target_id=?",
        (status, request_id, target_id),
    )
    await db.commit()


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
    await db.commit()
