import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backup_scheduler import create_database_backup


class DatabaseBackupSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, database, postgres_url=""):
        return create_database_backup(
            database,
            sqlite_path=self.root / "unused.sqlite3",
            sqlite_directory=self.root / "sqlite",
            sqlite_keep=3,
            postgres_url=postgres_url,
            postgres_directory=self.root / "postgres",
            postgres_keep=5,
        )

    def test_sqlite_uses_sqlite_backup_provider(self):
        database = type("Database", (), {"dialect": "sqlite"})()
        expected = self.root / "sqlite-backup.sqlite3"
        with patch("backup_scheduler.create_sqlite_backup", return_value=expected) as create:
            self.assertEqual(self._run(database), expected)
        create.assert_called_once_with(self.root / "unused.sqlite3", self.root / "sqlite", 3)

    def test_postgres_uses_postgres_backup_provider(self):
        database = type("Database", (), {"dialect": "postgres"})()
        expected = self.root / "game.dump"
        url = "postgresql://user:pass@db.example.test/game"
        with patch("postgres_backup.create_backup", return_value=expected) as create:
            self.assertEqual(self._run(database, url), expected)
        create.assert_called_once_with(url, self.root / "postgres", 5)

    def test_postgres_without_database_url_fails_closed(self):
        database = type("Database", (), {"dialect": "postgres"})()
        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is missing"):
            self._run(database)

    def test_unknown_dialect_is_rejected(self):
        database = type("Database", (), {"dialect": "mysql"})()
        with self.assertRaisesRegex(RuntimeError, "Unsupported database dialect"):
            self._run(database)

    def test_uninitialized_database_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "not initialized"):
            self._run(None)


if __name__ == "__main__":
    unittest.main()
