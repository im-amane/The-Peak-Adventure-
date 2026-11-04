"""PostgreSQL concurrency coverage for matchmaking account-level locking."""
import asyncio
import os
import unittest
import uuid

from postgres_adapter import PostgresConnection
import main
from matchmaking_system import MatchmakingError, join_matchmaking
from matchmaking_battle_system import MatchmakingBattleError, get_matchmaking_battle, perform_matchmaking_battle_action
from party_system import PartyError, create_party, leave_party, start_party_battle


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresMatchmakingConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_one = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        self.db_two = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        self.schema = "peak_matchmaking_" + uuid.uuid4().hex[:12]
        await self.db_one.execute(f'CREATE SCHEMA "{self.schema}"')
        await self.db_one.commit()
        for db in (self.db_one, self.db_two):
            await db.execute(f'SET search_path TO "{self.schema}"')
            await db.commit()
        await main.init_game_schema(self.db_one)
        await self.db_one.executemany(
            "INSERT INTO players(user_id,username) VALUES(?,?)",
            ((9_100_000_001, "QueueOne"), (9_100_000_002, "QueueTwo")),
        )
        await self.db_one.commit()

    async def asyncTearDown(self):
        for db in (self.db_one, self.db_two):
            if db.in_transaction:
                await db.rollback()
        await self.db_one.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await self.db_one.commit()
        await self.db_one.close()
        await self.db_two.close()

    async def test_same_account_cannot_join_two_modes_concurrently(self):
        outcomes = await asyncio.gather(
            join_matchmaking(self.db_one, 9_100_000_001, "casual", now=2_000_000_000),
            join_matchmaking(self.db_two, 9_100_000_001, "ranked", now=2_000_000_000),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, MatchmakingError) for item in outcomes), 1)
        cursor = await self.db_one.execute(
            "SELECT mode,status FROM matchmaking_queue WHERE user_id=?",
            (9_100_000_001,),
        )
        row = await cursor.fetchone()
        self.assertIn(row["mode"], {"casual", "ranked"})
        self.assertEqual(row["status"], "queued")

    async def test_pvp_damage_uses_match_start_stats_after_equipment_changes(self):
        await self.db_one.execute(
            "UPDATE players SET level=10 WHERE user_id IN (?,?)",
            (9_100_000_001, 9_100_000_002),
        )
        await self.db_one.execute(
            "UPDATE players SET hero_class='Mage' WHERE user_id=?",
            (9_100_000_001,),
        )
        await self.db_one.commit()
        await join_matchmaking(self.db_one, 9_100_000_001, "casual", now=2_000_000_300)
        matched = await join_matchmaking(self.db_two, 9_100_000_002, "casual", now=2_000_000_301)
        match_id = matched["match_id"]
        await self.db_one.execute(
            "UPDATE players SET weapon_attack=500 WHERE user_id=?",
            (9_100_000_001,),
        )
        await self.db_one.execute(
            "UPDATE players SET armor_defense=200 WHERE user_id=?",
            (9_100_000_002,),
        )
        await self.db_one.commit()

        result = await perform_matchmaking_battle_action(
            self.db_two, 9_100_000_001, match_id, "attack", main.HERO_CLASSES,
            rng=type("FixedRandom", (), {"randint": staticmethod(lambda low, high: 0)})(),
            now=2_000_000_302,
        )
        self.assertEqual(result["damage"], 86)

    async def test_same_turn_cannot_be_replayed_across_connections(self):
        await join_matchmaking(self.db_one, 9_100_000_001, "casual", now=2_000_000_200)
        matched = await join_matchmaking(self.db_two, 9_100_000_002, "casual", now=2_000_000_201)
        match_id = matched["match_id"]
        outcomes = await asyncio.gather(
            perform_matchmaking_battle_action(
                self.db_one, 9_100_000_001, match_id, "attack", main.HERO_CLASSES
            ),
            perform_matchmaking_battle_action(
                self.db_two, 9_100_000_001, match_id, "attack", main.HERO_CLASSES
            ),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, MatchmakingBattleError) for item in outcomes), 1)
        cursor = await self.db_one.execute(
            "SELECT turn_count,turn_user_id FROM matchmaking_battles WHERE match_id=?",
            (match_id,),
        )
        battle = await cursor.fetchone()
        self.assertEqual(battle["turn_count"], 1)
        self.assertEqual(battle["turn_user_id"], 9_100_000_002)

    async def test_concurrent_turn_expiry_settles_match_and_stats_once(self):
        await join_matchmaking(self.db_one, 9_100_000_001, "casual", now=2_000_000_300)
        matched = await join_matchmaking(self.db_two, 9_100_000_002, "casual", now=2_000_000_301)
        match_id = matched["match_id"]
        states = await asyncio.gather(
            get_matchmaking_battle(self.db_one, 9_100_000_001, match_id, now=2_000_000_421),
            get_matchmaking_battle(self.db_two, 9_100_000_002, match_id, now=2_000_000_421),
        )
        self.assertEqual([state["status"] for state in states], ["finished", "finished"])
        self.assertEqual([state["winner_id"] for state in states], [9_100_000_002, 9_100_000_002])
        cursor = await self.db_one.execute(
            "SELECT pvp_wins,pvp_losses FROM players WHERE user_id=9_100_000_002"
        )
        winner_stats = await cursor.fetchone()
        self.assertEqual((winner_stats["pvp_wins"], winner_stats["pvp_losses"]), (1, 0))
        cursor = await self.db_one.execute(
            "SELECT pvp_wins,pvp_losses FROM players WHERE user_id=9_100_000_001"
        )
        loser_stats = await cursor.fetchone()
        self.assertEqual((loser_stats["pvp_wins"], loser_stats["pvp_losses"]), (0, 1))

    async def test_two_accounts_match_once_under_concurrent_joins(self):
        results = await asyncio.gather(
            join_matchmaking(self.db_one, 9_100_000_001, "casual", now=2_000_000_100),
            join_matchmaking(self.db_two, 9_100_000_002, "casual", now=2_000_000_100),
        )
        statuses = {item["status"] for item in results}
        self.assertEqual(statuses, {"queued", "matched"})
        cursor = await self.db_one.execute("SELECT COUNT(*) AS count FROM matchmaking_matches")
        self.assertEqual((await cursor.fetchone())["count"], 1)


    async def test_last_member_leave_serializes_with_party_battle_creation(self):
        user_id = 9_100_000_001
        party_id = await create_party(self.db_one, user_id)

        async def start_battle():
            try:
                return await start_party_battle(
                    self.db_two, party_id, user_id, 10, "Concurrency Warden", 500
                )
            except PartyError as exc:
                return exc

        leave_result, battle_result = await asyncio.gather(
            leave_party(self.db_one, user_id),
            start_battle(),
            return_exceptions=True,
        )
        cursor = await self.db_one.execute(
            "SELECT COUNT(*) AS count FROM parties WHERE party_id=?", (party_id,)
        )
        party_count = (await cursor.fetchone())["count"]
        cursor = await self.db_one.execute(
            "SELECT COUNT(*) AS count FROM party_battles WHERE party_id=?", (party_id,)
        )
        battle_count = (await cursor.fetchone())["count"]

        # Either leave wins and removes the empty party, or battle creation wins
        # and the leave is rejected. A party without its battle or an orphaned
        # battle is never an acceptable outcome.
        if party_count == 0:
            self.assertIsNone(leave_result)
            self.assertEqual(battle_count, 0)
            self.assertIsInstance(battle_result, PartyError)
        else:
            self.assertEqual(party_count, 1)
            self.assertEqual(battle_count, 1)
            self.assertIsInstance(leave_result, PartyError)
            self.assertIsInstance(battle_result, int)



if __name__ == "__main__":
    unittest.main()
