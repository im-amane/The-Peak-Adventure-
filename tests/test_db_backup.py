import sqlite3
import tempfile
import unittest
from pathlib import Path

from db_backup import create_backup, restore_backup, verify_backup


class DatabaseBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "game.sqlite3"
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE players (user_id INTEGER PRIMARY KEY, coins INTEGER)")
            connection.execute("INSERT INTO players VALUES (7, 1234)")

    def tearDown(self):
        self.temp.cleanup()

    def test_backup_contains_committed_data_and_passes_integrity(self):
        backup = create_backup(self.database, self.root / "backups")
        self.assertTrue(verify_backup(backup))
        with sqlite3.connect(backup) as connection:
            self.assertEqual(connection.execute("SELECT coins FROM players WHERE user_id=7").fetchone()[0], 1234)

    def test_rotation_keeps_newest_requested_count(self):
        folder = self.root / "backups"
        for _ in range(4):
            create_backup(self.database, folder, keep=2)
        self.assertEqual(len(list(folder.glob("game-*.sqlite3"))), 2)

    def test_missing_database_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            create_backup(self.root / "missing.sqlite3", self.root / "backups")

    def test_invalid_retention_is_rejected(self):
        with self.assertRaises(ValueError):
            create_backup(self.database, self.root / "backups", keep=0)

    def test_invalid_backup_fails_verification(self):
        corrupt = self.root / "broken.sqlite3"
        corrupt.write_text("not a sqlite database", encoding="utf-8")
        self.assertFalse(verify_backup(corrupt))

    def test_restore_replaces_database_with_verified_snapshot(self):
        backup = create_backup(self.database, self.root / "backups")
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE players SET coins=0 WHERE user_id=7")
        restore_backup(backup, self.database)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT coins FROM players WHERE user_id=7").fetchone()[0], 1234)

    def test_restore_rejects_corrupt_backup_without_changing_database(self):
        corrupt = self.root / "broken.sqlite3"
        corrupt.write_text("not a sqlite database", encoding="utf-8")
        with self.assertRaises(sqlite3.DatabaseError):
            restore_backup(corrupt, self.database)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT coins FROM players WHERE user_id=7").fetchone()[0], 1234)


if __name__ == "__main__":
    unittest.main()
