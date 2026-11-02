"""Server-authoritative turn-based combat for matchmaking matches."""
from __future__ import annotations

import random
import time
from typing import Any


class MatchmakingBattleError(ValueError):
    """A PvP action is not valid for the current match state."""


def _is_postgres(db: Any) -> bool:
    return getattr(db, "dialect", "sqlite") == "postgres"


def _valid_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


async def _begin(db: Any, name: str) -> bool:
    nested = db.in_transaction
    if nested:
        await db.execute(f"SAVEPOINT {name}")
    else:
        await db.execute("BEGIN" if _is_postgres(db) else "BEGIN IMMEDIATE")
    return nested


async def _commit(db: Any, nested: bool, name: str) -> None:
    if nested:
        await db.execute(f"RELEASE SAVEPOINT {name}")
    else:
        await db.commit()


async def _rollback(db: Any, nested: bool, name: str) -> None:
    if nested:
        await db.execute(f"ROLLBACK TO SAVEPOINT {name}")
        await db.execute(f"RELEASE SAVEPOINT {name}")
    else:
        await db.rollback()


async def _battle_row(db: Any, match_id: int, lock: bool = False):
    query = (
        """SELECT b.*,m.player_one_id,m.player_two_id,m.mode,m.status AS match_status,
                  p1.username AS player_one_name,p1.level AS player_one_level,
                  p2.username AS player_two_name,p2.level AS player_two_level
           FROM matchmaking_battles b
           JOIN matchmaking_matches m ON m.match_id=b.match_id
           JOIN players p1 ON p1.user_id=m.player_one_id
           JOIN players p2 ON p2.user_id=m.player_two_id
           WHERE b.match_id=?"""
    )
    if lock and _is_postgres(db):
        query += " FOR UPDATE OF b,m"
    cursor = await db.execute(query, (match_id,))
    return await cursor.fetchone()


