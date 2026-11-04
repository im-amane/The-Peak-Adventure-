import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import postgres_backup


class PostgreSQLBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.url = "postgresql://backup-user:secret%40pass@db.example.test:5433/game_db?sslmode=require"

    def tearDown(self):
        self.temp.cleanup()

    def _fake_run(self, command, *, env, capture_output, text, check):
        if Path(command[0]).name == "pg_dump":
            Path(command[command.index("--file") + 1]).write_bytes(b"PGDMP-test-archive")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    def test_connection_options_keep_password_out_of_arguments(self):
        args, env, database = postgres_backup._connection_options(self.url)
        self.assertEqual(database, "game_db")
        self.assertIn("--dbname", args)
        self.assertIn("db.example.test:5433", " ".join(args))
        self.assertIn("sslmode=require", " ".join(args))
        self.assertNotIn("secret@pass", " ".join(args))
        self.assertEqual(env["PGPASSWORD"], "secret@pass")

    def test_rejects_non_postgres_or_unsupported_connection_options(self):
        with self.assertRaises(ValueError):
            postgres_backup._connection_options("sqlite:///game.db")
        with self.assertRaises(ValueError):
            postgres_backup._connection_options("postgresql://u:p@host/db?sslrootcert=/tmp/cert")

    @patch("postgres_backup.shutil.which", return_value="/usr/bin/fake")
    @patch("postgres_backup.subprocess.run")
    def test_backup_is_archived_checksummed_and_verified_before_publish(self, run, _which):
        run.side_effect = self._fake_run
        result = postgres_backup.create_backup(self.url, self.root, pg_dump="pg_dump", pg_restore="pg_restore")
        self.assertTrue(result.is_file())
        checksum = Path(str(result) + ".sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(checksum, hashlib.sha256(result.read_bytes()).hexdigest())
        self.assertEqual(run.call_count, 2)
        dump_call = run.call_args_list[0].args[0]
        self.assertIn("--format=custom", dump_call)
        self.assertNotIn("secret@pass", " ".join(dump_call))
        self.assertEqual(run.call_args_list[0].kwargs["env"]["PGPASSWORD"], "secret@pass")

    @patch("postgres_backup.shutil.which", return_value="/usr/bin/fake")
    @patch("postgres_backup.subprocess.run")
    def test_rotation_removes_archive_and_checksum_together(self, run, _which):
        run.side_effect = self._fake_run
        first = postgres_backup.create_backup(self.url, self.root, keep=2)
        second = postgres_backup.create_backup(self.url, self.root, keep=2)
        third = postgres_backup.create_backup(self.url, self.root, keep=2)
        self.assertFalse(first.exists())
        self.assertFalse(Path(str(first) + ".sha256").exists())
        self.assertTrue(second.exists())
        self.assertTrue(third.exists())

    @patch("postgres_backup.shutil.which", return_value="/usr/bin/fake")
    @patch("postgres_backup.subprocess.run")
    def test_rotation_namespaces_do_not_collide_after_filename_sanitization(self, run, _which):
        run.side_effect = self._fake_run
        first_url = "postgresql://backup-user:secret@db.example.test/game%2Fdb"
        second_url = "postgresql://backup-user:secret@db.example.test/game%3Fdb"
        first = postgres_backup.create_backup(first_url, self.root, keep=1)
        second = postgres_backup.create_backup(second_url, self.root, keep=1)
        self.assertNotEqual(first.name.split("-")[-2], second.name.split("-")[-2])
        self.assertTrue(first.is_file())
        self.assertTrue(Path(str(first) + ".sha256").is_file())
        self.assertTrue(second.is_file())
        self.assertTrue(Path(str(second) + ".sha256").is_file())

    @patch("postgres_backup.shutil.which", return_value="/usr/bin/fake")
    @patch("postgres_backup.subprocess.run")
    def test_restore_requires_exact_database_confirmation_and_verified_archive(self, run, _which):
        run.side_effect = self._fake_run
        backup = postgres_backup.create_backup(self.url, self.root)
        with self.assertRaisesRegex(ValueError, "exactly match"):
            postgres_backup.restore_backup(backup, self.url, confirm_database="other_db")
        run.reset_mock()
        postgres_backup.restore_backup(backup, self.url, confirm_database="game_db")
        restore_call = run.call_args.args[0]
        self.assertIn("--single-transaction", restore_call)
        self.assertIn("--clean", restore_call)

    @patch("postgres_backup.shutil.which", return_value="/usr/bin/fake")
    @patch("postgres_backup.subprocess.run")
    def test_checksum_mismatch_prevents_restore(self, run, _which):
        run.side_effect = self._fake_run
        backup = postgres_backup.create_backup(self.url, self.root)
        backup.write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "invalid or unreadable"):
            postgres_backup.restore_backup(backup, self.url, confirm_database="game_db")


if __name__ == "__main__":
    unittest.main()
