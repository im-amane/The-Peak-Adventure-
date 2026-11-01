import unittest

import aiosqlite

from account_system import init_account_tables, update_settings

from friend_system import (
    FriendError,
    init_friend_tables,
    list_friends,
    list_pending_friend_requests,
    remove_friend,
    respond_to_friend_request,
    search_players,
    send_friend_request,
)


class FriendSystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript("""
        CREATE TABLE players (
          user_id INTEGER PRIMARY KEY,
          username TEXT,
          level INTEGER NOT NULL DEFAULT 1
        );
        INSERT INTO players(user_id,username,level) VALUES
          (101,'Ash',4),(202,'Mira',8),(303,'Rook',2);
        """)
        await init_friend_tables(self.db)
        await init_account_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_request_is_created_and_accepted_by_target(self):
        request_id = await send_friend_request(self.db, 101, 202)
        await respond_to_friend_request(self.db, request_id, 202, True)
        friends = await list_friends(self.db, 101)
        self.assertEqual([(row["user_id"], row["username"]) for row in friends], [(202, "Mira")])

    async def test_search_returns_public_profiles(self):
        results = await search_players(self.db, 101, "Mi")
        self.assertEqual([row["user_id"] for row in results], [202])

    async def test_search_respects_friends_only_visibility(self):
        await update_settings(self.db, 202, profile_visibility="friends")
        self.assertEqual(await search_players(self.db, 101, "Mira"), [])
        request_id = await send_friend_request(self.db, 101, 202)
        await respond_to_friend_request(self.db, request_id, 202, True)
        results = await search_players(self.db, 101, "Mira")
        self.assertEqual([row["user_id"] for row in results], [202])

    async def test_search_escapes_wildcards_and_validates_query(self):
        self.assertEqual(await search_players(self.db, 101, "%%"), [])
        with self.assertRaisesRegex(FriendError, "between 2 and 32"):
            await search_players(self.db, 101, "x")

    async def test_pending_friend_requests_are_private_to_target(self):
        request_id = await send_friend_request(self.db, 101, 202)
        incoming = await list_pending_friend_requests(self.db, 202)
        self.assertEqual([row["request_id"] for row in incoming], [request_id])
        self.assertEqual(await list_pending_friend_requests(self.db, 101), [])

    async def test_self_request_is_rejected(self):
        with self.assertRaisesRegex(FriendError, "yourself"):
            await send_friend_request(self.db, 101, 101)

    async def test_duplicate_and_reverse_pending_requests_are_rejected(self):
        await send_friend_request(self.db, 101, 202)
        with self.assertRaisesRegex(FriendError, "already pending"):
            await send_friend_request(self.db, 101, 202)
        with self.assertRaisesRegex(FriendError, "already sent you"):
            await send_friend_request(self.db, 202, 101)

    async def test_only_target_can_accept_or_decline(self):
        request_id = await send_friend_request(self.db, 101, 202)
        with self.assertRaisesRegex(FriendError, "Only the invited player"):
            await respond_to_friend_request(self.db, request_id, 101, True)
        await respond_to_friend_request(self.db, request_id, 202, False)
        with self.assertRaisesRegex(FriendError, "no longer active"):
            await respond_to_friend_request(self.db, request_id, 202, True)

    async def test_accepted_friendship_is_bidirectional(self):
        request_id = await send_friend_request(self.db, 101, 303)
        await respond_to_friend_request(self.db, request_id, 303, True)
        self.assertEqual([row["user_id"] for row in await list_friends(self.db, 101)], [303])
        self.assertEqual([row["user_id"] for row in await list_friends(self.db, 303)], [101])
        with self.assertRaisesRegex(FriendError, "already friends"):
            await send_friend_request(self.db, 303, 101)

    async def test_removed_friend_can_be_added_again(self):
        request_id = await send_friend_request(self.db, 101, 202)
        await respond_to_friend_request(self.db, request_id, 202, True)
        await remove_friend(self.db, 101, 202)
        self.assertEqual(await list_friends(self.db, 101), [])
        new_request = await send_friend_request(self.db, 202, 101)
        self.assertGreater(new_request, request_id)

    async def test_outgoing_pending_requests_have_a_spam_limit(self):
        for target_id in range(1000, 1010):
            await send_friend_request(self.db, 101, target_id)
        with self.assertRaisesRegex(FriendError, "at most 10"):
            await send_friend_request(self.db, 101, 2000)

    async def test_invalid_and_boolean_player_ids_are_rejected(self):
        for requester_id, target_id in ((0, 202), (-1, 202), (True, 202), (101, False)):
            with self.subTest(requester_id=requester_id, target_id=target_id):
                with self.assertRaises(FriendError):
                    await send_friend_request(self.db, requester_id, target_id)

    async def test_unknown_friend_cannot_be_removed(self):
        with self.assertRaisesRegex(FriendError, "not on your friend list"):
            await remove_friend(self.db, 101, 202)


if __name__ == "__main__":
    unittest.main()
