import unittest
import aiosqlite
from unittest.mock import patch

from security_system import (
    SecurityEventError, get_security_events, get_suspicious_players,
    init_security_tables, record_security_event,
)


class SecuritySystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await init_security_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_records_and_aggregates_suspicious_activity(self):
        await record_security_event(self.db, 101, "invalid_battle_action", "unknown action", 2)
        await record_security_event(self.db, 101, "invalid_monster_request", "level 999", 4)
        await record_security_event(self.db, 202, "invalid_social_action", "unsupported action", 1)
        rows = await get_suspicious_players(self.db)
        self.assertEqual(rows[0]["user_id"], 101)
        self.assertEqual(rows[0]["event_count"], 2)
        self.assertEqual(rows[0]["max_severity"], 4)
        self.assertEqual(rows[0]["risk_score"], 6)

    async def test_event_details_are_bounded(self):
        await record_security_event(self.db, 101, "invalid_battle_action", "x" * 400)
        rows = await get_security_events(self.db, 101)
        self.assertEqual(len(rows[0]["details"]), 240)

    async def test_event_storage_respects_configured_cap(self):
        with patch("security_system.MAX_SECURITY_EVENTS", 2), patch("security_system.CLEANUP_INTERVAL", 1):
            for index in range(5):
                await record_security_event(self.db, 101, "invalid_battle_action", str(index))
        cur = await self.db.execute("SELECT COUNT(*) AS total FROM security_events")
        self.assertEqual((await cur.fetchone())["total"], 2)

    async def test_invalid_event_and_limits_are_rejected(self):
        with self.assertRaises(SecurityEventError):
            await record_security_event(self.db, 101, "not_allowed")
        with self.assertRaises(SecurityEventError):
            await get_suspicious_players(self.db, window_minutes=0)
        with self.assertRaises(SecurityEventError):
            await get_security_events(self.db, 101, limit=0)


if __name__ == "__main__":
    unittest.main()
