import asyncio
import os
import time
import unittest

from psycopg.errors import UniqueViolation

from postgres_adapter import PostgresConnection, qmark_to_pyformat
from moderation_system import (
    ModerationError,
    ban_player,
    get_active_ban,
    init_moderation_tables,
    unban_player,
)
from mana_system import consume_mana, get_mana, init_mana_tables, restore_mana
from stamina_system import consume_stamina, get_stamina, init_stamina_tables, restore_stamina
from story_system import CHAPTERS, StoryError, choose_story_path, claim_story_reward, get_story_flags, init_story_tables
from evolution_system import EVOLUTION_DEFEATS_REQUIRED, get_evolution_state, init_evolution_tables, record_monster_defeat
from world_system import WorldError, discover_world_landmark, get_current_world, get_world_choices, get_world_landmark, init_world_tables, travel_to_world
from dungeon_system import DungeonError, advance_dungeon, abandon_dungeon, claim_dungeon_reward, enter_dungeon, get_dungeon_state, init_dungeon_tables
from crafting_system import CraftingError, award_material_drop, craft_item, get_materials, init_crafting_tables
from daily_mission_system import DailyMissionError, claim_daily_mission, get_daily_missions, init_daily_mission_tables, record_daily_progress
from weekly_quest_system import WeeklyQuestError, claim_weekly_reward, get_weekly_quests, init_weekly_tables, record_weekly_progress
from report_system import ReportError, init_report_tables, list_open_reports, resolve_player_report, submit_player_report
from friend_system import FriendError, init_friend_tables, list_friends, list_pending_friend_requests, remove_friend, respond_to_friend_request, search_players, send_friend_request
from security_system import SecurityEventError, get_security_events, get_suspicious_players, init_security_tables, record_security_event
from presence_system import count_online_players, init_presence_tables, list_online_friends, touch_presence
from secret_area_system import SecretAreaError, discover_secret_area, get_secret_area_state, init_secret_area_tables
from roaming_event_system import RoamingEventError, attack_roaming_event, claim_roaming_event_reward, get_or_create_roaming_event, init_roaming_event_tables
from guild_system import (
    GuildFeatureError, attack_guild_raid, create_guild, create_guild_invite,
    declare_guild_war, get_guild_chat, get_guild_missions, guild_role,
    init_guild_features, record_guild_war_duel, respond_guild_invite,
    respond_guild_war, send_guild_message, start_guild_raid,
)
from group_system import (
    GroupError, attack_group_raid, claim_group_mission_reward,
    get_group_profile, init_group_tables, is_group_banned, list_group_players,
    record_group_activity, record_group_player, register_group, set_group_admin,
    set_group_ban, start_group_raid,
)
from party_system import (
    PartyError, attack_party_battle, create_party, get_party_battle,
    get_party_info, init_party_tables, invite_to_party, leave_party,
    respond_to_party_invite, reward_party_battle, start_party_battle,
)
from rate_limit import DatabaseSlidingWindowRateLimiter

from account_system import (
    AccountError, delete_player_account, get_settings,
    init_account_tables, update_settings,
)
from auction_system import (
    AuctionError, cancel_listing, create_listing, equip_stashed_item,
    init_auction_tables, list_active_auctions, list_stash, place_bid,
)
from premium_system import (
    PremiumError, buy_premium_item, consume_xp_boost, credit_premium_purchase,
    get_premium_balance, get_premium_packages, init_premium_tables,
)
from character_system import (
    get_appearance, init_character_tables, save_appearance,
)
from admin_tools import (
    adjust_player_coins, dashboard_stats, init_admin_tables,
    recent_admin_actions, record_admin_action,
)



from security_system import SecurityEventError, get_security_events, get_suspicious_players, init_security_tables, record_security_event


