import unittest
import aiosqlite

from report_system import (
    ReportError, init_report_tables, list_open_reports,
    resolve_player_report, submit_player_report,
)


class PlayerReportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("CREATE TABLE players(user_id INTEGER PRIMARY KEY)")
        await self.db.executemany("INSERT INTO players(user_id) VALUES(?)", [(1,), (2,)])
        await init_report_tables(self.db)

    async def asyncTearDown(self):
        await self.db.close()

    async def test_submit_report(self):
        report_id = await submit_player_report(self.db, 1, 2, "Repeatedly abusing other players", now=1000)
        self.assertEqual(report_id, 1)
        self.assertEqual(len(await list_open_reports(self.db)), 1)

    async def test_duplicate_open_report_blocked(self):
        await submit_player_report(self.db, 1, 2, "Repeatedly abusing other players", now=1000)
        with self.assertRaises(ReportError):
            await submit_player_report(self.db, 1, 2, "Another report about this player", now=1001)

    async def test_self_report_and_unknown_target_blocked(self):
        with self.assertRaises(ReportError):
            await submit_player_report(self.db, 1, 1, "This is a sufficiently long reason")
        with self.assertRaises(ReportError):
            await submit_player_report(self.db, 1, 99, "This is a sufficiently long reason")

    async def test_reason_length_validated(self):
        with self.assertRaises(ReportError):
            await submit_player_report(self.db, 1, 2, "short")

    async def test_admin_can_resolve_report_once(self):
        report_id = await submit_player_report(self.db, 1, 2, "Repeatedly abusing other players", now=1000)
        self.assertTrue(await resolve_player_report(self.db, report_id, 900, "reviewed", "Checked chat logs"))
        self.assertEqual(await list_open_reports(self.db), [])
        with self.assertRaises(ReportError):
            await resolve_player_report(self.db, report_id, 900, "dismissed")

if __name__ == "__main__":
    unittest.main()
