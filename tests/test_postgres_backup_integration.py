"""Real PostgreSQL dump/restore rehearsal against disposable CI databases."""
import os, shutil, tempfile, unittest, uuid
from urllib.parse import urlsplit, urlunsplit
import psycopg
from psycopg import sql
import postgres_backup

def database_url(base, name):
    p = urlsplit(base)
    return urlunsplit((p.scheme, p.netloc, "/" + name, p.query, p.fragment))

@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL") and shutil.which("pg_dump") and shutil.which("pg_restore"), "requires PostgreSQL CI service and client tools")
class PostgreSQLRealRestoreDrillTests(unittest.TestCase):
    def test_backup_rotation_keeps_only_latest_verified_archives(self):
        admin_url = os.environ["TEST_POSTGRES_URL"]
        suffix = uuid.uuid4().hex[:12]
        source = "peak_backup_rotate_" + suffix
        source_url = database_url(admin_url, source)
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(source)))
        try:
            with psycopg.connect(source_url) as db:
                db.execute("CREATE TABLE rotation_probe (id INTEGER PRIMARY KEY)")
                db.execute("INSERT INTO rotation_probe VALUES (1)")
            with tempfile.TemporaryDirectory(prefix="peak-backup-rotation-") as directory:
                archives = [
                    postgres_backup.create_backup(source_url, directory, keep=2)
                    for _ in range(3)
                ]
                remaining = sorted(__import__("pathlib").Path(directory).glob("*.dump"))
                self.assertEqual(len(remaining), 2)
                self.assertEqual(remaining, sorted(archives[-2:]))
                self.assertTrue(all(postgres_backup.verify_backup(path, source_url) for path in remaining))
                self.assertTrue(all(__import__("pathlib").Path(str(path) + ".sha256").is_file() for path in remaining))
        finally:
            with psycopg.connect(admin_url, autocommit=True) as admin:
                admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(source)))

    def test_backup_restores_rows_into_separate_disposable_database(self):
        admin_url = os.environ["TEST_POSTGRES_URL"]
        suffix = uuid.uuid4().hex[:12]
        source, target = "peak_backup_src_" + suffix, "peak_backup_dst_" + suffix
        source_url, target_url = database_url(admin_url, source), database_url(admin_url, target)
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(source)))
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
        try:
            with psycopg.connect(source_url) as db:
                db.execute("CREATE TABLE restore_drill (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
                db.execute("INSERT INTO restore_drill VALUES (%s,%s),(%s,%s)", (1,"first",2,"second"))
            with tempfile.TemporaryDirectory(prefix="peak-restore-drill-") as directory:
                archive = postgres_backup.create_backup(source_url, directory, keep=1)
                self.assertTrue(postgres_backup.verify_backup(archive, target_url))
                with self.assertRaisesRegex(ValueError, "must exactly match"):
                    postgres_backup.restore_backup(
                        archive, target_url, confirm_database="wrong_database_name"
                    )
                postgres_backup.restore_backup(archive, target_url, confirm_database=target)
            with psycopg.connect(target_url) as db:
                rows = db.execute("SELECT id,payload FROM restore_drill ORDER BY id").fetchall()
            self.assertEqual(rows, [(1,"first"),(2,"second")])
        finally:
            with psycopg.connect(admin_url, autocommit=True) as admin:
                for name in (target, source):
                    admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))

if __name__ == "__main__":
    unittest.main()