async def get_matchmaking_battle(db: Any, user_id: int, match_id: int | None = None) -> dict | None:
    """Return only participant-safe battle state for the requesting player."""
    if not _valid_id(user_id):
        raise MatchmakingBattleError("Invalid player account.")
    if match_id is None:
        cursor = await db.execute(
            """SELECT match_id FROM matchmaking_queue
               WHERE user_id=? AND match_id IS NOT NULL
               ORDER BY updated_at DESC LIMIT 1""",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        match_id = row["match_id"]
    if not _valid_id(match_id):
        raise MatchmakingBattleError("Invalid matchmaking match.")
    row = await _battle_row(db, match_id)
    if not row or user_id not in {row["player_one_id"], row["player_two_id"]}:
        return None
    first = row["player_one_id"] == user_id
    opponent_id = row["player_two_id"] if first else row["player_one_id"]
    opponent_name = row["player_two_name"] if first else row["player_one_name"]
    opponent_level = row["player_two_level"] if first else row["player_one_level"]
    own_hp = row["player_one_hp"] if first else row["player_two_hp"]
    own_max_hp = row["player_one_max_hp"] if first else row["player_two_max_hp"]
    opponent_hp = row["player_two_hp"] if first else row["player_one_hp"]
    opponent_max_hp = row["player_two_max_hp"] if first else row["player_one_max_hp"]
    return {
        "match_id": row["match_id"],
        "mode": row["mode"],
        "status": row["status"],
        "opponent_id": opponent_id,
        "opponent_name": opponent_name or "Adventurer",
        "opponent_level": opponent_level,
        "my_hp": own_hp,
        "my_max_hp": own_max_hp,
        "opponent_hp": opponent_hp,
        "opponent_max_hp": opponent_max_hp,
        "turn_user_id": row["turn_user_id"],
        "is_my_turn": row["status"] == "active" and row["turn_user_id"] == user_id,
        "turn_count": row["turn_count"],
        "winner_id": row["winner_id"],
        "is_winner": row["winner_id"] == user_id,
    }


async def perform_matchmaking_battle_action(
    db: Any,
    user_id: int,
    match_id: int,
    action: str,
    hero_classes: dict,
    *,
    rng=None,
) -> dict:
    """Apply one validated player turn and settle match/rating counters atomically."""
    if not _valid_id(user_id) or not _valid_id(match_id):
        raise MatchmakingBattleError("Invalid player or match.")
    if action not in {"attack", "skill", "surrender"}:
        raise MatchmakingBattleError("Choose attack, skill, or surrender.")
    random_source = rng or random
    savepoint = "matchmaking_battle_action"
    nested = await _begin(db, savepoint)
    try:
        row = await _battle_row(db, match_id, lock=True)
        if not row or user_id not in {row["player_one_id"], row["player_two_id"]}:
            raise MatchmakingBattleError("You are not part of this match.")
        if row["status"] != "active" or row["match_status"] != "matched":
            raise MatchmakingBattleError("This PvP battle is already closed.")
        if row["turn_user_id"] != user_id:
            raise MatchmakingBattleError("Wait for your opponent's turn.")

        first = row["player_one_id"] == user_id
        opponent_column = "player_two_hp" if first else "player_one_hp"
        opponent_id = row["player_two_id"] if first else row["player_one_id"]
        winner_id = None
        damage = 0

        if action == "surrender":
            winner_id = opponent_id
        else:
            attacker_cursor = await db.execute(
                "SELECT level,hero_class,weapon_attack FROM players WHERE user_id=?",
                (user_id,),
            )
            attacker = await attacker_cursor.fetchone()
            defender_cursor = await db.execute(
                "SELECT hero_class,armor_defense FROM players WHERE user_id=?",
                (opponent_id,),
            )
            defender = await defender_cursor.fetchone()
            if not attacker or not defender:
                raise MatchmakingBattleError("A player account is no longer available.")
            attacker_class = hero_classes.get(attacker["hero_class"], hero_classes["Knight"])
            defender_class = hero_classes.get(defender["hero_class"], hero_classes["Knight"])
            base = int(attacker["level"]) * 8 + attacker_class["attack"] + int(attacker["weapon_attack"] or 0)
            if action == "skill":
                base = int(base * 1.8)
            damage = max(
                5,
                base + random_source.randint(0, 12)
                - int(defender["armor_defense"] or 0) - defender_class["defense"],
            )
            new_hp = max(0, int(row[opponent_column]) - damage)
            if new_hp == 0:
                winner_id = user_id
            await db.execute(
                f"UPDATE matchmaking_battles SET {opponent_column}=? WHERE match_id=?",
                (new_hp, match_id),
            )

        if winner_id is not None:
            await db.execute(
                """UPDATE matchmaking_battles SET status='finished',winner_id=?,
                   turn_user_id=NULL,turn_count=turn_count+1 WHERE match_id=?""",
                (winner_id, match_id),
            )
            await db.execute(
                """UPDATE matchmaking_matches SET status='completed',completed_at=?,
                   winner_id=? WHERE match_id=? AND status='matched'""",
                (int(time.time()), winner_id, match_id),
            )
            loser_id = opponent_id if winner_id == user_id else user_id
            await db.execute("UPDATE players SET pvp_wins=pvp_wins+1 WHERE user_id=?", (winner_id,))
            await db.execute("UPDATE players SET pvp_losses=pvp_losses+1 WHERE user_id=?", (loser_id,))
            await db.execute(
                """UPDATE matchmaking_queue SET status='completed',updated_at=?
                   WHERE match_id=? AND status='matched'""",
                (int(time.time()), match_id),
            )
        else:
            await db.execute(
                "UPDATE matchmaking_battles SET turn_user_id=?,turn_count=turn_count+1,updated_at=? WHERE match_id=?",
                (opponent_id, int(time.time()), match_id),
            )
        await _commit(db, nested, savepoint)
    except Exception:
        await _rollback(db, nested, savepoint)
        raise
    state = await get_matchmaking_battle(db, user_id, match_id)
    if state is None:
        raise MatchmakingBattleError("Match state could not be loaded.")
    state["last_action"] = action
    state["damage"] = damage
    return state