class QmarkTranslationTests(unittest.TestCase):
    def test_converts_only_placeholders_outside_literals_identifiers_and_comments(self):
        sql = """SELECT ?, '?' AS literal, "?" AS quoted_identifier,
                 $$?$$ AS dollar_text -- ?
                 /* ? /* nested ? */ still ? */"""
        converted = qmark_to_pyformat(sql)
        self.assertEqual(
            converted,
            """SELECT %s, '?' AS literal, "?" AS quoted_identifier,
                 $$?$$ AS dollar_text -- ?
                 /* ? /* nested ? */ still ? */""",
        )

    def test_rejects_unterminated_sql_quoted_text(self):
        with self.assertRaisesRegex(ValueError, "Unterminated"):
            qmark_to_pyformat("SELECT 'unfinished")

    def test_cte_select_ignores_write_words_in_literals_and_comments(self):
        from postgres_adapter import _is_write_statement

        sql = """WITH payload AS (
                     SELECT 'UPDATE players' AS note /* DELETE FROM players */
                   )
                   SELECT note FROM payload -- INSERT INTO players
              """
        self.assertFalse(_is_write_statement(sql))

    def test_data_modifying_cte_is_classified_as_write(self):
        from postgres_adapter import _is_write_statement

        sql = """WITH changed AS (
                     UPDATE players SET coins=coins+1 RETURNING user_id
                   )
                   SELECT user_id FROM changed"""
        self.assertTrue(_is_write_statement(sql))

    def test_select_for_update_is_classified_as_transactional(self):
        from postgres_adapter import _is_write_statement

        self.assertTrue(_is_write_statement("SELECT * FROM players FOR UPDATE"))

    def test_executemany_begin_immediate_is_normalized(self):
        from postgres_adapter import _prepare_statement

        self.assertEqual(_prepare_statement("BEGIN IMMEDIATE"), "BEGIN")


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PsycopgAdapterIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS adapter_probe")
        await self.db.execute(
            """CREATE TABLE adapter_probe(
                 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                 value TEXT NOT NULL UNIQUE
               )"""
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS adapter_probe")
        await self.db.commit()
        await self.db.close()

    async def test_read_does_not_open_transaction_but_write_does(self):
        cursor = await self.db.execute("SELECT 1 AS value")
        self.assertEqual((await cursor.fetchone())["value"], 1)
        self.assertFalse(self.db.in_transaction)

        await self.db.execute(
            "INSERT INTO adapter_probe(value) VALUES (?)", ("implicit-write",)
        )
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertFalse(self.db.in_transaction)

    async def test_cte_write_also_opens_transaction(self):
        await self.db.execute(
            """WITH payload(value) AS (VALUES (?))
               INSERT INTO adapter_probe(value) SELECT value FROM payload""",
            ("cte-write",),
        )
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertFalse(self.db.in_transaction)

    async def test_qmark_insert_returning_and_dict_rows(self):
        cursor = await self.db.execute(
            "INSERT INTO adapter_probe(value) VALUES (?) RETURNING id,value",
            ("first",),
        )
        row = await cursor.fetchone()
        self.assertEqual(row["value"], "first")
        self.assertIsInstance(row["id"], int)
        self.assertEqual(cursor.rowcount, 1)
        await self.db.commit()
        self.assertFalse(self.db.in_transaction)

    async def test_begin_immediate_translation_and_nested_savepoint_rollback(self):
        await self.db.execute("BEGIN IMMEDIATE")
        self.assertTrue(self.db.in_transaction)
        await self.db.execute(
            "INSERT INTO adapter_probe(value) VALUES (?)", ("alpha",)
        )
        await self.db.execute("SAVEPOINT nested_probe")

        with self.assertRaises(UniqueViolation):
            await self.db.execute(
                "INSERT INTO adapter_probe(value) VALUES (?)", ("alpha",)
            )

        await self.db.execute("ROLLBACK TO SAVEPOINT nested_probe")
        await self.db.execute("RELEASE SAVEPOINT nested_probe")
        await self.db.execute(
            "INSERT INTO adapter_probe(value) VALUES (?)", ("beta",)
        )
        await self.db.commit()
        self.assertFalse(self.db.in_transaction)

        cursor = await self.db.execute("SELECT value FROM adapter_probe ORDER BY value")
        rows = await cursor.fetchall()
        self.assertEqual([row["value"] for row in rows], ["alpha", "beta"])
        await self.db.commit()

    async def test_outer_rollback_discards_all_writes(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await self.db.execute(
            "INSERT INTO adapter_probe(value) VALUES (?)", ("rolled-back",)
        )
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertFalse(self.db.in_transaction)

        cursor = await self.db.execute(
            "SELECT COUNT(*) AS total FROM adapter_probe WHERE value=?",
            ("rolled-back",),
        )
        self.assertEqual((await cursor.fetchone())["total"], 0)
        await self.db.commit()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresModerationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS player_bans")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.execute(
            "CREATE TABLE players(user_id BIGINT PRIMARY KEY)"
        )
        await self.db.execute("INSERT INTO players(user_id) VALUES (1),(2)")
        await self.db.commit()
        await init_moderation_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS player_bans")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.commit()
        await self.db.close()

    async def test_ban_reban_and_unban_roundtrip_on_postgres(self):
        await ban_player(self.db, 900, 2, "Repeated harassment", now=1000)
        await ban_player(self.db, 901, 2, "Cheating detected", now=1100)
        row = await get_active_ban(self.db, 2)
        self.assertEqual(
            (row["actor_id"], row["reason"], row["created_at"]),
            (901, "Cheating detected", 1000),
        )

        await unban_player(self.db, 901, 2, now=1200)
        self.assertIsNone(await get_active_ban(self.db, 2))

    async def test_moderation_service_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await ban_player(self.db, 900, 2, "Repeated harassment", now=1000)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertFalse(self.db.in_transaction)
        self.assertIsNone(await get_active_ban(self.db, 2))

    async def test_missing_player_ban_is_rejected_and_not_persisted(self):
        with self.assertRaises(ModerationError):
            await ban_player(self.db, 900, 99, "Repeated harassment", now=1000)
        self.assertIsNone(await get_active_ban(self.db, 99))

    async def test_moderation_schema_initialization_is_idempotent(self):
        await init_moderation_tables(self.db)
        await init_moderation_tables(self.db)
        await self.db.commit()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresResourceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS player_mana")
        await self.db.execute("DROP TABLE IF EXISTS player_stamina")
        await self.db.commit()
        await init_mana_tables(self.db)
        await init_stamina_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS player_mana")
        await self.db.execute("DROP TABLE IF EXISTS player_stamina")
        await self.db.commit()
        await self.db.close()

    async def test_mana_consumption_and_passive_regeneration(self):
        state = await consume_mana(self.db, 301, 40, now=1000)
        self.assertEqual(state["mana"], 60)
        state = await get_mana(self.db, 301, now=1000 + 2 * 60)
        self.assertEqual(state["mana"], 62)

    async def test_stamina_consumption_and_passive_regeneration(self):
        state = await consume_stamina(self.db, 302, 30, now=1000)
        self.assertEqual(state["stamina"], 70)
        state = await get_stamina(self.db, 302, now=1000 + 2 * 300)
        self.assertEqual(state["stamina"], 72)

    async def test_mana_and_stamina_restore_are_capped(self):
        await consume_mana(self.db, 303, 10, now=1000)
        mana = await restore_mana(self.db, 303, 20, now=1000)
        self.assertEqual(mana["mana"], 100)

        await consume_stamina(self.db, 304, 20, now=1000)
        stamina = await restore_stamina(self.db, 304, 50, now=1000)
        self.assertEqual(stamina["stamina"], 100)

    async def test_mana_debit_preserves_caller_owned_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        state = await consume_mana(self.db, 305, 30, now=1000, commit=False)
        self.assertEqual(state["mana"], 70)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT 1 FROM player_mana WHERE user_id=?", (305,)
        )
        self.assertIsNone(await cursor.fetchone())

    async def test_stamina_debit_preserves_caller_owned_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        state = await consume_stamina(self.db, 306, 10, now=1000, commit=False)
        self.assertEqual(state["stamina"], 90)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT 1 FROM player_stamina WHERE user_id=?", (306,)
        )
        self.assertIsNone(await cursor.fetchone())


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresStoryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS story_reward_claims")
        await self.db.execute("DROP TABLE IF EXISTS story_flags")
        await self.db.execute("DROP TABLE IF EXISTS player_story")
        await self.db.execute("DROP TABLE IF EXISTS party_members")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.execute(
            "CREATE TABLE players(user_id BIGINT PRIMARY KEY,coins BIGINT NOT NULL DEFAULT 0)"
        )
        await self.db.execute("CREATE TABLE party_members(user_id BIGINT,party_id BIGINT)")
        await self.db.execute("INSERT INTO players(user_id,coins) VALUES(401,0)")
        await self.db.commit()
        await init_story_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS story_reward_claims")
        await self.db.execute("DROP TABLE IF EXISTS story_flags")
        await self.db.execute("DROP TABLE IF EXISTS player_story")
        await self.db.execute("DROP TABLE IF EXISTS party_members")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.commit()
        await self.db.close()

    async def test_branch_choice_and_reward_claim_roundtrip(self):
        await choose_story_path(self.db, 401, 5, 1, "follow_mira")
        await choose_story_path(self.db, 401, 5, 2, "trust_mira")
        self.assertEqual((await get_story_flags(self.db, 401))["trust_path"], "mira")

        self.assertEqual(await claim_story_reward(self.db, 401, 1), 80)
        with self.assertRaises(StoryError):
            await claim_story_reward(self.db, 401, 1)
        cursor = await self.db.execute("SELECT coins FROM players WHERE user_id=?", (401,))
        self.assertEqual((await cursor.fetchone())["coins"], 80)

    async def test_party_story_gate_and_choice(self):
        for chapter_id in range(1, 8):
            choice = next(iter(CHAPTERS[chapter_id - 1]["choices"]))
            await choose_story_path(self.db, 401, 100, chapter_id, choice)

        with self.assertRaises(StoryError):
            await choose_story_path(self.db, 401, 100, 8, "light_together")

        await self.db.execute("INSERT INTO party_members(user_id,party_id) VALUES(?,?)", (401, 55))
        result = await choose_story_path(self.db, 401, 100, 8, "light_together")
        self.assertEqual(result["chapter"]["title"], "The Last Lantern")
        await self.db.commit()

    async def test_story_choice_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await choose_story_path(self.db, 401, 1, 1, "follow_mira")
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT 1 FROM player_story WHERE user_id=? AND chapter_id=?",
            (401, 1),
        )
        self.assertIsNone(await cursor.fetchone())

    async def test_story_reward_claim_and_coin_credit_roll_back_together(self):
        await choose_story_path(self.db, 401, 1, 1, "follow_mira")
        await self.db.execute("BEGIN IMMEDIATE")
        self.assertEqual(await claim_story_reward(self.db, 401, 1), 80)
        await self.db.rollback()

        cursor = await self.db.execute(
            "SELECT 1 FROM story_reward_claims WHERE user_id=? AND chapter_id=?",
            (401, 1),
        )
        self.assertIsNone(await cursor.fetchone())
        cursor = await self.db.execute("SELECT coins FROM players WHERE user_id=?", (401,))
        self.assertEqual((await cursor.fetchone())["coins"], 0)

    async def test_story_schema_initialization_is_idempotent(self):
        await init_story_tables(self.db)
        await init_story_tables(self.db)
        await self.db.commit()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresEvolutionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS player_monster_mastery")
        await self.db.commit()
        await init_evolution_tables(self.db)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS player_monster_mastery")
        await self.db.commit()
        await self.db.close()

    async def test_mastery_threshold_and_player_isolation(self):
        for _ in range(EVOLUTION_DEFEATS_REQUIRED):
            state = await record_monster_defeat(self.db, 701, 7)
        self.assertEqual(state["defeats"], EVOLUTION_DEFEATS_REQUIRED)
        self.assertTrue(state["evolved"])
        other = await get_evolution_state(self.db, 702, 7)
        self.assertEqual(other["defeats"], 0)

    async def test_mastery_increment_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        state = await record_monster_defeat(self.db, 703, 8)
        self.assertEqual(state["defeats"], 1)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        state = await get_evolution_state(self.db, 703, 8)
        self.assertEqual(state["defeats"], 0)

    async def test_concurrent_defeats_from_separate_connections_are_not_lost(self):
        second = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            first_result, second_result = await asyncio.gather(
                record_monster_defeat(self.db, 704, 9),
                record_monster_defeat(second, 704, 9),
            )
            state = await get_evolution_state(self.db, 704, 9)
            self.assertEqual(state["defeats"], 2)
            self.assertEqual(sorted((first_result["defeats"], second_result["defeats"])), [1, 2])
        finally:
            await second.close()

    async def test_evolution_schema_initialization_is_idempotent(self):
        await init_evolution_tables(self.db)
        await init_evolution_tables(self.db)
        await self.db.commit()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresWorldServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS world_discoveries")
        await self.db.execute("DROP TABLE IF EXISTS player_worlds")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY,
                 coins BIGINT NOT NULL DEFAULT 0,
                 potions BIGINT NOT NULL DEFAULT 0
               )"""
        )
        await self.db.execute("INSERT INTO players(user_id) VALUES(801)")
        await self.db.commit()
        await init_world_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS world_discoveries")
        await self.db.execute("DROP TABLE IF EXISTS player_worlds")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.commit()
        await self.db.close()

    async def test_current_world_and_fast_travel_roundtrip(self):
        self.assertEqual(await get_current_world(self.db, 801, 1), 1)
        result = await travel_to_world(self.db, 801, 21, 3)
        self.assertEqual(result["world_id"], 3)
        choices = await get_world_choices(self.db, 801, 21)
        self.assertTrue(choices[2]["current"])
        self.assertFalse(choices[3]["unlocked"])

    async def test_landmark_reward_is_idempotent(self):
        reward = await discover_world_landmark(self.db, 801, 1, 1)
        self.assertEqual(reward["coins"], 125)
        self.assertEqual(reward["potions"], 1)
        with self.assertRaises(WorldError):
            await discover_world_landmark(self.db, 801, 1, 1)

        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (801,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (125, 1))
        landmark = await get_world_landmark(self.db, 801, 1)
        self.assertTrue(landmark["discovered"])

    async def test_world_travel_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await travel_to_world(self.db, 801, 21, 3)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT 1 FROM player_worlds WHERE user_id=?", (801,)
        )
        self.assertIsNone(await cursor.fetchone())

    async def test_landmark_reward_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await discover_world_landmark(self.db, 801, 1, 1)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (801,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (0, 0))
        cursor = await self.db.execute(
            "SELECT 1 FROM world_discoveries WHERE user_id=?", (801,)
        )
        self.assertIsNone(await cursor.fetchone())

    async def test_missing_player_does_not_keep_landmark_discovery(self):
        await self.db.execute("DELETE FROM players WHERE user_id=?", (801,))
        await self.db.commit()
        with self.assertRaisesRegex(WorldError, "Player account not found"):
            await discover_world_landmark(self.db, 801, 1, 1)
        cursor = await self.db.execute(
            "SELECT 1 FROM world_discoveries WHERE user_id=?", (801,)
        )
        self.assertIsNone(await cursor.fetchone())

    async def test_concurrent_duplicate_landmark_claim_awards_once(self):
        second = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            results = await asyncio.gather(
                discover_world_landmark(self.db, 801, 1, 1),
                discover_world_landmark(second, 801, 1, 1),
                return_exceptions=True,
            )
            successes = [item for item in results if isinstance(item, dict)]
            failures = [item for item in results if isinstance(item, WorldError)]
            self.assertEqual(len(successes), 1)
            self.assertEqual(len(failures), 1)
            cursor = await self.db.execute(
                "SELECT coins,potions FROM players WHERE user_id=?", (801,)
            )
            self.assertEqual(tuple((await cursor.fetchone()).values()), (125, 1))
            await self.db.commit()
        finally:
            await second.close()

    async def test_world_schema_initialization_is_idempotent(self):
        await init_world_tables(self.db)
        await init_world_tables(self.db)
        await self.db.commit()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresDungeonServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS dungeon_rewards")
        await self.db.execute("DROP TABLE IF EXISTS dungeon_runs")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY,
                 coins BIGINT NOT NULL DEFAULT 0,
                 potions BIGINT NOT NULL DEFAULT 0
               )"""
        )
        await self.db.execute("INSERT INTO players(user_id) VALUES(901)")
        await self.db.commit()
        await init_dungeon_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS dungeon_rewards")
        await self.db.execute("DROP TABLE IF EXISTS dungeon_runs")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.commit()
        await self.db.close()

    async def complete_first_dungeon(self):
        state = await enter_dungeon(self.db, 901, 1, 1)
        for _ in range(3):
            state = await advance_dungeon(self.db, 901, state["target_level"])
        self.assertEqual(state["status"], "completed")
        return state

    async def test_enter_advance_and_claim_dungeon_reward(self):
        await self.complete_first_dungeon()
        self.assertEqual(await claim_dungeon_reward(self.db, 901), (150, 2))
        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (901,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (150, 2))
        self.assertIsNone(await get_dungeon_state(self.db, 901))

    async def test_completed_dungeon_reward_cannot_be_claimed_twice(self):
        await self.complete_first_dungeon()
        await claim_dungeon_reward(self.db, 901)
        with self.assertRaises(DungeonError):
            await enter_dungeon(self.db, 901, 1, 1)
        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (901,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (150, 2))

    async def test_dungeon_reward_preserves_outer_transaction(self):
        await self.complete_first_dungeon()
        await self.db.execute("BEGIN IMMEDIATE")
        self.assertEqual(await claim_dungeon_reward(self.db, 901), (150, 2))
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (901,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (0, 0))
        cursor = await self.db.execute(
            "SELECT 1 FROM dungeon_rewards WHERE user_id=?", (901,)
        )
        self.assertIsNone(await cursor.fetchone())
        self.assertEqual((await get_dungeon_state(self.db, 901))["status"], "completed")

    async def test_dungeon_entry_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await enter_dungeon(self.db, 901, 1, 1)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertIsNone(await get_dungeon_state(self.db, 901))

    async def test_dungeon_advance_preserves_outer_transaction(self):
        state = await enter_dungeon(self.db, 901, 1, 1)
        await self.db.execute("BEGIN IMMEDIATE")
        await advance_dungeon(self.db, 901, state["target_level"])
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertEqual((await get_dungeon_state(self.db, 901))["room"], 1)

    async def test_concurrent_reward_claims_award_only_once(self):
        await self.complete_first_dungeon()
        second = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            results = await asyncio.gather(
                claim_dungeon_reward(self.db, 901),
                claim_dungeon_reward(second, 901),
                return_exceptions=True,
            )
            successes = [item for item in results if isinstance(item, tuple)]
            failures = [item for item in results if isinstance(item, DungeonError)]
            self.assertEqual(successes, [(150, 2)])
            self.assertEqual(len(failures), 1)
            cursor = await self.db.execute(
                "SELECT coins,potions FROM players WHERE user_id=?", (901,)
            )
            self.assertEqual(tuple((await cursor.fetchone()).values()), (150, 2))
            await self.db.commit()
        finally:
            await second.close()

    async def test_dungeon_schema_initialization_is_idempotent(self):
        await init_dungeon_tables(self.db)
        await init_dungeon_tables(self.db)
        await self.db.commit()

    async def test_telegram_sized_player_id_is_supported(self):
        player_id = 9_876_543_210
        await self.db.execute("INSERT INTO players(user_id) VALUES(?)", (player_id,))
        await self.db.commit()
        state = await enter_dungeon(self.db, player_id, 1, 1)
        self.assertEqual(state["dungeon_id"], 1)


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresTelegramIdWidthTests(unittest.IsolatedAsyncioTestCase):
    player_id = 9_876_543_210

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        tables = (
            "dungeon_rewards", "dungeon_runs", "world_discoveries", "player_worlds",
            "player_monster_mastery", "story_reward_claims", "story_flags", "player_story",
            "player_stamina", "player_mana", "player_bans", "party_members", "players",
        )
        for table in tables:
            await self.db.execute(f"DROP TABLE IF EXISTS {table}")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY,
                 coins BIGINT NOT NULL DEFAULT 0,
                 potions BIGINT NOT NULL DEFAULT 0
               )"""
        )
        await self.db.execute(
            "INSERT INTO players(user_id) VALUES(?)", (self.player_id,)
        )
        await self.db.execute("CREATE TABLE party_members(user_id BIGINT,party_id BIGINT)")
        await self.db.commit()
        await init_moderation_tables(self.db)
        await init_mana_tables(self.db)
        await init_stamina_tables(self.db)
        await init_story_tables(self.db)
        await init_evolution_tables(self.db)
        await init_world_tables(self.db)
        await init_dungeon_tables(self.db)

    async def asyncTearDown(self):
        tables = (
            "dungeon_rewards", "dungeon_runs", "world_discoveries", "player_worlds",
            "player_monster_mastery", "story_reward_claims", "story_flags", "player_story",
            "player_stamina", "player_mana", "player_bans", "party_members", "players",
        )
        for table in tables:
            await self.db.execute(f"DROP TABLE IF EXISTS {table}")
        await self.db.commit()
        await self.db.close()

    async def test_all_migrated_service_schemas_accept_64_bit_telegram_ids(self):
        player_id = self.player_id
        await ban_player(self.db, player_id + 1, player_id, "64-bit account", now=1000)
        self.assertEqual((await get_active_ban(self.db, player_id))["actor_id"], player_id + 1)

        self.assertEqual((await consume_mana(self.db, player_id, 10, now=1000))["mana"], 90)
        self.assertEqual((await consume_stamina(self.db, player_id, 10, now=1000))["stamina"], 90)
        await choose_story_path(self.db, player_id, 1, 1, "follow_mira")
        self.assertEqual((await get_story_flags(self.db, player_id)), {})
        self.assertEqual((await record_monster_defeat(self.db, player_id, 7))["defeats"], 1)
        self.assertEqual(await travel_to_world(self.db, player_id, 21, 3), {
            "world_id": 3, "name": "Stormglass Highlands", "min_level": 21
        })
        self.assertEqual((await discover_world_landmark(self.db, player_id, 21, 3))["coins"], 175)
        self.assertEqual((await enter_dungeon(self.db, player_id, 21, 3))["dungeon_id"], 3)


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresCraftingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS crafted_items")
        await self.db.execute("DROP TABLE IF EXISTS player_materials")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY,
                 weapon TEXT,
                 weapon_attack BIGINT NOT NULL DEFAULT 0,
                 armor TEXT,
                 armor_defense BIGINT NOT NULL DEFAULT 0
               )"""
        )
        await self.db.execute("INSERT INTO players(user_id) VALUES(1001)")
        await self.db.commit()
        await init_crafting_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS crafted_items")
        await self.db.execute("DROP TABLE IF EXISTS player_materials")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.commit()
        await self.db.close()

    async def add_iron_sword_materials(self, user_id=1001):
        await self.db.execute(
            "INSERT INTO player_materials(user_id,material_id,quantity) VALUES(?,?,?)",
            (user_id, "iron_ore", 3),
        )
        await self.db.execute(
            "INSERT INTO player_materials(user_id,material_id,quantity) VALUES(?,?,?)",
            (user_id, "ember_shard", 1),
        )
        await self.db.commit()

    async def test_craft_item_consumes_materials_and_equips_upgrade(self):
        await self.add_iron_sword_materials()
        result = await craft_item(self.db, 1001, 5, "iron_sword")
        self.assertEqual(result["name"], "Forged Iron Sword")
        self.assertEqual(await get_materials(self.db, 1001), {
            "iron_ore": 0, "ember_shard": 0
        })
        cursor = await self.db.execute(
            "SELECT weapon,weapon_attack FROM players WHERE user_id=?", (1001,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), ("Forged Iron Sword", 12))
        with self.assertRaisesRegex(CraftingError, "already crafted"):
            await craft_item(self.db, 1001, 5, "iron_sword")

    async def test_failed_craft_rolls_back_partial_material_debits(self):
        await self.db.execute(
            "INSERT INTO player_materials(user_id,material_id,quantity) VALUES(?,?,?)",
            (1001, "iron_ore", 3),
        )
        await self.db.commit()
        with self.assertRaisesRegex(CraftingError, "Missing materials"):
            await craft_item(self.db, 1001, 5, "iron_sword")
        self.assertEqual(await get_materials(self.db, 1001), {"iron_ore": 3})
        cursor = await self.db.execute(
            "SELECT 1 FROM crafted_items WHERE user_id=?", (1001,)
        )
        self.assertIsNone(await cursor.fetchone())

    async def test_crafting_preserves_outer_transaction(self):
        await self.add_iron_sword_materials()
        await self.db.execute("BEGIN IMMEDIATE")
        await craft_item(self.db, 1001, 5, "iron_sword")
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertEqual(await get_materials(self.db, 1001), {
            "iron_ore": 3, "ember_shard": 1
        })
        cursor = await self.db.execute(
            "SELECT 1 FROM crafted_items WHERE user_id=?", (1001,)
        )
        self.assertIsNone(await cursor.fetchone())

    async def test_material_drop_upsert_increments_quantity(self):
        class FixedRng:
            def __init__(self):
                self.values = iter((0.1, 0.1))
            def random(self):
                return next(self.values)

        await award_material_drop(
            self.db, 1001, {"level": 10, "boss": False}, rng=FixedRng()
        )
        await award_material_drop(
            self.db, 1001, {"level": 10, "boss": False}, rng=FixedRng()
        )
        self.assertEqual(await get_materials(self.db, 1001), {"iron_ore": 2})

    async def test_concurrent_crafts_cannot_spend_the_same_materials_twice(self):
        await self.add_iron_sword_materials()
        second = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            results = await asyncio.gather(
                craft_item(self.db, 1001, 5, "iron_sword"),
                craft_item(second, 1001, 5, "iron_sword"),
                return_exceptions=True,
            )
            successes = [item for item in results if isinstance(item, dict)]
            failures = [item for item in results if isinstance(item, CraftingError)]
            self.assertEqual(len(successes), 1)
            self.assertEqual(len(failures), 1)
            cursor = await self.db.execute(
                "SELECT COUNT(*) AS total FROM crafted_items WHERE user_id=?", (1001,)
            )
            self.assertEqual((await cursor.fetchone())["total"], 1)
            self.assertEqual(await get_materials(self.db, 1001), {
                "iron_ore": 0, "ember_shard": 0
            })
            await self.db.commit()
        finally:
            await second.close()

    async def test_crafting_schema_initialization_is_idempotent(self):
        await init_crafting_tables(self.db)
        await init_crafting_tables(self.db)
        await self.db.commit()

    async def test_crafting_supports_64_bit_telegram_player_ids(self):
        player_id = 9_876_543_210
        await self.db.execute("INSERT INTO players(user_id) VALUES(?)", (player_id,))
        await self.db.execute(
            "INSERT INTO player_materials(user_id,material_id,quantity) VALUES(?,?,?)",
            (player_id, "iron_ore", 3),
        )
        await self.db.execute(
            "INSERT INTO player_materials(user_id,material_id,quantity) VALUES(?,?,?)",
            (player_id, "ember_shard", 1),
        )
        await self.db.commit()
        await craft_item(self.db, player_id, 5, "iron_sword")
        self.assertEqual((await get_materials(self.db, player_id))["iron_ore"], 0)


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresQuestServiceTests(unittest.IsolatedAsyncioTestCase):
    player_id = 9_876_543_210

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS player_daily_missions")
        await self.db.execute("DROP TABLE IF EXISTS player_weekly_quests")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY,
                 coins BIGINT NOT NULL DEFAULT 0,
                 potions BIGINT NOT NULL DEFAULT 0
               )"""
        )
        await self.db.execute("INSERT INTO players(user_id) VALUES(?)", (self.player_id,))
        await self.db.commit()
        await init_daily_mission_tables(self.db)
        await init_weekly_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS player_daily_missions")
        await self.db.execute("DROP TABLE IF EXISTS player_weekly_quests")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.commit()
        await self.db.close()

    async def test_daily_progress_claim_and_idempotency(self):
        await record_daily_progress(self.db, self.player_id, "wins", 100, now=1000)
        missions = await get_daily_missions(self.db, self.player_id, now=1000)
        hunter = next(item for item in missions if item["id"] == "daily_hunter")
        self.assertEqual(hunter["progress"], 3)
        self.assertTrue(hunter["completed"])

        reward = await claim_daily_mission(
            self.db, self.player_id, "daily_hunter", now=1000
        )
        self.assertEqual((reward["coins"], reward["potions"]), (75, 1))
        with self.assertRaises(DailyMissionError):
            await claim_daily_mission(
                self.db, self.player_id, "daily_hunter", now=1000
            )
        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.player_id,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (75, 1))

    async def test_daily_progress_rolls_over_at_utc_day_boundary(self):
        await record_daily_progress(self.db, self.player_id, "wins", 2, now=1000)
        next_day = await get_daily_missions(
            self.db, self.player_id, now=86400 + 1000
        )
        hunter = next(item for item in next_day if item["id"] == "daily_hunter")
        self.assertEqual(hunter["progress"], 0)
        self.assertFalse(hunter["claimed"])

    async def test_weekly_progress_claim_and_idempotency(self):
        await record_weekly_progress(self.db, self.player_id, "wins", 100, now=1)
        quests = await get_weekly_quests(self.db, self.player_id, now=1)
        hunter = next(item for item in quests if item["id"] == "weekly_hunter")
        self.assertEqual(hunter["progress"], 15)
        self.assertTrue(hunter["completed"])
        self.assertTrue(hunter["week_key"].endswith("W01"))

        reward = await claim_weekly_reward(
            self.db, self.player_id, "weekly_hunter", now=1
        )
        self.assertEqual((reward["coins"], reward["potions"]), (300, 2))
        with self.assertRaises(WeeklyQuestError):
            await claim_weekly_reward(
                self.db, self.player_id, "weekly_hunter", now=1
            )
        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.player_id,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (300, 2))

    async def test_weekly_progress_rolls_over_at_utc_week_boundary(self):
        await record_weekly_progress(self.db, self.player_id, "wins", 5, now=1)
        next_week = await get_weekly_quests(
            self.db, self.player_id, now=7 * 86400 + 1
        )
        hunter = next(item for item in next_week if item["id"] == "weekly_hunter")
        self.assertEqual(hunter["progress"], 0)
        self.assertFalse(hunter["claimed"])
        self.assertTrue(hunter["week_key"].endswith("W02"))

    async def test_daily_claim_preserves_outer_transaction(self):
        await record_daily_progress(self.db, self.player_id, "wins", 3, now=1000)
        await self.db.execute("BEGIN IMMEDIATE")
        await claim_daily_mission(self.db, self.player_id, "daily_hunter", now=1000)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.player_id,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (0, 0))
        missions = await get_daily_missions(self.db, self.player_id, now=1000)
        hunter = next(item for item in missions if item["id"] == "daily_hunter")
        self.assertFalse(hunter["claimed"])

    async def test_weekly_claim_preserves_outer_transaction(self):
        await record_weekly_progress(self.db, self.player_id, "wins", 15, now=1)
        await self.db.execute("BEGIN IMMEDIATE")
        await claim_weekly_reward(self.db, self.player_id, "weekly_hunter", now=1)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.player_id,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (0, 0))
        quests = await get_weekly_quests(self.db, self.player_id, now=1)
        hunter = next(item for item in quests if item["id"] == "weekly_hunter")
        self.assertFalse(hunter["claimed"])

    async def test_concurrent_daily_claims_award_once(self):
        await record_daily_progress(self.db, self.player_id, "wins", 3, now=1000)
        second = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            results = await asyncio.gather(
                claim_daily_mission(self.db, self.player_id, "daily_hunter", now=1000),
                claim_daily_mission(second, self.player_id, "daily_hunter", now=1000),
                return_exceptions=True,
            )
            self.assertEqual(sum(isinstance(x, dict) for x in results), 1)
            self.assertEqual(sum(isinstance(x, DailyMissionError) for x in results), 1)
            cursor = await self.db.execute(
                "SELECT coins,potions FROM players WHERE user_id=?", (self.player_id,)
            )
            self.assertEqual(tuple((await cursor.fetchone()).values()), (75, 1))
            await self.db.commit()
        finally:
            await second.close()

    async def test_quest_schemas_initialize_idempotently(self):
        await init_daily_mission_tables(self.db)
        await init_weekly_tables(self.db)
        await self.db.commit()

    async def test_quest_schema_initialization_preserves_outer_transaction(self):
        await self.db.execute("DROP TABLE player_daily_missions")
        await self.db.execute("DROP TABLE player_weekly_quests")
        await self.db.commit()

        await self.db.execute("BEGIN")
        await init_daily_mission_tables(self.db)
        await init_weekly_tables(self.db)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()

        for table in ("player_daily_missions", "player_weekly_quests"):
            cursor = await self.db.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=current_schema() AND table_name=?",
                (table,),
            )
            self.assertIsNone(await cursor.fetchone(), table)


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresReportServiceTests(unittest.IsolatedAsyncioTestCase):
    reporter_id = 9_876_543_210
    target_id = 9_876_543_211
    admin_id = 9_876_543_212

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS player_reports")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.execute("CREATE TABLE players(user_id BIGINT PRIMARY KEY)")
        await self.db.execute(
            "INSERT INTO players(user_id) VALUES(?),(?)",
            (self.reporter_id, self.target_id),
        )
        await self.db.commit()
        await init_report_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS player_reports")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.commit()
        await self.db.close()

    async def test_report_submit_review_and_resubmit_lifecycle(self):
        report_id = await submit_player_report(
            self.db, self.reporter_id, self.target_id, "Repeated harassment in chat", now=1000
        )
        self.assertIsInstance(report_id, int)
        self.assertEqual(len(await list_open_reports(self.db)), 1)
        self.assertTrue(
            await resolve_player_report(
                self.db, report_id, self.admin_id, "reviewed", "Evidence checked"
            )
        )
        self.assertEqual(await list_open_reports(self.db), [])

        next_id = await submit_player_report(
            self.db, self.reporter_id, self.target_id, "New incident after review", now=2000
        )
        self.assertGreater(next_id, report_id)

    async def test_duplicate_open_report_is_rejected(self):
        await submit_player_report(
            self.db, self.reporter_id, self.target_id, "Repeated harassment in chat", now=1000
        )
        with self.assertRaises(ReportError):
            await submit_player_report(
                self.db, self.reporter_id, self.target_id, "Another valid report reason", now=1001
            )
        self.assertEqual(len(await list_open_reports(self.db)), 1)

    async def test_concurrent_duplicate_reports_are_blocked_by_unique_index(self):
        second = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            results = await asyncio.gather(
                submit_player_report(
                    self.db, self.reporter_id, self.target_id,
                    "Repeated harassment in chat", now=1000
                ),
                submit_player_report(
                    second, self.reporter_id, self.target_id,
                    "Another valid report reason", now=1000
                ),
                return_exceptions=True,
            )
            self.assertEqual(sum(isinstance(x, int) for x in results), 1)
            self.assertEqual(sum(isinstance(x, ReportError) for x in results), 1)
            self.assertEqual(len(await list_open_reports(self.db)), 1)
            await self.db.commit()
        finally:
            await second.close()

    async def test_report_submission_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await submit_player_report(
            self.db, self.reporter_id, self.target_id, "Repeated harassment in chat", now=1000
        )
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertEqual(await list_open_reports(self.db), [])

    async def test_report_schema_initialization_is_idempotent(self):
        await init_report_tables(self.db)
        await init_report_tables(self.db)
        await self.db.commit()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresFriendServiceTests(unittest.IsolatedAsyncioTestCase):
    alice = 9_876_543_210
    bob = 9_876_543_211
    charlie = 9_876_543_212

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS friend_requests")
        await self.db.execute("DROP TABLE IF EXISTS friendships")
        await self.db.execute("DROP TABLE IF EXISTS player_settings")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.execute(
            "CREATE TABLE players(user_id BIGINT PRIMARY KEY,username TEXT NOT NULL,level INTEGER NOT NULL DEFAULT 1)"
        )
        await self.db.execute(
            "CREATE TABLE player_settings(user_id BIGINT PRIMARY KEY,profile_visibility TEXT NOT NULL DEFAULT 'public')"
        )
        await self.db.execute(
            "INSERT INTO players(user_id,username,level) VALUES(?,?,?),(?,?,?),(?,?,?)",
            (
                self.alice, "Alice", 20,
                self.bob, "Bob", 15,
                self.charlie, "Charlie", 10,
            ),
        )
        await self.db.execute(
            "INSERT INTO player_settings(user_id,profile_visibility) VALUES(?,?),(?,?),(?,?)",
            (
                self.alice, "public",
                self.bob, "friends",
                self.charlie, "private",
            ),
        )
        await self.db.commit()
        await init_friend_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS friend_requests")
        await self.db.execute("DROP TABLE IF EXISTS friendships")
        await self.db.execute("DROP TABLE IF EXISTS player_settings")
        await self.db.execute("DROP TABLE IF EXISTS players")
        await self.db.commit()
        await self.db.close()

    async def test_send_accept_list_and_search_friends(self):
        request_id = await send_friend_request(self.db, self.alice, self.bob)
        pending = await list_pending_friend_requests(self.db, self.bob)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["request_id"], request_id)
        await respond_to_friend_request(self.db, request_id, self.bob, True)

        friends = await list_friends(self.db, self.alice)
        self.assertEqual([item["user_id"] for item in friends], [self.bob])
        results = await search_players(self.db, self.alice, "bob", limit=10)
        self.assertEqual([item["user_id"] for item in results], [self.bob])
        hidden = await search_players(self.db, self.alice, "charlie", limit=10)
        self.assertEqual(hidden, [])

    async def test_remove_friend_allows_a_new_request(self):
        request_id = await send_friend_request(self.db, self.alice, self.bob)
        await respond_to_friend_request(self.db, request_id, self.bob, True)
        await remove_friend(self.db, self.alice, self.bob)
        self.assertEqual(await list_friends(self.db, self.alice), [])
        new_id = await send_friend_request(self.db, self.alice, self.bob)
        self.assertGreater(new_id, request_id)

    async def test_reverse_pending_request_is_accepted(self):
        request_id = await send_friend_request(self.db, self.alice, self.bob)
        with self.assertRaisesRegex(FriendError, "Accept it instead"):
            await send_friend_request(self.db, self.bob, self.alice)
        await respond_to_friend_request(self.db, request_id, self.bob, True)
        self.assertEqual(len(await list_friends(self.db, self.alice)), 1)

    async def test_duplicate_open_request_is_rejected(self):
        await send_friend_request(self.db, self.alice, self.bob)
        with self.assertRaises(FriendError):
            await send_friend_request(self.db, self.alice, self.bob)

    async def test_concurrent_duplicate_requests_are_serialized(self):
        second = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            results = await asyncio.gather(
                send_friend_request(self.db, self.alice, self.bob),
                send_friend_request(second, self.alice, self.bob),
                return_exceptions=True,
            )
            self.assertEqual(sum(isinstance(x, int) for x in results), 1)
            self.assertEqual(sum(isinstance(x, FriendError) for x in results), 1)
            self.assertEqual(len(await list_pending_friend_requests(self.db, self.bob)), 1)
            await self.db.commit()
        finally:
            await second.close()

    async def test_pending_request_limit_is_enforced(self):
        for target in range(2000, 2010):
            await send_friend_request(self.db, self.alice, target)
        with self.assertRaises(FriendError):
            await send_friend_request(self.db, self.alice, 2010)

    async def test_friend_request_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await send_friend_request(self.db, self.alice, self.bob)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertEqual(await list_pending_friend_requests(self.db, self.bob), [])

    async def test_friend_schema_initialization_is_idempotent(self):
        await init_friend_tables(self.db)
        await init_friend_tables(self.db)
        await self.db.commit()


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresSecurityEventServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS security_events")
        await self.db.commit()
        await init_security_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS security_events")
        await self.db.commit()
        await self.db.close()

    async def test_records_and_aggregates_security_events(self):
        await record_security_event(self.db, 9_876_543_210, "invalid_battle_action", "unknown action", 2)
        await record_security_event(self.db, 9_876_543_210, "invalid_monster_request", "level 999", 4)
        await record_security_event(self.db, 9_876_543_211, "invalid_social_action", "unsupported action", 1)
        rows = await get_suspicious_players(self.db)
        self.assertEqual(rows[0]["user_id"], 9_876_543_210)
        self.assertEqual(rows[0]["event_count"], 2)
        self.assertEqual(rows[0]["max_severity"], 4)
        self.assertEqual(rows[0]["risk_score"], 6)
        events = await get_security_events(self.db, 9_876_543_210)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["details"], "level 999")

    async def test_event_details_are_bounded_and_invalid_values_rejected(self):
        await record_security_event(self.db, 1, "invalid_battle_action", "x" * 400)
        rows = await get_security_events(self.db, 1)
        self.assertEqual(len(rows[0]["details"]), 240)
        with self.assertRaises(SecurityEventError):
            await record_security_event(self.db, 1, "not_allowed")
        with self.assertRaises(SecurityEventError):
            await get_suspicious_players(self.db, window_minutes=0)

    async def test_security_event_write_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await record_security_event(self.db, 303, "invalid_battle_action", "rolled back with caller")
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertEqual(await get_security_events(self.db, 303), [])

    async def test_cleanup_respects_configured_event_cap(self):
        from unittest.mock import patch
        with patch("security_system.MAX_SECURITY_EVENTS", 2), patch("security_system.CLEANUP_INTERVAL", 1):
            for index in range(5):
                await record_security_event(self.db, 404, "invalid_battle_action", str(index))
        rows = await get_security_events(self.db, 404, limit=100)
        self.assertEqual([row["details"] for row in rows], ["4", "3"])

    async def test_security_schema_initialization_is_idempotent(self):
        await init_security_tables(self.db)
        await self.db.commit()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresPresenceServiceTests(unittest.IsolatedAsyncioTestCase):
    user_id = 9_876_543_210
    friend_id = 9_876_543_211

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        for table in ("player_presence", "friend_requests", "player_settings", "players"):
            await self.db.execute(f"DROP TABLE IF EXISTS {table}")
        await self.db.execute(
            "CREATE TABLE players(user_id BIGINT PRIMARY KEY,username TEXT,level INTEGER)"
        )
        await self.db.execute(
            "CREATE TABLE friend_requests(user_low BIGINT,user_high BIGINT,status TEXT)"
        )
        await self.db.execute(
            "CREATE TABLE player_settings(user_id BIGINT PRIMARY KEY,profile_visibility TEXT)"
        )
        await self.db.execute(
            "INSERT INTO players VALUES(?,?,?),(?,?,?)",
            (self.user_id, "Ash", 5, self.friend_id, "Mira", 7),
        )
        await self.db.execute(
            "INSERT INTO friend_requests VALUES(?,?,?)",
            (self.user_id, self.friend_id, "accepted"),
        )
        await self.db.commit()
        await init_presence_tables(self.db)

    async def asyncTearDown(self):
        for table in ("player_presence", "friend_requests", "player_settings", "players"):
            await self.db.execute(f"DROP TABLE IF EXISTS {table}")
        await self.db.commit()
        await self.db.close()

    async def test_touch_and_count_support_64_bit_telegram_ids(self):
        await touch_presence(self.db, self.user_id)
        await touch_presence(self.db, self.friend_id)
        self.assertEqual(await count_online_players(self.db), 2)

    async def test_online_friends_respect_privacy_setting(self):
        await touch_presence(self.db, self.friend_id)
        rows = await list_online_friends(self.db, self.user_id)
        self.assertEqual([row["user_id"] for row in rows], [self.friend_id])
        await self.db.execute(
            "INSERT INTO player_settings(user_id,profile_visibility) VALUES(?,?)",
            (self.friend_id, "private"),
        )
        await self.db.commit()
        self.assertEqual(await list_online_friends(self.db, self.user_id), [])

    async def test_presence_write_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await touch_presence(self.db, self.user_id)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        self.assertEqual(await count_online_players(self.db), 0)

    async def test_presence_schema_initialization_is_idempotent(self):
        await init_presence_tables(self.db)
        await self.db.commit()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresSecretAreaServiceTests(unittest.IsolatedAsyncioTestCase):
    user_id = 9_876_543_210

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        for table in ("player_secret_areas", "player_monster_mastery", "boss_defeats", "players"):
            await self.db.execute(f"DROP TABLE IF EXISTS {table}")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY,
                 coins BIGINT NOT NULL DEFAULT 0,
                 potions BIGINT NOT NULL DEFAULT 0
               )"""
        )
        await self.db.execute("INSERT INTO players(user_id) VALUES(?)", (self.user_id,))
        await self.db.execute(
            "CREATE TABLE boss_defeats(user_id BIGINT,monster_level INTEGER)"
        )
        await self.db.commit()
        await init_evolution_tables(self.db)
        await init_secret_area_tables(self.db)

    async def asyncTearDown(self):
        for table in ("player_secret_areas", "player_monster_mastery", "boss_defeats", "players"):
            await self.db.execute(f"DROP TABLE IF EXISTS {table}")
        await self.db.commit()
        await self.db.close()

    async def unlock_first_area(self):
        await self.db.execute(
            "INSERT INTO boss_defeats(user_id,monster_level) VALUES(?,?)",
            (self.user_id, 10),
        )
        await self.db.commit()
        for _ in range(5):
            await record_monster_defeat(self.db, self.user_id, 1)

    async def test_boss_and_five_wins_unlock_and_award_once(self):
        await self.unlock_first_area()
        state = await get_secret_area_state(self.db, self.user_id, 10, 1)
        self.assertTrue(state["unlocked"])
        reward = await discover_secret_area(self.db, self.user_id, 10, 1)
        self.assertEqual((reward["coins"], reward["potions"]), (350, 2))
        with self.assertRaises(SecretAreaError):
            await discover_secret_area(self.db, self.user_id, 10, 1)
        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.user_id,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (350, 2))

    async def test_discovery_and_reward_roll_back_with_outer_transaction(self):
        await self.unlock_first_area()
        await self.db.execute("BEGIN IMMEDIATE")
        await discover_secret_area(self.db, self.user_id, 10, 1)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        state = await get_secret_area_state(self.db, self.user_id, 10, 1)
        self.assertFalse(state["discovered"])
        cursor = await self.db.execute(
            "SELECT coins,potions FROM players WHERE user_id=?", (self.user_id,)
        )
        self.assertEqual(tuple((await cursor.fetchone()).values()), (0, 0))

    async def test_missing_player_does_not_keep_discovery(self):
        await self.unlock_first_area()
        await self.db.execute("DELETE FROM players WHERE user_id=?", (self.user_id,))
        await self.db.commit()
        with self.assertRaisesRegex(SecretAreaError, "Player account not found"):
            await discover_secret_area(self.db, self.user_id, 10, 1)
        cursor = await self.db.execute(
            "SELECT 1 FROM player_secret_areas WHERE user_id=?", (self.user_id,)
        )
        self.assertIsNone(await cursor.fetchone())

    async def test_secret_area_schema_initialization_is_idempotent(self):
        await init_secret_area_tables(self.db)
        await self.db.commit()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresRoamingEventServiceTests(unittest.IsolatedAsyncioTestCase):
    user_id = 9_876_543_210
    other_id = 9_876_543_211

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        for table in ("roaming_event_participants", "roaming_events", "players"):
            await self.db.execute(f"DROP TABLE IF EXISTS {table}")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY,
                 level INTEGER NOT NULL DEFAULT 1,
                 xp INTEGER NOT NULL DEFAULT 0,
                 coins BIGINT NOT NULL DEFAULT 0,
                 hp INTEGER NOT NULL DEFAULT 120,
                 max_hp INTEGER NOT NULL DEFAULT 120,
                 hero_class TEXT NOT NULL DEFAULT 'Knight'
               )"""
        )
        await self.db.execute(
            "INSERT INTO players(user_id) VALUES(?),(?)",
            (self.user_id, self.other_id),
        )
        await self.db.commit()
        await init_roaming_event_tables(self.db)

    async def asyncTearDown(self):
        for table in ("roaming_event_participants", "roaming_events", "players"):
            await self.db.execute(f"DROP TABLE IF EXISTS {table}")
        await self.db.commit()
        await self.db.close()

    async def test_event_creation_and_shared_damage_support_64_bit_ids(self):
        event = await get_or_create_roaming_event(
            self.db, 1, 3, "Mire Colossus", 1, now=1000
        )
        same = await get_or_create_roaming_event(
            self.db, 1, 4, "Different Monster", 1, now=1001
        )
        self.assertEqual(event["event_id"], same["event_id"])
        self.assertEqual(same["monster_name"], "Mire Colossus")
        result = await attack_roaming_event(
            self.db, event["event_id"], self.user_id, 5, now=1000
        )
        self.assertEqual(result["damage"], 5)
        self.assertEqual(result["participants"], 1)

    async def test_contributor_reward_is_atomic_and_one_time(self):
        event = await get_or_create_roaming_event(
            self.db, 1, 3, "Mire Colossus", 1, now=1000
        )
        await attack_roaming_event(self.db, event["event_id"], self.user_id, 5, now=1000)
        await attack_roaming_event(self.db, event["event_id"], self.other_id, 100, now=1000)
        reward = await claim_roaming_event_reward(self.db, event["event_id"], self.user_id)
        self.assertEqual(reward["coins"], 136)
        with self.assertRaises(RoamingEventError):
            await claim_roaming_event_reward(self.db, event["event_id"], self.user_id)
        cursor = await self.db.execute(
            "SELECT coins FROM players WHERE user_id=?", (self.user_id,)
        )
        self.assertEqual((await cursor.fetchone())["coins"], 136)

    async def test_reward_claim_preserves_outer_transaction(self):
        event = await get_or_create_roaming_event(
            self.db, 1, 3, "Mire Colossus", 1, now=1000
        )
        await attack_roaming_event(self.db, event["event_id"], self.user_id, 5, now=1000)
        await attack_roaming_event(self.db, event["event_id"], self.other_id, 100, now=1000)
        await self.db.execute("BEGIN IMMEDIATE")
        await claim_roaming_event_reward(self.db, event["event_id"], self.user_id)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT coins FROM players WHERE user_id=?", (self.user_id,)
        )
        self.assertEqual((await cursor.fetchone())["coins"], 0)
        cursor = await self.db.execute(
            "SELECT reward_claimed FROM roaming_event_participants WHERE event_id=? AND user_id=?",
            (event["event_id"], self.user_id),
        )
        self.assertEqual((await cursor.fetchone())["reward_claimed"], 0)

    async def test_roaming_schema_initialization_is_idempotent(self):
        await init_roaming_event_tables(self.db)
        await self.db.commit()


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class GuildPostgresIntegrationTests(unittest.IsolatedAsyncioTestCase):
    user_id = 5_000_000_000_000_001
    member_id = 5_000_000_000_000_002
    target_leader_id = 5_000_000_000_000_003

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        for table in (
            "guild_war_duel_events", "guild_wars", "guild_raid_cooldowns",
            "guild_raid_contributions", "guild_raids", "guild_missions",
            "guild_chat_messages", "guild_announcements", "guild_invites",
            "guild_members", "guilds", "players",
        ):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY, username TEXT,
                 level INTEGER NOT NULL DEFAULT 1, xp INTEGER NOT NULL DEFAULT 0,
                 coins BIGINT NOT NULL DEFAULT 1000
               )"""
        )
        await self.db.execute(
            """CREATE TABLE guilds(
                 guild_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                 name TEXT NOT NULL UNIQUE, leader_id BIGINT NOT NULL,
                 guild_level INTEGER NOT NULL DEFAULT 1,
                 guild_xp BIGINT NOT NULL DEFAULT 0
               )"""
        )
        await self.db.execute(
            """CREATE TABLE guild_members(
                 user_id BIGINT PRIMARY KEY, guild_id BIGINT NOT NULL,
                 role TEXT NOT NULL, joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        await self.db.execute(
            "INSERT INTO players(user_id,username) VALUES(?,?),(?,?),(?,?)",
            (
                self.user_id, "leader",
                self.member_id, "member",
                self.target_leader_id, "target",
            ),
        )
        await self.db.execute(
            "INSERT INTO guilds(guild_id,name,leader_id) VALUES(900,'Target Guild',?)",
            (self.target_leader_id,),
        )
        await self.db.execute(
            "INSERT INTO guild_members(user_id,guild_id,role) VALUES(?,900,'leader')",
            (self.target_leader_id,),
        )
        await self.db.commit()
        await init_guild_features(self.db)

    async def asyncTearDown(self):
        for table in (
            "guild_war_duel_events", "guild_wars", "guild_raid_cooldowns",
            "guild_raid_contributions", "guild_raids", "guild_missions",
            "guild_chat_messages", "guild_announcements", "guild_invites",
            "guild_members", "guilds", "players",
        ):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.commit()
        await self.db.close()

    async def test_guild_creation_invites_chat_and_missions_support_bigint_ids(self):
        guild_id = await create_guild(self.db, self.user_id, "High Peak")
        self.assertIsInstance(guild_id, int)
        self.assertEqual(await guild_role(self.db, guild_id, self.user_id), "leader")

        invite_id = await create_guild_invite(
            self.db, guild_id, self.user_id, self.member_id
        )
        self.assertIsInstance(invite_id, int)
        self.assertEqual(
            await respond_guild_invite(self.db, invite_id, self.member_id, True),
            guild_id,
        )
        self.assertEqual(await guild_role(self.db, guild_id, self.member_id), "member")

        message_id = await send_guild_message(
            self.db, guild_id, self.member_id, "  Ready   for   the raid "
        )
        self.assertIsInstance(message_id, int)
        messages = await get_guild_chat(self.db, guild_id, self.member_id)
        self.assertEqual(messages[0]["message"], "Ready for the raid")

        first = await get_guild_missions(self.db, guild_id, "2026-11-02")
        second = await get_guild_missions(self.db, guild_id, "2026-11-02")
        self.assertEqual(len(first), 3)
        self.assertEqual(len(second), 3)

    async def test_raid_and_war_generated_ids_and_idempotency(self):
        guild_id = await create_guild(self.db, self.user_id, "Raiders")
        raid_id = await start_guild_raid(
            self.db, guild_id, self.user_id, 10, "Root Warden", 100
        )
        self.assertIsInstance(raid_id, int)
        with self.assertRaises(GuildFeatureError):
            await attack_guild_raid(self.db, guild_id, self.member_id, 100)

        # Add the member through the invitation flow before attacking.
        invite_id = await create_guild_invite(
            self.db, guild_id, self.user_id, self.member_id
        )
        await respond_guild_invite(self.db, invite_id, self.member_id, True)
        raid_result = await attack_guild_raid(self.db, guild_id, self.member_id, 100)
        self.assertEqual(raid_result["status"], "won")

        war_id = await declare_guild_war(
            self.db, guild_id, self.user_id, 900
        )
        self.assertIsInstance(war_id, int)
        self.assertEqual(
            await respond_guild_war(self.db, war_id, self.target_leader_id, True),
            "active",
        )
        first = await record_guild_war_duel(
            self.db, self.user_id, self.target_leader_id, self.user_id, duel_id=8_000_001
        )
        duplicate = await record_guild_war_duel(
            self.db, self.user_id, self.target_leader_id, self.user_id, duel_id=8_000_001
        )
        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)

    async def test_concurrent_guild_raid_starts_create_only_one_active_raid(self):
        guild_id = await create_guild(self.db, self.user_id, "Concurrent Raiders")
        other_db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            results = await asyncio.gather(
                start_guild_raid(
                    self.db, guild_id, self.user_id, 10, "Root Warden", 1000
                ),
                start_guild_raid(
                    other_db, guild_id, self.user_id, 10, "Ash Titan", 1000
                ),
                return_exceptions=True,
            )
            self.assertEqual(sum(isinstance(result, int) for result in results), 1)
            self.assertEqual(
                sum(isinstance(result, GuildFeatureError) for result in results), 1
            )
            cursor = await self.db.execute(
                "SELECT COUNT(*) AS total FROM guild_raids WHERE guild_id=? AND status='active'",
                (guild_id,),
            )
            self.assertEqual((await cursor.fetchone())["total"], 1)
        finally:
            await other_db.close()

    async def test_raid_cooldown_uses_postgres_timestamp_arithmetic(self):
        guild_id = await create_guild(self.db, self.user_id, "Cooldown Crew")
        invite_id = await create_guild_invite(
            self.db, guild_id, self.user_id, self.member_id
        )
        await respond_guild_invite(self.db, invite_id, self.member_id, True)
        await start_guild_raid(
            self.db, guild_id, self.user_id, 10, "Root Warden", 1000
        )
        await attack_guild_raid(self.db, guild_id, self.member_id, 10)
        with self.assertRaisesRegex(GuildFeatureError, "cooldown"):
            await attack_guild_raid(self.db, guild_id, self.member_id, 10)


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class GroupPostgresIntegrationTests(unittest.IsolatedAsyncioTestCase):
    chat_id = -10_000_000_000_001
    owner_id = 5_000_000_000_000_101
    admin_id = 5_000_000_000_000_102
    target_id = 5_000_000_000_000_103

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        for table in (
            "group_bans", "group_raid_cooldowns", "group_raid_contributions",
            "group_raids", "group_missions", "group_players", "group_admins",
            "group_profiles", "players",
        ):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.execute(
            "CREATE TABLE players(user_id BIGINT PRIMARY KEY,coins BIGINT NOT NULL DEFAULT 0)"
        )
        await self.db.execute(
            "INSERT INTO players(user_id,coins) VALUES(?,0),(?,0),(?,0)",
            (self.owner_id, self.admin_id, self.target_id),
        )
        await self.db.commit()
        await init_group_tables(self.db)
        await register_group(self.db, self.chat_id, "Peak Raiders", self.owner_id)
        await set_group_admin(self.db, self.chat_id, self.admin_id, "admin")
        await record_group_player(self.db, self.chat_id, self.owner_id, "Ash", 10)
        await record_group_player(self.db, self.chat_id, self.admin_id, "Mira", 20)

    async def asyncTearDown(self):
        for table in (
            "group_bans", "group_raid_cooldowns", "group_raid_contributions",
            "group_raids", "group_missions", "group_players", "group_admins",
            "group_profiles", "players",
        ):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.commit()
        await self.db.close()

    async def test_group_profiles_roster_missions_and_rewards_support_bigint_ids(self):
        profile = await get_group_profile(self.db, self.chat_id)
        self.assertEqual(profile["owner_id"], self.owner_id)
        roster = await list_group_players(self.db, self.chat_id)
        self.assertEqual(roster[0]["user_id"], self.admin_id)

        first = await record_group_activity(self.db, self.chat_id, "battle", 10)
        second = await record_group_activity(self.db, self.chat_id, "battle", 10)
        self.assertTrue(next(row for row in first if row["id"] == "battles")["completed"])
        self.assertEqual(
            next(row for row in second if row["id"] == "battles")["progress"], 5
        )
        self.assertEqual(
            await claim_group_mission_reward(
                self.db, self.chat_id, self.admin_id, "battles"
            ),
            (120, 40),
        )
        cursor = await self.db.execute(
            "SELECT coins FROM players WHERE user_id=?", (self.admin_id,)
        )
        self.assertEqual((await cursor.fetchone())["coins"], 120)

    async def test_group_raid_generated_id_cooldown_and_contribution_upsert(self):
        raid_id = await start_group_raid(
            self.db, self.chat_id, self.admin_id, 10, "Root Warden", 1000
        )
        self.assertIsInstance(raid_id, int)
        await attack_group_raid(self.db, self.chat_id, self.owner_id, 10)
        with self.assertRaisesRegex(GroupError, "cooldown"):
            await attack_group_raid(self.db, self.chat_id, self.owner_id, 10)

        await self.db.execute(
            "UPDATE group_raid_cooldowns SET last_attack_at=CURRENT_TIMESTAMP-INTERVAL '10 seconds' WHERE raid_id=? AND user_id=?",
            (raid_id, self.owner_id),
        )
        await self.db.commit()
        await attack_group_raid(self.db, self.chat_id, self.owner_id, 15)
        cursor = await self.db.execute(
            "SELECT damage FROM group_raid_contributions WHERE raid_id=? AND user_id=?",
            (raid_id, self.owner_id),
        )
        self.assertEqual((await cursor.fetchone())["damage"], 25)

    async def test_concurrent_group_raid_starts_create_only_one_active_raid(self):
        other_db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            results = await asyncio.gather(
                start_group_raid(
                    self.db, self.chat_id, self.admin_id, 10, "Root Warden", 1000
                ),
                start_group_raid(
                    other_db, self.chat_id, self.owner_id, 10, "Ashen Warden", 1200
                ),
                return_exceptions=True,
            )
            self.assertEqual(sum(isinstance(result, int) for result in results), 1)
            self.assertEqual(sum(isinstance(result, GroupError) for result in results), 1)
            cursor = await self.db.execute(
                "SELECT COUNT(*) AS total FROM group_raids WHERE chat_id=? AND status='active'",
                (self.chat_id,),
            )
            self.assertEqual((await cursor.fetchone())["total"], 1)
        finally:
            await other_db.close()

    async def test_group_ban_upsert_and_unban(self):
        await set_group_ban(
            self.db, self.chat_id, self.admin_id, self.target_id, True, "spam"
        )
        await set_group_ban(
            self.db, self.chat_id, self.admin_id, self.target_id, True, "repeat spam"
        )
        self.assertTrue(await is_group_banned(self.db, self.chat_id, self.target_id))
        cursor = await self.db.execute(
            "SELECT actor_id,reason FROM group_bans WHERE chat_id=? AND user_id=?",
            (self.chat_id, self.target_id),
        )
        row = await cursor.fetchone()
        self.assertEqual((row["actor_id"], row["reason"]), (self.admin_id, "repeat spam"))
        await set_group_ban(
            self.db, self.chat_id, self.admin_id, self.target_id, False
        )
        self.assertFalse(await is_group_banned(self.db, self.chat_id, self.target_id))


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PartyPostgresIntegrationTests(unittest.IsolatedAsyncioTestCase):
    leader_id = 5_000_000_000_000_201
    member_id = 5_000_000_000_000_202

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        for table in (
            "party_battle_rewards", "party_battle_cooldowns",
            "party_battle_contributions", "party_battles",
            "party_invites", "party_members", "parties", "players",
        ):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY, username TEXT,
                 level INTEGER NOT NULL DEFAULT 1,
                 xp INTEGER NOT NULL DEFAULT 0,
                 coins BIGINT NOT NULL DEFAULT 0
               )"""
        )
        await self.db.execute(
            "INSERT INTO players(user_id,username,level) VALUES(?,?,4),(?,?,8)",
            (self.leader_id, "Ash", self.member_id, "Mira"),
        )
        await self.db.commit()
        await init_party_tables(self.db)

    async def asyncTearDown(self):
        for table in (
            "party_battle_rewards", "party_battle_cooldowns",
            "party_battle_contributions", "party_battles",
            "party_invites", "party_members", "parties", "players",
        ):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.commit()
        await self.db.close()

    async def test_party_battle_contributions_and_rewards_support_bigint_ids(self):
        party_id = await create_party(self.db, self.leader_id)
        invite_id = await invite_to_party(
            self.db, party_id, self.leader_id, self.member_id
        )
        await respond_to_party_invite(self.db, invite_id, self.member_id, True)
        party, members = await get_party_info(self.db, self.leader_id)
        self.assertEqual(party["member_count"], 2)
        self.assertEqual(
            {row["user_id"] for row in members},
            {self.leader_id, self.member_id},
        )

        battle_id = await start_party_battle(
            self.db, party_id, self.leader_id, 10, "Root Warden", 50
        )
        first = await attack_party_battle(self.db, party_id, self.leader_id, 10)
        self.assertEqual(first["hp"], 40)
        await self.db.execute(
            "UPDATE party_battle_cooldowns SET last_attack_at=CURRENT_TIMESTAMP-INTERVAL '10 seconds' WHERE battle_id=? AND user_id=?",
            (battle_id, self.leader_id),
        )
        await self.db.commit()
        result = await attack_party_battle(self.db, party_id, self.leader_id, 40)
        self.assertEqual(result["status"], "won")

        cursor = await self.db.execute(
            "SELECT damage FROM party_battle_contributions WHERE battle_id=? AND user_id=?",
            (battle_id, self.leader_id),
        )
        self.assertEqual((await cursor.fetchone())["damage"], 50)

        leader_reward = await reward_party_battle(
            self.db, battle_id, self.leader_id, 75, 100
        )
        member_reward = await reward_party_battle(
            self.db, battle_id, self.member_id, 75, 100
        )
        self.assertEqual(leader_reward["coins"], 75)
        self.assertEqual(member_reward["coins"], 75)
        with self.assertRaisesRegex(PartyError, "already claimed"):
            await reward_party_battle(
                self.db, battle_id, self.leader_id, 75, 100
            )
        cursor = await self.db.execute(
            "SELECT coins FROM players WHERE user_id=?", (self.leader_id,)
        )
        self.assertEqual((await cursor.fetchone())["coins"], 75)

    async def test_concurrent_invite_accepts_cannot_exceed_party_capacity(self):
        party_id = await create_party(self.db, self.leader_id)
        first_invite = await invite_to_party(
            self.db, party_id, self.leader_id, self.member_id
        )
        await respond_to_party_invite(self.db, first_invite, self.member_id, True)

        extra_member = self.member_id + 1
        first_target = self.member_id + 2
        second_target = self.member_id + 3
        await self.db.execute(
            "INSERT INTO party_members(user_id,party_id) VALUES(?,?)",
            (extra_member, party_id),
        )
        first_pending = await invite_to_party(
            self.db, party_id, self.leader_id, first_target
        )
        second_pending = await invite_to_party(
            self.db, party_id, self.leader_id, second_target
        )

        other_db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            results = await asyncio.gather(
                respond_to_party_invite(
                    self.db, first_pending, first_target, True
                ),
                respond_to_party_invite(
                    other_db, second_pending, second_target, True
                ),
                return_exceptions=True,
            )
            self.assertEqual(sum(result is None for result in results), 1)
            self.assertEqual(sum(isinstance(result, PartyError) for result in results), 1)
            cursor = await self.db.execute(
                "SELECT COUNT(*) AS total FROM party_members WHERE party_id=?",
                (party_id,),
            )
            self.assertEqual((await cursor.fetchone())["total"], 4)
        finally:
            await other_db.close()

    async def test_party_attack_cooldown_uses_postgres_timestamps(self):
        party_id = await create_party(self.db, self.leader_id)
        await start_party_battle(
            self.db, party_id, self.leader_id, 10, "Root Warden", 1000
        )
        await attack_party_battle(self.db, party_id, self.leader_id, 10)
        with self.assertRaisesRegex(PartyError, "cooldown"):
            await attack_party_battle(self.db, party_id, self.leader_id, 10)

    async def test_leader_departure_transfers_party_leadership(self):
        party_id = await create_party(self.db, self.leader_id)
        invite_id = await invite_to_party(
            self.db, party_id, self.leader_id, self.member_id
        )
        await respond_to_party_invite(self.db, invite_id, self.member_id, True)
        self.assertEqual(await leave_party(self.db, self.leader_id), self.member_id)
        party, members = await get_party_info(self.db, self.member_id)
        self.assertEqual(party["leader_id"], self.member_id)
        self.assertEqual([row["user_id"] for row in members], [self.member_id])


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class AccountPostgresIntegrationTests(unittest.IsolatedAsyncioTestCase):
    user_id = 5_000_000_000_000_301
    bidder_id = 5_000_000_000_000_302

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        tables = (
            "player_settings", "guild_chat_messages", "guild_war_duel_events",
            "duels", "auction_listings", "auction_stash", "trades",
            "premium_wallets", "guild_members", "group_profiles", "group_admins",
            "group_players", "group_missions", "group_raids", "group_bans",
            "guild_invites", "guild_announcements", "guild_raid_contributions",
            "guild_raid_cooldowns", "friend_requests", "party_invites",
            "party_battle_contributions", "party_battle_cooldowns",
            "party_battle_rewards", "party_members", "parties", "party_battles",
            "group_raid_contributions", "group_raid_cooldowns", "battles",
            "daily_claims", "boss_defeats", "monster_discoveries",
            "quest_progress", "achievement_progress", "character_appearance",
            "dungeon_runs", "dungeon_rewards", "player_materials",
            "crafted_items", "player_worlds", "player_presence",
            "world_discoveries", "player_story", "story_flags",
            "story_reward_claims", "players",
        )
        for table in tables:
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY, username TEXT,
                 level INTEGER NOT NULL DEFAULT 1,
                 xp INTEGER NOT NULL DEFAULT 0,
                 coins BIGINT NOT NULL DEFAULT 0
               )"""
        )
        await self.db.execute(
            "INSERT INTO players(user_id,username,level,coins) VALUES(?,?,10,0),(?,?,5,100)",
            (self.user_id, "Ash", self.bidder_id, "Mira"),
        )
        statements = (
            "CREATE TABLE guild_members(user_id BIGINT,guild_id BIGINT,role TEXT,joined_at TEXT)",
            "CREATE TABLE group_profiles(chat_id BIGINT,owner_id BIGINT)",
            "CREATE TABLE group_admins(chat_id BIGINT,user_id BIGINT,role TEXT)",
            "CREATE TABLE group_players(chat_id BIGINT,user_id BIGINT)",
            "CREATE TABLE group_missions(chat_id BIGINT,mission_id TEXT)",
            "CREATE TABLE group_raids(raid_id BIGINT,chat_id BIGINT)",
            "CREATE TABLE group_bans(chat_id BIGINT,user_id BIGINT,actor_id BIGINT)",
            "CREATE TABLE guild_invites(guild_id BIGINT,inviter_id BIGINT,target_id BIGINT)",
            "CREATE TABLE guild_announcements(guild_id BIGINT,author_id BIGINT)",
            "CREATE TABLE guild_raid_contributions(raid_id BIGINT,user_id BIGINT)",
            "CREATE TABLE guild_raid_cooldowns(raid_id BIGINT,user_id BIGINT)",
            "CREATE TABLE friend_requests(user_low BIGINT,user_high BIGINT)",
            "CREATE TABLE party_invites(inviter_id BIGINT,target_id BIGINT)",
            "CREATE TABLE party_battle_contributions(battle_id BIGINT,user_id BIGINT)",
            "CREATE TABLE party_battle_cooldowns(battle_id BIGINT,user_id BIGINT)",
            "CREATE TABLE party_battle_rewards(battle_id BIGINT,user_id BIGINT)",
            "CREATE TABLE party_members(user_id BIGINT,party_id BIGINT)",
            "CREATE TABLE parties(party_id BIGINT,leader_id BIGINT)",
            "CREATE TABLE party_battles(battle_id BIGINT,party_id BIGINT)",
            "CREATE TABLE group_raid_contributions(raid_id BIGINT,user_id BIGINT)",
            "CREATE TABLE group_raid_cooldowns(raid_id BIGINT,user_id BIGINT)",
            "CREATE TABLE guild_chat_messages(guild_id BIGINT,user_id BIGINT,message TEXT)",
            "CREATE TABLE guild_war_duel_events(duel_id BIGINT,war_id BIGINT,winner_id BIGINT)",
            "CREATE TABLE duels(duel_id BIGINT,challenger_id BIGINT,opponent_id BIGINT)",
            "CREATE TABLE auction_listings(listing_id BIGINT,seller_id BIGINT,current_bid BIGINT,highest_bidder BIGINT,status TEXT)",
            "CREATE TABLE auction_stash(stash_id BIGINT,user_id BIGINT)",
            "CREATE TABLE trades(initiator_id BIGINT,partner_id BIGINT)",
            "CREATE TABLE premium_wallets(user_id BIGINT,balance BIGINT)",
        )
        for statement in statements:
            await self.db.execute(statement)
        generic_user_tables = (
            "battles", "daily_claims", "boss_defeats", "monster_discoveries",
            "quest_progress", "achievement_progress", "character_appearance",
            "dungeon_runs", "dungeon_rewards", "player_materials",
            "crafted_items", "player_worlds", "player_presence",
            "world_discoveries", "player_story", "story_flags",
            "story_reward_claims",
        )
        for table in generic_user_tables:
            await self.db.execute(
                f"CREATE TABLE {table}(user_id BIGINT)"
            )
        await self.db.commit()
        await init_account_tables(self.db)

    async def asyncTearDown(self):
        tables = (
            "player_settings", "guild_chat_messages", "guild_war_duel_events",
            "duels", "auction_listings", "auction_stash", "trades",
            "premium_wallets", "guild_members", "group_profiles", "group_admins",
            "group_players", "group_missions", "group_raids", "group_bans",
            "guild_invites", "guild_announcements", "guild_raid_contributions",
            "guild_raid_cooldowns", "friend_requests", "party_invites",
            "party_battle_contributions", "party_battle_cooldowns",
            "party_battle_rewards", "party_members", "parties", "party_battles",
            "group_raid_contributions", "group_raid_cooldowns", "battles",
            "daily_claims", "boss_defeats", "monster_discoveries",
            "quest_progress", "achievement_progress", "character_appearance",
            "dungeon_runs", "dungeon_rewards", "player_materials",
            "crafted_items", "player_worlds", "player_presence",
            "world_discoveries", "player_story", "story_flags",
            "story_reward_claims", "players",
        )
        for table in tables:
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.commit()
        await self.db.close()

    async def test_database_rate_limit_is_shared_across_postgres_connections(self):
        other_db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        limiter = DatabaseSlidingWindowRateLimiter(window_seconds=10)
        try:
            await limiter.init(self.db)
            await limiter.init(other_db)
            results = await asyncio.gather(
                limiter.allow(self.db, "shared-player-key", 1, now=500),
                limiter.allow(other_db, "shared-player-key", 1, now=500),
            )
            self.assertEqual(sum(allowed for allowed, _ in results), 1)
        finally:
            await other_db.close()
            await self.db.execute("DROP TABLE IF EXISTS api_rate_limit_events")
            await self.db.commit()

    async def test_settings_use_bigint_ids_and_postgres_catalog_migration(self):
        self.assertEqual(
            await get_settings(self.db, self.user_id),
            {
                "notifications_enabled": 1,
                "profile_visibility": "public",
                "sound_enabled": 1,
            },
        )
        updated = await update_settings(
            self.db, self.user_id, notifications_enabled=False,
            profile_visibility="friends", sound_enabled=False,
        )
        self.assertEqual(
            updated,
            {
                "notifications_enabled": 0,
                "profile_visibility": "friends",
                "sound_enabled": 0,
            },
        )

        await self.db.execute("DROP TABLE player_settings")
        await self.db.execute(
            """CREATE TABLE player_settings(
                 user_id BIGINT PRIMARY KEY,
                 notifications_enabled INTEGER NOT NULL DEFAULT 1,
                 profile_visibility TEXT NOT NULL DEFAULT 'public',
                 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        await self.db.commit()
        await init_account_tables(self.db)
        cursor = await self.db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='player_settings'"
        )
        columns = {row["column_name"] for row in await cursor.fetchall()}
        self.assertIn("sound_enabled", columns)

    async def test_concurrent_partial_settings_updates_preserve_both_changes(self):
        other_db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            results = await asyncio.gather(
                update_settings(self.db, self.user_id, notifications_enabled=False),
                update_settings(other_db, self.user_id, sound_enabled=False),
            )
            self.assertEqual(len(results), 2)
            self.assertEqual(
                await get_settings(self.db, self.user_id),
                {
                    "notifications_enabled": 0,
                    "profile_visibility": "public",
                    "sound_enabled": 0,
                },
            )
        finally:
            await other_db.close()

    async def test_account_deletion_uses_postgres_catalog_and_cleans_optional_data(self):
        await self.db.execute(
            "INSERT INTO guild_chat_messages VALUES(5,?,'private guild text')",
            (self.user_id,),
        )
        await self.db.execute(
            "INSERT INTO duels VALUES(101,?,?)", (self.user_id, self.bidder_id)
        )
        await self.db.execute(
            "INSERT INTO guild_war_duel_events VALUES(101,50,?)", (self.bidder_id,)
        )
        await self.db.execute(
            "INSERT INTO auction_listings VALUES(1,?,75,?,'active')",
            (self.user_id, self.bidder_id),
        )
        await self.db.execute(
            "INSERT INTO auction_stash VALUES(1,?)", (self.user_id,)
        )
        await self.db.execute(
            "INSERT INTO trades VALUES(?,?)", (self.user_id, self.bidder_id)
        )
        await self.db.execute(
            "INSERT INTO premium_wallets VALUES(?,500)", (self.user_id,)
        )
        await self.db.commit()

        self.assertTrue(await delete_player_account(self.db, self.user_id))

        cursor = await self.db.execute(
            "SELECT 1 FROM players WHERE user_id=?", (self.user_id,)
        )
        self.assertIsNone(await cursor.fetchone())
        cursor = await self.db.execute(
            "SELECT coins FROM players WHERE user_id=?", (self.bidder_id,)
        )
        self.assertEqual((await cursor.fetchone())["coins"], 175)
        for table in (
            "guild_chat_messages", "guild_war_duel_events", "duels",
            "auction_stash", "trades", "premium_wallets",
        ):
            cursor = await self.db.execute(f"SELECT COUNT(*) AS total FROM {table}")
            self.assertEqual((await cursor.fetchone())["total"], 0, table)
        cursor = await self.db.execute(
            "SELECT status FROM auction_listings WHERE listing_id=1"
        )
        self.assertEqual((await cursor.fetchone())["status"], "cancelled")

    async def test_account_deletion_preserves_outer_transaction(self):
        await self.db.execute("BEGIN IMMEDIATE")
        await delete_player_account(self.db, self.user_id)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT 1 FROM players WHERE user_id=?", (self.user_id,)
        )
        self.assertIsNotNone(await cursor.fetchone())


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class AuctionPostgresIntegrationTests(unittest.IsolatedAsyncioTestCase):
    seller_id = 5_000_000_000_000_401
    buyer_id = 5_000_000_000_000_402

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        for table in ("auction_stash", "auction_listings", "battles", "players"):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.execute(
            """CREATE TABLE players(
                 user_id BIGINT PRIMARY KEY, coins BIGINT NOT NULL,
                 weapon TEXT NOT NULL, weapon_attack INTEGER NOT NULL,
                 armor TEXT NOT NULL, armor_defense INTEGER NOT NULL
               )"""
        )
        await self.db.execute(
            """INSERT INTO players VALUES
               (?,?, 'Stormblade',25,'Traveler Clothes',0),
               (?,?,'Rusty Sword',0,'Dragon Mail',40),
               (?,?,'Oak Bow',12,'Traveler Clothes',0)""",
            (self.seller_id, 100, self.buyer_id, 1000, self.buyer_id + 1, 1000),
        )
        await self.db.execute("CREATE TABLE battles(user_id BIGINT PRIMARY KEY)")
        await self.db.commit()
        await init_auction_tables(self.db)

    async def asyncTearDown(self):
        for table in ("auction_stash", "auction_listings", "battles", "players"):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.commit()
        await self.db.close()

    async def test_listing_bidding_expiry_and_stash_use_bigint_ids(self):
        listing_id = await create_listing(
            self.db, self.seller_id, "weapon", 100, 1, now=1000
        )
        self.assertIsInstance(listing_id, int)
        await place_bid(self.db, self.buyer_id, listing_id, 100, now=1001)
        await list_active_auctions(self.db, now=4601)

        cursor = await self.db.execute(
            "SELECT coins,weapon,weapon_attack FROM players WHERE user_id=?",
            (self.seller_id,),
        )
        seller = await cursor.fetchone()
        self.assertEqual((seller["coins"], seller["weapon"], seller["weapon_attack"]), (200, "Rusty Sword", 0))
        cursor = await self.db.execute(
            "SELECT coins,weapon,weapon_attack FROM players WHERE user_id=?",
            (self.buyer_id,),
        )
        buyer = await cursor.fetchone()
        self.assertEqual((buyer["coins"], buyer["weapon"], buyer["weapon_attack"]), (900, "Stormblade", 25))

        stash = await list_stash(self.db, self.buyer_id)
        self.assertEqual(len(stash), 1)
        self.assertEqual((stash[0]["item_name"], stash[0]["item_stat"]), ("Rusty Sword", 0))
        self.assertGreater(stash[0]["stash_id"], 0)
        equipped = await equip_stashed_item(self.db, self.buyer_id, stash[0]["stash_id"])
        self.assertEqual(equipped, ("Rusty Sword", "weapon", 0))
        cursor = await self.db.execute(
            "SELECT weapon,weapon_attack FROM players WHERE user_id=?",
            (self.buyer_id,),
        )
        row = await cursor.fetchone()
        self.assertEqual((row["weapon"], row["weapon_attack"]), ("Rusty Sword", 0))

    async def test_buyer_in_active_battle_receives_item_in_stash(self):
        listing_id = await create_listing(
            self.db, self.seller_id, "weapon", 100, 1, now=1000
        )
        await place_bid(self.db, self.buyer_id, listing_id, 100, now=1001)
        await self.db.execute("INSERT INTO battles(user_id) VALUES(?)", (self.buyer_id,))
        await self.db.commit()
        await list_active_auctions(self.db, now=4601)

        cursor = await self.db.execute(
            "SELECT weapon,weapon_attack FROM players WHERE user_id=?",
            (self.buyer_id,),
        )
        row = await cursor.fetchone()
        self.assertEqual((row["weapon"], row["weapon_attack"]), ("Rusty Sword", 0))
        stash = await list_stash(self.db, self.buyer_id)
        self.assertEqual([(row["item_name"], row["item_stat"]) for row in stash], [("Stormblade", 25)])

    async def test_no_bid_expiry_returns_item_without_overwriting_new_gear(self):
        listing_id = await create_listing(
            self.db, self.seller_id, "weapon", 100, 1, now=1000
        )
        await self.db.execute(
            "UPDATE players SET weapon='New Blade',weapon_attack=12 WHERE user_id=?",
            (self.seller_id,),
        )
        await self.db.commit()
        await list_active_auctions(self.db, now=4601)

        cursor = await self.db.execute(
            "SELECT weapon,weapon_attack FROM players WHERE user_id=?",
            (self.seller_id,),
        )
        row = await cursor.fetchone()
        self.assertEqual((row["weapon"], row["weapon_attack"]), ("Stormblade", 25))
        stash = await list_stash(self.db, self.seller_id)
        self.assertEqual([(row["item_name"], row["item_stat"]) for row in stash], [("New Blade", 12)])

    async def test_missing_buyer_cannot_trigger_seller_payout(self):
        listing_id = await create_listing(
            self.db, self.seller_id, "weapon", 100, 1, now=1000
        )
        await place_bid(self.db, self.buyer_id, listing_id, 100, now=1001)
        await self.db.execute("DELETE FROM players WHERE user_id=?", (self.buyer_id,))
        await self.db.commit()
        await list_active_auctions(self.db, now=4601)

        cursor = await self.db.execute(
            "SELECT coins FROM players WHERE user_id=?", (self.seller_id,)
        )
        self.assertEqual((await cursor.fetchone())["coins"], 100)
        cursor = await self.db.execute(
            "SELECT status FROM auction_listings WHERE listing_id=?", (listing_id,)
        )
        self.assertEqual((await cursor.fetchone())["status"], "expired")

    async def test_concurrent_bids_serialize_on_the_listing_row(self):
        listing_id = await create_listing(
            self.db, self.seller_id, "weapon", 100, 1, now=1000
        )
        second_db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        try:
            outcomes = await asyncio.gather(
                place_bid(self.db, self.buyer_id, listing_id, 100, now=1001),
                place_bid(second_db, self.buyer_id + 1, listing_id, 110, now=1001),
                return_exceptions=True,
            )
            accepted = [value for value in outcomes if not isinstance(value, Exception)]
            rejected = [value for value in outcomes if isinstance(value, AuctionError)]
            self.assertGreaterEqual(len(accepted), 1)
            self.assertEqual(len(accepted) + len(rejected), 2)
            cursor = await self.db.execute(
                "SELECT current_bid,highest_bidder FROM auction_listings WHERE listing_id=?",
                (listing_id,),
            )
            listing = await cursor.fetchone()
            self.assertIn(listing["current_bid"], (100, 110))
            self.assertIn(listing["highest_bidder"], (self.buyer_id, self.buyer_id + 1))
            cursor = await self.db.execute(
                "SELECT coins FROM players WHERE user_id=?", (self.buyer_id,)
            )
            buyer_balance = (await cursor.fetchone())["coins"]
            self.assertEqual(
                buyer_balance + (listing["current_bid"] if listing["highest_bidder"] == self.buyer_id else 0),
                1000,
            )
        finally:
            await second_db.close()

    async def test_missing_seller_refunds_existing_buyer(self):
        listing_id = await create_listing(
            self.db, self.seller_id, "weapon", 100, 1, now=1000
        )
        await place_bid(self.db, self.buyer_id, listing_id, 100, now=1001)
        await self.db.execute("DELETE FROM players WHERE user_id=?", (self.seller_id,))
        await self.db.commit()
        await list_active_auctions(self.db, now=4601)

        cursor = await self.db.execute(
            "SELECT coins FROM players WHERE user_id=?", (self.buyer_id,)
        )
        self.assertEqual((await cursor.fetchone())["coins"], 1000)
        cursor = await self.db.execute(
            "SELECT status FROM auction_listings WHERE listing_id=?", (listing_id,)
        )
        self.assertEqual((await cursor.fetchone())["status"], "expired")


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PremiumPostgresIntegrationTests(unittest.IsolatedAsyncioTestCase):
    user_id = 5_000_000_000_000_501

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        for table in (
            "premium_shop_purchases", "player_xp_boosts",
            "premium_transactions", "premium_wallets",
            "player_stamina", "players",
        ):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.execute(
            "CREATE TABLE players(user_id BIGINT PRIMARY KEY,potions INTEGER NOT NULL DEFAULT 0)"
        )
        await self.db.execute(
            "CREATE TABLE player_stamina(user_id BIGINT PRIMARY KEY,stamina INTEGER NOT NULL,updated_at BIGINT NOT NULL)"
        )
        await self.db.execute(
            "INSERT INTO players(user_id,potions) VALUES(?,2)",
            (self.user_id,),
        )
        await self.db.execute(
            "INSERT INTO player_stamina(user_id,stamina,updated_at) VALUES(?,30,?)",
            (self.user_id, int(time.time())),
        )
        await self.db.commit()
        await init_premium_tables(self.db)

    async def asyncTearDown(self):
        for table in (
            "premium_shop_purchases", "player_xp_boosts",
            "premium_transactions", "premium_wallets",
            "player_stamina", "players",
        ):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.commit()
        await self.db.close()

    async def test_stars_ledger_is_idempotent_with_bigint_player_ids(self):
        package = get_premium_packages()["crest"]
        first = await credit_premium_purchase(
            self.db, self.user_id, "crest", package["stars"], "pg-charge-001"
        )
        second = await credit_premium_purchase(
            self.db, self.user_id, "crest", package["stars"], "pg-charge-001"
        )
        self.assertTrue(first["credited"])
        self.assertFalse(second["credited"])
        self.assertEqual(first["gems"], package["gems"])
        self.assertEqual(await get_premium_balance(self.db, self.user_id), 120)

        cursor = await self.db.execute(
            "SELECT transaction_id,user_id,telegram_charge_id FROM premium_transactions"
        )
        row = await cursor.fetchone()
        self.assertGreater(row["transaction_id"], 0)
        self.assertEqual((row["user_id"], row["telegram_charge_id"]), (self.user_id, "pg-charge-001"))
        await self.db.execute(
            "INSERT INTO players(user_id,potions) VALUES(?,0)", (self.user_id + 1,)
        )
        await self.db.commit()
        with self.assertRaisesRegex(PremiumError, "different purchase"):
            await credit_premium_purchase(
                self.db, self.user_id + 1, "crest", package["stars"], "pg-charge-001"
            )

    async def test_shop_items_apply_effects_and_xp_boosts(self):
        for package_id in ("crest", "spark"):
            package = get_premium_packages()[package_id]
            await credit_premium_purchase(
                self.db, self.user_id, package_id, package["stars"],
                f"pg-charge-{package_id}",
            )

        potion = await buy_premium_item(self.db, self.user_id, "potion_bundle")
        stamina = await buy_premium_item(self.db, self.user_id, "stamina_crystal")
        charm = await buy_premium_item(self.db, self.user_id, "xp_charm")
        self.assertEqual((potion["balance"], stamina["balance"], charm["balance"]), (130, 105, 45))

        cursor = await self.db.execute(
            "SELECT potions FROM players WHERE user_id=?", (self.user_id,)
        )
        self.assertEqual((await cursor.fetchone())["potions"], 7)
        cursor = await self.db.execute(
            "SELECT stamina FROM player_stamina WHERE user_id=?", (self.user_id,)
        )
        self.assertEqual((await cursor.fetchone())["stamina"], 80)

        self.assertTrue(await consume_xp_boost(self.db, self.user_id))
        self.assertTrue(await consume_xp_boost(self.db, self.user_id))
        self.assertTrue(await consume_xp_boost(self.db, self.user_id))
        self.assertFalse(await consume_xp_boost(self.db, self.user_id))
        await self.db.commit()

        cursor = await self.db.execute(
            "SELECT purchase_id,user_id,item_id FROM premium_shop_purchases ORDER BY purchase_id"
        )
        purchases = await cursor.fetchall()
        self.assertEqual(len(purchases), 3)
        self.assertTrue(all(row["purchase_id"] > 0 and row["user_id"] == self.user_id for row in purchases))

    async def test_failed_shop_log_rolls_back_item_effect_and_wallet_debit(self):
        package = get_premium_packages()["crest"]
        await credit_premium_purchase(
            self.db, self.user_id, "crest", package["stars"], "pg-charge-rollback"
        )
        await self.db.execute(
            """CREATE FUNCTION reject_premium_purchase_log() RETURNS trigger AS $$
               BEGIN RAISE EXCEPTION 'purchase log unavailable'; END;
               $$ LANGUAGE plpgsql"""
        )
        await self.db.execute(
            """CREATE TRIGGER reject_premium_purchase_log
               BEFORE INSERT ON premium_shop_purchases
               FOR EACH ROW EXECUTE FUNCTION reject_premium_purchase_log()"""
        )
        await self.db.commit()

        with self.assertRaises(Exception):
            await buy_premium_item(self.db, self.user_id, "potion_bundle")
        cursor = await self.db.execute(
            "SELECT potions FROM players WHERE user_id=?", (self.user_id,)
        )
        self.assertEqual((await cursor.fetchone())["potions"], 2)
        self.assertEqual(await get_premium_balance(self.db, self.user_id), 120)
        cursor = await self.db.execute("SELECT COUNT(*) AS total FROM premium_shop_purchases")
        self.assertEqual((await cursor.fetchone())["total"], 0)

    async def test_premium_schema_initialization_preserves_outer_transaction(self):
        await self.db.execute("DROP TABLE premium_shop_purchases")
        await self.db.commit()
        await self.db.execute("UPDATE players SET potions=potions+1 WHERE user_id=?", (self.user_id,))
        await init_premium_tables(self.db)
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT potions FROM players WHERE user_id=?", (self.user_id,)
        )
        self.assertEqual((await cursor.fetchone())["potions"], 2)
        cursor = await self.db.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=current_schema() AND table_name='premium_shop_purchases'"
        )
        self.assertIsNone(await cursor.fetchone())


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class CharacterAppearancePostgresIntegrationTests(unittest.IsolatedAsyncioTestCase):
    user_id = 5_000_000_000_000_601

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        await self.db.execute("DROP TABLE IF EXISTS character_appearance CASCADE")
        await self.db.commit()
        await init_character_tables(self.db)

    async def asyncTearDown(self):
        await self.db.execute("DROP TABLE IF EXISTS character_appearance CASCADE")
        await self.db.commit()
        await self.db.close()

    async def test_appearance_persists_with_bigint_telegram_user_id(self):
        defaults = await get_appearance(self.db, self.user_id)
        self.assertEqual(defaults["race"], "Human")
        saved = await save_appearance(
            self.db,
            self.user_id,
            {"race": "Elf", "skin": "deep", "hair": "braided",
             "outfit": "ranger", "face": "scarred", "body": "broad"},
        )
        self.assertEqual(await get_appearance(self.db, self.user_id), saved)
        cursor = await self.db.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='character_appearance' "
            "AND column_name='user_id'"
        )
        self.assertEqual((await cursor.fetchone())["data_type"], "bigint")

    async def test_legacy_postgres_appearance_schema_is_migrated(self):
        await self.db.execute("DROP TABLE character_appearance")
        await self.db.execute(
            """CREATE TABLE character_appearance(
                 user_id INTEGER PRIMARY KEY,
                 race TEXT NOT NULL DEFAULT 'Human',
                 skin TEXT NOT NULL DEFAULT 'warm',
                 hair TEXT NOT NULL DEFAULT 'short',
                 outfit TEXT NOT NULL DEFAULT 'traveler',
                 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        legacy_user_id = 601
        await self.db.execute(
            "INSERT INTO character_appearance(user_id) VALUES(?)", (legacy_user_id,)
        )
        await self.db.commit()
        await init_character_tables(self.db)
        appearance = await get_appearance(self.db, legacy_user_id)
        self.assertEqual((appearance["face"], appearance["body"]), ("soft", "balanced"))
        cursor = await self.db.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='character_appearance' "
            "AND column_name='user_id'"
        )
        self.assertEqual((await cursor.fetchone())["data_type"], "bigint")

    async def test_save_appearance_preserves_outer_transaction(self):
        await self.db.execute("BEGIN")
        await save_appearance(self.db, self.user_id, {"race": "Orc"})
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT 1 FROM character_appearance WHERE user_id=?", (self.user_id,)
        )
        self.assertIsNone(await cursor.fetchone())


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class AdminToolsPostgresIntegrationTests(unittest.IsolatedAsyncioTestCase):
    actor_id = 5_000_000_000_000_701
    user_id = 5_000_000_000_000_702

    async def asyncSetUp(self):
        self.db = await PostgresConnection.connect(os.environ["TEST_POSTGRES_URL"])
        for table in ("admin_audit_log", "security_events", "duels",
                      "group_profiles", "guilds", "battles", "players"):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.execute(
            "CREATE TABLE players(user_id BIGINT PRIMARY KEY,coins BIGINT NOT NULL DEFAULT 0)"
        )
        await self.db.execute(
            "CREATE TABLE battles(user_id BIGINT PRIMARY KEY)"
        )
        await self.db.execute(
            "CREATE TABLE guilds(guild_id BIGINT PRIMARY KEY)"
        )
        await self.db.execute(
            "CREATE TABLE group_profiles(chat_id BIGINT PRIMARY KEY)"
        )
        await self.db.execute(
            """CREATE TABLE duels(
                 duel_id BIGINT PRIMARY KEY,challenger_id BIGINT,
                 opponent_id BIGINT,status TEXT
               )"""
        )
        await self.db.execute(
            "INSERT INTO players(user_id,coins) VALUES(?,500)",
            (self.user_id,),
        )
        await self.db.commit()
        await init_admin_tables(self.db)

    async def asyncTearDown(self):
        for table in ("admin_audit_log", "security_events", "duels",
                      "group_profiles", "guilds", "battles", "players"):
            await self.db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        await self.db.commit()
        await self.db.close()

    async def test_audit_log_and_coin_adjustment_support_bigint_ids(self):
        balance = await adjust_player_coins(
            self.db, self.user_id, 75, self.actor_id
        )
        self.assertEqual(balance, 575)
        await record_admin_action(
            self.db, self.actor_id, "player_review", self.user_id, "verified"
        )
        logs = await recent_admin_actions(self.db)
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["actor_id"], self.actor_id)
        self.assertEqual(logs[0]["target_id"], self.user_id)
        self.assertGreater(logs[0]["log_id"], 0)

    async def test_dashboard_uses_postgres_catalog_and_interval_queries(self):
        stats = await dashboard_stats(self.db)
        self.assertEqual(stats["players"], 1)
        self.assertEqual(stats["security_events_24h"], 0)
        self.assertEqual(stats["stars_received"], 0)
        self.assertEqual(stats["premium_gems_issued"], 0)

        await self.db.execute(
            """CREATE TABLE security_events(
                 event_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        await self.db.execute(
            "INSERT INTO security_events(created_at) VALUES(CURRENT_TIMESTAMP-INTERVAL '1 hour')"
        )
        await self.db.commit()
        stats = await dashboard_stats(self.db)
        self.assertEqual(stats["security_events_24h"], 1)

    async def test_admin_mutation_preserves_caller_owned_transaction(self):
        await self.db.execute("BEGIN")
        self.assertEqual(
            await adjust_player_coins(self.db, self.user_id, 25, self.actor_id),
            525,
        )
        self.assertTrue(self.db.in_transaction)
        await self.db.rollback()
        cursor = await self.db.execute(
            "SELECT coins FROM players WHERE user_id=?", (self.user_id,)
        )
        self.assertEqual((await cursor.fetchone())["coins"], 500)
        self.assertEqual(await recent_admin_actions(self.db), [])
