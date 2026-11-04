import time
import unittest

import aiosqlite

from matchmaking_battle_system import MatchmakingBattleError, get_matchmaking_battle, perform_matchmaking_battle_action
from mana_system import init_mana_tables
from matchmaking_system import (
    MatchmakingError,
    cancel_matchmaking,
    complete_matchmaking_match,
    expire_matchmaking_queue,
    get_matchmaking_status,
    init_matchmaking_tables,
    join_matchmaking,
)


class MatchmakingSystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute(
            """CREATE TABLE players(
                 user_id INTEGER PRIMARY KEY,
                 username TEXT,
                 level INTEGER NOT NULL DEFAULT 1,
                 pvp_wins INTEGER NOT NULL DEFAULT 0,
                 pvp_losses INTEGER NOT NULL DEFAULT 0,
                 max_hp INTEGER NOT NULL DEFAULT 100,
                 hero_class TEXT NOT NULL DEFAULT 'Knight',
                 weapon_attack INTEGER NOT NULL DEFAULT 0,
                 armor_defense INTEGER NOT NULL DEFAULT 0,
                 skill_cd INTEGER NOT NULL DEFAULT 0
               )"""
        )
        await self.db.execute("CREATE TABLE battles(user_id INTEGER PRIMARY KEY)")
        await self.db.execute("CREATE TABLE dungeon_runs(user_id INTEGER PRIMARY KEY,status TEXT)")
        await self.db.execute("CREATE TABLE party_members(party_id INTEGER,user_id INTEGER)")
        await self.db.execute("CREATE TABLE party_battles(battle_id INTEGER PRIMARY KEY,party_id INTEGER,status TEXT)")
        await self.db.execute(
            "CREATE TABLE duels(duel_id INTEGER PRIMARY KEY,challenger_id INTEGER,opponent_id INTEGER,status TEXT)"
        )
        await self.db.execute(
            "CREATE TABLE trades(trade_id INTEGER PRIMARY KEY,initiator_id INTEGER,partner_id INTEGER,status TEXT)"
        )
        await self.db.executemany(
            "INSERT INTO players(user_id,level,pvp_wins,pvp_losses) VALUES(?,?,?,?)",
            (
                (1, 10, 0, 0),
                (2, 10, 0, 0),
                (3, 10, 0, 0),
                (4, 10, 10, 0),
            ),
        )
        await init_matchmaking_tables(self.db)
        await init_mana_tables(self.db)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()

    async def test_cannot_join_matchmaking_during_other_active_game_modes(self):
        await self.db.execute("INSERT INTO battles(user_id) VALUES(1)")
        await self.db.commit()
        with self.assertRaisesRegex(MatchmakingError, "active PvE battle"):
            await join_matchmaking(self.db, 1, "casual", now=1000)

        await self.db.execute("DELETE FROM battles WHERE user_id=1")
        await self.db.execute(
            "INSERT INTO duels(duel_id,challenger_id,opponent_id,status) VALUES(1,1,2,'pending')"
        )
        await self.db.commit()
        with self.assertRaisesRegex(MatchmakingError, "active duel"):
            await join_matchmaking(self.db, 1, "casual", now=1001)

        await self.db.execute("DELETE FROM duels WHERE duel_id=1")
        await self.db.execute(
            "INSERT INTO trades(trade_id,initiator_id,partner_id,status) VALUES(1,1,2,'open')"
        )
        await self.db.commit()
        with self.assertRaisesRegex(MatchmakingError, "active trade"):
            await join_matchmaking(self.db, 1, "casual", now=1002)

        await self.db.execute("DELETE FROM trades WHERE trade_id=1")
        await self.db.execute("INSERT INTO dungeon_runs(user_id,status) VALUES(1,'active')")
        await self.db.commit()
        with self.assertRaisesRegex(MatchmakingError, "active dungeon"):
            await join_matchmaking(self.db, 1, "casual", now=1003)

        await self.db.execute("DELETE FROM dungeon_runs WHERE user_id=1")
        await self.db.execute("INSERT INTO party_members(party_id,user_id) VALUES(10,1)")
        await self.db.execute("INSERT INTO party_battles(battle_id,party_id,status) VALUES(1,10,'active')")
        await self.db.commit()
        with self.assertRaisesRegex(MatchmakingError, "party's active co-op battle"):
            await join_matchmaking(self.db, 1, "casual", now=1004)

    async def test_two_similar_players_match_and_can_complete_match(self):
        first = await join_matchmaking(self.db, 1, "casual", now=1000)
        self.assertEqual(first["status"], "queued")

        second = await join_matchmaking(self.db, 2, "casual", now=1001)
        self.assertEqual(second["status"], "matched")
        self.assertEqual(second["opponent_id"], 1)
        self.assertIsNotNone(second["match_id"])

        first_status = await get_matchmaking_status(self.db, 1, now=1001)
        self.assertEqual(first_status["status"], "matched")
        self.assertEqual(first_status["match_id"], second["match_id"])
        self.assertEqual(first_status["opponent_id"], 2)

        completed = await complete_matchmaking_match(
            self.db,
            second["match_id"],
            winner_id=2,
            now=1010,
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["winner_id"], 2)
        self.assertEqual((await get_matchmaking_status(self.db, 1, now=1010))["status"], "completed")
        closed_battle = await get_matchmaking_battle(self.db, 1, second["match_id"], now=1010)
        self.assertEqual(closed_battle["status"], "finished")
        self.assertEqual(closed_battle["winner_id"], 2)

    async def test_matchmaking_match_creates_live_battle_and_turns_are_server_authoritative(self):
        await join_matchmaking(self.db, 1, "casual", now=1000)
        matched = await join_matchmaking(self.db, 2, "casual", now=1001)
        match_id = matched["match_id"]
        battle = await get_matchmaking_battle(self.db, 1, match_id, now=1001)
        self.assertEqual(battle["status"], "active")
        self.assertTrue(battle["is_my_turn"])
        self.assertEqual(battle["my_hp"], 100)
        self.assertEqual(battle["opponent_hp"], 100)

        classes = {
            "Knight": {"attack": 8, "defense": 12},
            "Mage": {"attack": 18, "defense": 0},
            "Archer": {"attack": 12, "defense": 4},
            "Berserker": {"attack": 22, "defense": -3},
        }
        with self.assertRaisesRegex(MatchmakingBattleError, "Wait for your opponent"):
            await perform_matchmaking_battle_action(self.db, 2, match_id, "attack", classes, now=1002)

        turn = await perform_matchmaking_battle_action(
            self.db, 1, match_id, "attack", classes,
            rng=type("FixedRandom", (), {"randint": staticmethod(lambda low, high: 0)})(),
            now=1002,
        )
        self.assertEqual(turn["status"], "active")
        self.assertEqual(turn["turn_user_id"], 2)
        self.assertEqual(turn["turn_count"], 1)
        self.assertLess(turn["opponent_hp"], 100)

    async def test_pvp_damage_uses_combat_stats_snapshotted_at_match_start(self):
        await self.db.execute("UPDATE players SET hero_class='Mage' WHERE user_id=1")
        await join_matchmaking(self.db, 1, "casual", now=1000)
        matched = await join_matchmaking(self.db, 2, "casual", now=1001)
        match_id = matched["match_id"]

        await self.db.execute("UPDATE players SET weapon_attack=500 WHERE user_id=1")
        await self.db.execute("UPDATE players SET armor_defense=200 WHERE user_id=2")
        await self.db.commit()

        classes = {
            "Knight": {"attack": 8, "defense": 12},
            "Mage": {"attack": 18, "defense": 0},
            "Archer": {"attack": 12, "defense": 4},
            "Berserker": {"attack": 22, "defense": -3},
        }
        result = await perform_matchmaking_battle_action(
            self.db, 1, match_id, "attack", classes,
            rng=type("FixedRandom", (), {"randint": staticmethod(lambda low, high: 0)})(),
            now=1002,
        )
        self.assertEqual(result["damage"], 86)

    async def test_pvp_skill_consumes_mana_and_obeys_class_cooldown(self):
        await self.db.execute("UPDATE players SET max_hp=1000 WHERE user_id IN (1,2)")
        await self.db.commit()
        await join_matchmaking(self.db, 1, "casual", now=1000)
        matched = await join_matchmaking(self.db, 2, "casual", now=1001)
        match_id = matched["match_id"]
        classes = {"Knight": {"attack": 8, "defense": 12}}
        result = await perform_matchmaking_battle_action(
            self.db, 1, match_id, "skill", classes,
            rng=type("FixedRandom", (), {"randint": staticmethod(lambda low, high: 0)})(),
            now=1002,
        )
        self.assertGreater(result["damage"], 0)
        cursor = await self.db.execute("SELECT mana FROM player_mana WHERE user_id=1")
        self.assertEqual((await cursor.fetchone())["mana"], 75)
        cursor = await self.db.execute("SELECT skill_cd FROM players WHERE user_id=1")
        self.assertEqual((await cursor.fetchone())["skill_cd"], 3)

        await perform_matchmaking_battle_action(self.db, 2, match_id, "attack", classes, now=1003)
        with self.assertRaisesRegex(MatchmakingBattleError, "Skill cooling down"):
            await perform_matchmaking_battle_action(self.db, 1, match_id, "skill", classes, now=1004)
        cursor = await self.db.execute("SELECT mana FROM player_mana WHERE user_id=1")
        self.assertEqual((await cursor.fetchone())["mana"], 75)

    async def test_pvp_skill_without_mana_does_not_consume_a_turn(self):
        await join_matchmaking(self.db, 1, "casual", now=1000)
        matched = await join_matchmaking(self.db, 2, "casual", now=1001)
        match_id = matched["match_id"]
        await self.db.execute(
            "INSERT INTO player_mana(user_id,mana,updated_at) VALUES(1,10,?)",
            (int(time.time()),)
        )
        await self.db.commit()
        with self.assertRaisesRegex(MatchmakingBattleError, "Not enough mana"):
            await perform_matchmaking_battle_action(
                self.db, 1, match_id, "skill",
                {"Knight": {"attack": 8, "defense": 12}}, now=1002,
            )
        battle = await get_matchmaking_battle(self.db, 1, match_id, now=1002)
        self.assertTrue(battle["is_my_turn"])
        self.assertEqual(battle["opponent_hp"], 100)
        cursor = await self.db.execute("SELECT mana FROM player_mana WHERE user_id=1")
        self.assertEqual((await cursor.fetchone())["mana"], 10)

    async def test_inactive_turn_expires_and_awards_win_to_waiting_player(self):
        await join_matchmaking(self.db, 1, "casual", now=1000)
        matched = await join_matchmaking(self.db, 2, "casual", now=1001)
        match_id = matched["match_id"]
        before_deadline = await get_matchmaking_battle(self.db, 1, match_id, now=1120)
        self.assertEqual(before_deadline["status"], "active")
        self.assertEqual(before_deadline["turn_time_remaining"], 1)

        expired = await get_matchmaking_battle(self.db, 1, match_id, now=1121)
        self.assertEqual(expired["status"], "finished")
        self.assertEqual(expired["winner_id"], 2)
        self.assertFalse(expired["is_winner"])
        cursor = await self.db.execute(
            "SELECT pvp_wins,pvp_losses FROM players WHERE user_id=2"
        )
        self.assertEqual(tuple(await cursor.fetchone()), (1, 0))

    async def test_action_after_turn_deadline_forfeits_without_applying_damage(self):
        await join_matchmaking(self.db, 1, "casual", now=1000)
        matched = await join_matchmaking(self.db, 2, "casual", now=1001)
        result = await perform_matchmaking_battle_action(
            self.db, 1, matched["match_id"], "attack",
            {"Knight": {"attack": 8, "defense": 12}}, now=1121,
        )
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["last_action"], "timeout")
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["winner_id"], 2)
        self.assertEqual(result["damage"], 0)

    async def test_matchmaking_pvp_surrender_settles_stats_once(self):
        await join_matchmaking(self.db, 1, "casual", now=1000)
        matched = await join_matchmaking(self.db, 2, "casual", now=1001)
        match_id = matched["match_id"]
        classes = {"Knight": {"attack": 8, "defense": 12}}
        result = await perform_matchmaking_battle_action(self.db, 1, match_id, "surrender", classes, now=1002)
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["winner_id"], 2)
        self.assertEqual(result["turn_count"], 1)
        cursor = await self.db.execute(
            "SELECT user_id,pvp_wins,pvp_losses FROM players WHERE user_id IN (1,2) ORDER BY user_id"
        )
        rows = await cursor.fetchall()
        self.assertEqual([(row["pvp_wins"], row["pvp_losses"]) for row in rows], [(0, 1), (1, 0)])
        cursor = await self.db.execute(
            "SELECT status FROM matchmaking_queue WHERE user_id IN (1,2) ORDER BY user_id"
        )
        self.assertEqual([row["status"] for row in await cursor.fetchall()], ["completed", "completed"])

    async def test_join_is_idempotent_and_cancelled_users_are_rate_limited(self):
        first = await join_matchmaking(self.db, 1, now=1000)
        again = await join_matchmaking(self.db, 1, now=1001)
        self.assertEqual(again["status"], "queued")
        self.assertEqual(first["queued_at"], again["queued_at"])

        self.assertTrue(await cancel_matchmaking(self.db, 1, now=1002))
        self.assertFalse(await cancel_matchmaking(self.db, 1, now=1003))
        self.assertEqual((await get_matchmaking_status(self.db, 1, now=1003))["status"], "cancelled")

        with self.assertRaisesRegex(MatchmakingError, "Wait 6 seconds"):
            await join_matchmaking(self.db, 1, now=1004)
        rejoined = await join_matchmaking(self.db, 1, now=1010)
        self.assertEqual(rejoined["status"], "queued")

    async def test_rating_window_expands_for_waiting_players(self):
        waiting = await join_matchmaking(self.db, 4, "ranked", now=1000)
        self.assertEqual(waiting["status"], "queued")
        matched = await join_matchmaking(self.db, 1, "ranked", now=1015)
        self.assertEqual(matched["status"], "matched")
        self.assertEqual(matched["opponent_id"], 4)
        self.assertEqual(matched["rating_gap"], 200)

    async def test_expired_queue_entry_cannot_be_matched(self):
        await join_matchmaking(self.db, 1, now=1000)
        self.assertEqual(
            (await get_matchmaking_status(self.db, 1, now=1180))["status"],
            "expired",
        )

        other = await join_matchmaking(self.db, 2, now=1181)
        self.assertEqual(other["status"], "queued")

    async def test_invalid_mode_and_unknown_player_are_rejected(self):
        with self.assertRaises(MatchmakingError):
            await join_matchmaking(self.db, 1, "tournament", now=1000)
        with self.assertRaises(MatchmakingError):
            await join_matchmaking(self.db, 999, "casual", now=1000)

    async def test_queue_join_preserves_outer_transaction(self):
        await self.db.execute("BEGIN")
        result = await join_matchmaking(self.db, 1, now=1000)
        self.assertEqual(result["status"], "queued")
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertIsNone(await get_matchmaking_status(self.db, 1, now=1001))


if __name__ == "__main__":
    unittest.main()
