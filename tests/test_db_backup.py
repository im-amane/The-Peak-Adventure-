import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import db_backup
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

    def test_backup_fsyncs_snapshot_before_atomic_publish(self):
        events = []
        real_replace = db_backup.os.replace

        def tracked_replace(source, destination):
            events.append("replace")
            return real_replace(source, destination)

        with patch("db_backup._fsync_file", side_effect=lambda path: events.append("file")), patch(
            "db_backup.os.replace", side_effect=tracked_replace
        ), patch("db_backup._fsync_directory", side_effect=lambda path: events.append("directory")):
            create_backup(self.database, self.root / "backups")

        self.assertEqual(events, ["file", "replace", "directory"])

    def test_restore_fsyncs_verified_snapshot_before_atomic_publish(self):
        backup = create_backup(self.database, self.root / "backups")
        events = []
        real_replace = db_backup.os.replace

        def tracked_replace(source, destination):
            events.append("replace")
            return real_replace(source, destination)

        with patch("db_backup._fsync_file", side_effect=lambda path: events.append("file")), patch(
            "db_backup.os.replace", side_effect=tracked_replace
        ), patch("db_backup._fsync_directory", side_effect=lambda path: events.append("directory")):
            restore_backup(backup, self.database)

        self.assertEqual(events, ["file", "replace", "directory"])

    def test_failed_atomic_restore_keeps_existing_database_and_cleans_temporary_file(self):
        backup = create_backup(self.database, self.root / "backups")
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE players SET coins=4321 WHERE user_id=7")

        with patch("db_backup.os.replace", side_effect=OSError("simulated atomic rename failure")):
            with self.assertRaisesRegex(OSError, "simulated atomic rename failure"):
                restore_backup(backup, self.database)

        with sqlite3.connect(self.database) as connection:
            self.assertEqual(
                connection.execute("SELECT coins FROM players WHERE user_id=7").fetchone()[0],
                4321,
            )
        self.assertEqual(list(self.root.glob(".restore-*.tmp")), [])

    def test_online_backup_remains_valid_during_concurrent_writes(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE events(event_id INTEGER PRIMARY KEY,value TEXT)")
            connection.commit()

        started = threading.Event()
        failures = []

        def write_events():
            try:
                with sqlite3.connect(self.database, timeout=30) as connection:
                    for index in range(300):
                        connection.execute(
                            "INSERT INTO events(event_id,value) VALUES(?,?)",
                            (index + 1, f"event-{index + 1}"),
                        )
                        if index == 0 or index % 10 == 0:
                            connection.commit()
                        if index == 0:
                            started.set()
                        time.sleep(0.001)
                    connection.commit()
            except Exception as exc:
                failures.append(exc)
                started.set()

        writer = threading.Thread(target=write_events, daemon=True)
        writer.start()
        self.assertTrue(started.wait(timeout=5))
        backup = create_backup(self.database, self.root / "backups")
        writer.join(timeout=10)

        self.assertFalse(writer.is_alive(), "concurrent SQLite writer did not finish")
        self.assertEqual(failures, [])
        self.assertTrue(verify_backup(backup))
        with sqlite3.connect(backup) as connection:
            count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self.assertGreaterEqual(count, 1)
        self.assertLessEqual(count, 300)

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

    def test_restore_rejects_existing_wal_or_shm_sidecars(self):
        backup = create_backup(self.database, self.root / "backups")
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE players SET coins=0 WHERE user_id=7")
        for suffix in ("-wal", "-shm"):
            with self.subTest(sidecar=suffix):
                sidecar = Path(str(self.database) + suffix)
                sidecar.write_bytes(b"stale sidecar")
                try:
                    with self.assertRaises(sqlite3.OperationalError):
                        restore_backup(backup, self.database)
                    with sqlite3.connect(self.database) as connection:
                        self.assertEqual(
                            connection.execute("SELECT coins FROM players WHERE user_id=7").fetchone()[0],
                            0,
                        )
                    self.assertTrue(sidecar.exists())
                finally:
                    sidecar.unlink(missing_ok=True)

    def test_restore_rejects_same_source_and_destination(self):
        with self.assertRaises(sqlite3.OperationalError):
            restore_backup(self.database, self.database)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(
                connection.execute("SELECT coins FROM players WHERE user_id=7").fetchone()[0],
                1234,
            )

    def test_restore_rejects_corrupt_backup_without_changing_database(self):
        corrupt = self.root / "broken.sqlite3"
        corrupt.write_text("not a sqlite database", encoding="utf-8")
        with self.assertRaises(sqlite3.DatabaseError):
            restore_backup(corrupt, self.database)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT coins FROM players WHERE user_id=7").fetchone()[0], 1234)


if __name__ == "__main__":
    unittest.main()
