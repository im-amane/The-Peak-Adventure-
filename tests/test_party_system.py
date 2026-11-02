import asyncio
import unittest

import aiosqlite

from stamina_system import consume_stamina, get_stamina, init_stamina_tables

from party_system import (
    PartyError,
    create_party,
    disband_party,
    get_party_info,
    init_party_tables,
    invite_to_party,
    leave_party,
    list_pending_party_invites,
    respond_to_party_invite,
    start_party_battle, attack_party_battle, get_party_battle, reward_party_battle,
)


class PartySystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript("""
        CREATE TABLE players (
          user_id INTEGER PRIMARY KEY, username TEXT, level INTEGER NOT NULL DEFAULT 1,
          xp INTEGER NOT NULL DEFAULT 0, coins INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO players(user_id,username,level) VALUES
          (101,'Ash',4),(202,'Mira',8),(303,'Rook',2),(404,'Vale',5),(505,'Nyx',3);
        """)
        await init_party_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_party_creation_and_invite_acceptance(self):
        party_id = await create_party(self.db, 101)
        invite_id = await invite_to_party(self.db, party_id, 101, 202)
        await respond_to_party_invite(self.db, invite_id, 202, True)
        party, members = await get_party_info(self.db, 101)
        self.assertEqual(party["member_count"], 2)
        self.assertEqual({member["user_id"] for member in members}, {101, 202})

    async def test_player_cannot_create_or_join_two_parties(self):
        await create_party(self.db, 101)
        with self.assertRaisesRegex(PartyError, "already in a party"):
            await create_party(self.db, 101)

    async def test_only_leader_can_invite(self):
        party_id = await create_party(self.db, 101)
        invite_id = await invite_to_party(self.db, party_id, 101, 202)
        await respond_to_party_invite(self.db, invite_id, 202, True)
        with self.assertRaisesRegex(PartyError, "Only the party leader"):
            await invite_to_party(self.db, party_id, 202, 303)

    async def test_invite_cannot_be_accepted_by_another_player(self):
        party_id = await create_party(self.db, 101)
        invite_id = await invite_to_party(self.db, party_id, 101, 202)
        with self.assertRaisesRegex(PartyError, "Only the invited player"):
            await respond_to_party_invite(self.db, invite_id, 303, True)

    async def test_pending_invite_is_unique_per_target(self):
        party_a = await create_party(self.db, 101)
        party_b = await create_party(self.db, 303)
        await invite_to_party(self.db, party_a, 101, 202)
        with self.assertRaisesRegex(PartyError, "pending party invitation"):
            await invite_to_party(self.db, party_b, 303, 202)

    async def test_pending_party_invites_are_private_to_target(self):
        party_id = await create_party(self.db, 101)
        invite_id = await invite_to_party(self.db, party_id, 101, 202)
        incoming = await list_pending_party_invites(self.db, 202)
        self.assertEqual([row["invite_id"] for row in incoming], [invite_id])
        self.assertEqual(await list_pending_party_invites(self.db, 101), [])

    async def test_party_capacity_is_four(self):
        party_id = await create_party(self.db, 101)
        for target in (202, 303, 404):
            invite_id = await invite_to_party(self.db, party_id, 101, target)
            await respond_to_party_invite(self.db, invite_id, target, True)
        with self.assertRaisesRegex(PartyError, "at most 4"):
            await invite_to_party(self.db, party_id, 101, 505)

    async def test_leader_leaving_transfers_leadership(self):
        party_id = await create_party(self.db, 101)
        invite_id = await invite_to_party(self.db, party_id, 101, 202)
        await respond_to_party_invite(self.db, invite_id, 202, True)
        new_leader = await leave_party(self.db, 101)
        self.assertEqual(new_leader, 202)
        party, members = await get_party_info(self.db, 202)
        self.assertEqual(party["leader_id"], 202)
        self.assertEqual([member["user_id"] for member in members], [202])

    async def test_last_member_leaving_deletes_party(self):
        party_id = await create_party(self.db, 101)
        await leave_party(self.db, 101)
        with self.assertRaisesRegex(PartyError, "not in a party"):
            await get_party_info(self.db, 101)
        with self.assertRaisesRegex(PartyError, "not found"):
            await disband_party(self.db, party_id, 101)

    async def test_only_leader_can_disband(self):
        party_id = await create_party(self.db, 101)
        invite_id = await invite_to_party(self.db, party_id, 101, 202)
        await respond_to_party_invite(self.db, invite_id, 202, True)
        with self.assertRaisesRegex(PartyError, "Only the party leader"):
            await disband_party(self.db, party_id, 202)

    async def test_declined_invite_cannot_be_reused(self):
        party_id = await create_party(self.db, 101)
        invite_id = await invite_to_party(self.db, party_id, 101, 202)
        await respond_to_party_invite(self.db, invite_id, 202, False)
        with self.assertRaisesRegex(PartyError, "no longer active"):
            await respond_to_party_invite(self.db, invite_id, 202, True)



    async def test_party_leader_can_start_coop_battle(self):
        party_id=await create_party(self.db,101)
        battle_id=await start_party_battle(self.db,party_id,101,10,"Root Warden",100)
        self.assertGreater(battle_id,0)

    async def test_only_party_leader_can_start_coop_battle(self):
        party_id=await create_party(self.db,101)
        invite=await invite_to_party(self.db,party_id,101,202)
        await respond_to_party_invite(self.db,invite,202,True)
        with self.assertRaises(PartyError):
            await start_party_battle(self.db,party_id,202,10,"Root Warden",100)

    async def test_party_cannot_start_second_active_coop_battle(self):
        party_id = await create_party(self.db, 101)
        await start_party_battle(self.db, party_id, 101, 10, "Root Warden", 100)
        with self.assertRaisesRegex(PartyError, "already has an active"):
            await start_party_battle(self.db, party_id, 101, 11, "Ash Sentinel", 120)

    async def test_invalid_coop_monster_name_is_rejected(self):
        party_id = await create_party(self.db, 101)
        with self.assertRaisesRegex(PartyError, "monster name"):
            await start_party_battle(self.db, party_id, 101, 10, "   ", 100)

    async def test_party_member_can_attack_shared_boss(self):
        party_id=await create_party(self.db,101)
        invite=await invite_to_party(self.db,party_id,101,202)
        await respond_to_party_invite(self.db,invite,202,True)
        await start_party_battle(self.db,party_id,101,10,"Root Warden",100)
        result=await attack_party_battle(self.db,party_id,202,100)
        self.assertEqual(result["status"],"won")
        self.assertEqual(result["members"],[101,202])

    async def test_nonmember_cannot_attack_coop_battle(self):
        party_id=await create_party(self.db,101)
        await start_party_battle(self.db,party_id,101,10,"Root Warden",100)
        with self.assertRaises(PartyError):
            await attack_party_battle(self.db,party_id,202,10)



    async def test_concurrent_party_members_can_attack_without_transaction_collisions(self):
        party_id = await create_party(self.db, 101)
        invite_id = await invite_to_party(self.db, party_id, 101, 202)
        await respond_to_party_invite(self.db, invite_id, 202, True)
        battle_id = await start_party_battle(
            self.db, party_id, 101, 8, "Stormglass Behemoth", 100
        )

        results = await asyncio.gather(
            attack_party_battle(self.db, party_id, 101, 20),
            attack_party_battle(self.db, party_id, 202, 30),
            return_exceptions=True,
        )

        self.assertTrue(all(not isinstance(result, Exception) for result in results))
        battle = await get_party_battle(self.db, party_id)
        self.assertEqual(battle["battle_id"], battle_id)
        self.assertEqual(battle["hp"], 50)
        cur = await self.db.execute(
            "SELECT SUM(damage) AS total FROM party_battle_contributions WHERE battle_id=?",
            (battle_id,),
        )
        contribution = await cur.fetchone()
        self.assertEqual(contribution["total"], 50)

    async def test_concurrent_reward_claims_are_applied_exactly_once(self):
        party_id = await create_party(self.db, 101)
        battle_id = await start_party_battle(
            self.db, party_id, 101, 1, "Concurrency Warden", 25
        )
        await attack_party_battle(self.db, party_id, 101, 25)

        results = await asyncio.gather(
            reward_party_battle(self.db, battle_id, 101, 75, 40),
            reward_party_battle(self.db, battle_id, 101, 75, 40),
            return_exceptions=True,
        )

        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, Exception)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], PartyError)
        cur = await self.db.execute(
            "SELECT coins,xp FROM players WHERE user_id=?",
            (101,),
        )
        player = await cur.fetchone()
        self.assertEqual(player["coins"], 75)
        self.assertEqual(player["xp"], 40)

    async def test_coop_reward_is_claimed_once_per_member(self):
        party_id=await create_party(self.db,101)
        invite=await invite_to_party(self.db,party_id,101,202)
        await respond_to_party_invite(self.db,invite,202,True)
        battle_id=await start_party_battle(self.db,party_id,101,10,"Root Warden",100)
        await attack_party_battle(self.db,party_id,101,100)
        reward=await reward_party_battle(self.db,battle_id,101,50,100)
        self.assertEqual(reward["coins"],50)
        with self.assertRaises(PartyError):
            await reward_party_battle(self.db,battle_id,101,50,100)
        await reward_party_battle(self.db,battle_id,202,50,100)
        cur=await self.db.execute("SELECT coins FROM players WHERE user_id=202")
        self.assertEqual((await cur.fetchone())["coins"],50)

    async def test_coop_attack_rejects_invalid_player_id(self):
        party_id = await create_party(self.db, 101)
        await start_party_battle(self.db, party_id, 101, 10, "Root Warden", 100)
        with self.assertRaisesRegex(PartyError, "Invalid party or player"):
            await attack_party_battle(self.db, party_id, 0, 10)

    async def test_coop_attack_cooldown(self):
        party_id=await create_party(self.db,101)
        await start_party_battle(self.db,party_id,101,10,"Root Warden",1000)
        await attack_party_battle(self.db,party_id,101,10)
        with self.assertRaises(PartyError):
            await attack_party_battle(self.db,party_id,101,10)


    async def test_party_table_initialization_preserves_outer_transaction(self):
        db = await aiosqlite.connect(":memory:")
        try:
            await db.execute("CREATE TABLE transaction_marker(value INTEGER)")
            await db.execute("BEGIN")
            await db.execute("INSERT INTO transaction_marker VALUES(1)")
            await init_party_tables(db)
            self.assertTrue(db.in_transaction)
            await db.rollback()
            cur = await db.execute("SELECT COUNT(*) FROM transaction_marker")
            self.assertEqual((await cur.fetchone())[0], 0)
            cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='parties'")
            self.assertIsNone(await cur.fetchone())
        finally:
            await db.close()

    async def test_party_exploration_rolls_back_stamina_if_battle_creation_fails(self):
        party_id = await create_party(self.db, 101)
        await init_stamina_tables(self.db)
        await get_stamina(self.db, 101, now=1000)
        await self.db.execute("CREATE TRIGGER reject_party_battle BEFORE INSERT ON party_battles BEGIN SELECT RAISE(ABORT,'battle unavailable'); END")
        await self.db.commit()
        await self.db.execute("BEGIN IMMEDIATE")
        try:
            await consume_stamina(self.db, 101, 10, now=1000, commit=False)
            with self.assertRaises(Exception):
                await start_party_battle(self.db, party_id, 101, 10, "Root Warden", 100)
        finally:
            await self.db.rollback()
        state = await get_stamina(self.db, 101, now=1000)
        self.assertEqual(state["stamina"], 100)
        self.assertIsNone(await get_party_battle(self.db, party_id))

    async def test_coop_attack_rolls_back_if_contribution_write_fails(self):
        party_id = await create_party(self.db, 101)
        battle_id = await start_party_battle(self.db, party_id, 101, 10, "Root Warden", 100)
        await self.db.execute("CREATE TRIGGER reject_party_contribution BEFORE INSERT ON party_battle_contributions BEGIN SELECT RAISE(ABORT,'contribution unavailable'); END")
        await self.db.commit()
        with self.assertRaises(Exception):
            await attack_party_battle(self.db, party_id, 101, 20)
        battle = await get_party_battle(self.db, party_id)
        self.assertEqual(battle["hp"], 100)
        cur = await self.db.execute("SELECT COUNT(*) FROM party_battle_cooldowns WHERE battle_id=?", (battle_id,))
        self.assertEqual((await cur.fetchone())[0], 0)

    async def test_coop_reward_rolls_back_if_player_update_fails(self):
        party_id = await create_party(self.db, 101)
        battle_id = await start_party_battle(self.db, party_id, 101, 10, "Root Warden", 100)
        await attack_party_battle(self.db, party_id, 101, 100)
        await self.db.execute("CREATE TRIGGER reject_party_reward BEFORE UPDATE OF coins ON players BEGIN SELECT RAISE(ABORT,'reward unavailable'); END")
        await self.db.commit()
        with self.assertRaises(Exception):
            await reward_party_battle(self.db, battle_id, 101, 50, 40)
        cur = await self.db.execute("SELECT COUNT(*) FROM party_battle_rewards WHERE battle_id=? AND user_id=101", (battle_id,))
        self.assertEqual((await cur.fetchone())[0], 0)
        cur = await self.db.execute("SELECT coins,xp FROM players WHERE user_id=101")
        self.assertEqual(tuple(await cur.fetchone()), (0, 0))

    async def test_leaving_and_rejoining_does_not_reset_old_battle_reward_claim(self):
        party_id = await create_party(self.db, 101)
        invite_id = await invite_to_party(self.db, party_id, 101, 202)
        await respond_to_party_invite(self.db, invite_id, 202, True)
        battle_id = await start_party_battle(
            self.db, party_id, 101, 10, "Root Warden", 100
        )
        await attack_party_battle(self.db, party_id, 101, 100)
        await reward_party_battle(self.db, battle_id, 101, 50, 40)

        await leave_party(self.db, 101)
        rejoin_invite = await invite_to_party(self.db, party_id, 202, 101)
        await respond_to_party_invite(self.db, rejoin_invite, 101, True)

        with self.assertRaisesRegex(PartyError, "already claimed"):
            await reward_party_battle(self.db, battle_id, 101, 50, 40)
        cur = await self.db.execute(
            "SELECT coins,xp FROM players WHERE user_id=101"
        )
        player = await cur.fetchone()
        self.assertEqual((player["coins"], player["xp"]), (50, 40))
        cur = await self.db.execute(
            "SELECT COUNT(*) FROM party_battle_rewards WHERE battle_id=? AND user_id=101",
            (battle_id,),
        )
        self.assertEqual((await cur.fetchone())[0], 1)

if __name__ == "__main__":
    unittest.main()
