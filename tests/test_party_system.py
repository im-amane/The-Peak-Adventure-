import unittest

import aiosqlite

from party_system import (
    PartyError,
    create_party,
    disband_party,
    get_party_info,
    init_party_tables,
    invite_to_party,
    leave_party,
    respond_to_party_invite,
)


class PartySystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript("""
        CREATE TABLE players (
          user_id INTEGER PRIMARY KEY, username TEXT, level INTEGER NOT NULL DEFAULT 1
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


if __name__ == "__main__":
    unittest.main()
