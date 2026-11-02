"""Verified SQLite online backups with rotation and safe restore validation."""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import warnings


def _fsync_file(path: Path) -> None:
    """Flush file contents and metadata before publishing an atomic rename."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    """Persist directory entry changes on POSIX filesystems."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_backup(database_path: str | Path, backup_dir: str | Path, keep: int = 7) -> Path:
    """Create a consistent SQLite backup, verify it, then atomically publish it."""
    source_path = Path(database_path)
    if keep < 1:
        raise ValueError("keep must be at least 1")
    if not source_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {source_path}")
    destination_dir = Path(backup_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    final_path = destination_dir / f"{source_path.stem}-{stamp}.sqlite3"
    fd, temporary_name = tempfile.mkstemp(prefix=".backup-", suffix=".tmp", dir=destination_dir)
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        with closing(sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True, timeout=30)) as source:
            with closing(sqlite3.connect(temporary_path, timeout=30)) as target:
                source.backup(target, pages=256, sleep=0.05)
                result = target.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise sqlite3.DatabaseError(f"Backup integrity check failed: {result}")
        _fsync_file(temporary_path)
        os.replace(temporary_path, final_path)
        _fsync_directory(destination_dir)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    backups = sorted(
        (p for p in destination_dir.glob(f"{source_path.stem}-*.sqlite3") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed_backup = False
    for old_backup in backups[keep:]:
        try:
            old_backup.unlink(missing_ok=True)
            removed_backup = True
        except OSError as exc:
            warnings.warn(
                f"Backup was created, but retention cleanup could not remove {old_backup}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
    if removed_backup:
        _fsync_directory(destination_dir)
    return final_path


def verify_backup(backup_path: str | Path) -> bool:
    """Return True only when SQLite reports a clean, readable database."""
    path = Path(backup_path)
    if not path.is_file():
        return False
    try:
        with closing(sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=10)) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            return bool(result and result[0] == "ok")
    except sqlite3.Error:
        return False

 
def restore_backup(backup_path: str | Path, database_path: str | Path) -> Path:
    """Atomically restore a verified snapshot. Stop the game process before calling."""
    source = Path(backup_path)
    destination = Path(database_path)
    if not verify_backup(source):
        raise sqlite3.DatabaseError("Refusing to restore an invalid or unreadable backup")
    if source.resolve() == destination.resolve():
        raise sqlite3.OperationalError("Backup source and restore destination must be different files")
    sidecars = (Path(str(destination) + "-wal"), Path(str(destination) + "-shm"))
    if any(path.exists() for path in sidecars):
        raise sqlite3.OperationalError(
            "Refusing to restore while SQLite WAL/SHM sidecar files exist; stop all database users and resolve the sidecars first"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".restore-", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with closing(sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True, timeout=30)) as source_db:
            with closing(sqlite3.connect(temporary, timeout=30)) as target_db:
                source_db.backup(target_db, pages=256, sleep=0.05)
                result = target_db.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise sqlite3.DatabaseError(f"Restore verification failed: {result}")
        _fsync_file(temporary)
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination

 
def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="The Peak Adventure SQLite backup utility")
    commands = parser.add_subparsers(dest="command", required=True)
    backup_parser = commands.add_parser("backup", help="create and verify a rotated backup")
    backup_parser.add_argument("--database", default=os.getenv("DATABASE_PATH", "peak_adventure.db"))
    backup_parser.add_argument("--directory", default=os.getenv("BACKUP_DIR", "backups"))
    backup_parser.add_argument("--keep", type=int, default=int(os.getenv("BACKUP_RETENTION", "7")))
    verify_parser = commands.add_parser("verify", help="verify a backup integrity")
    verify_parser.add_argument("backup")
    restore_parser = commands.add_parser("restore", help="restore a verified backup (stop the bot first)")
    restore_parser.add_argument("backup")
    restore_parser.add_argument("--database", default=os.getenv("DATABASE_PATH", "peak_adventure.db"))
    args = parser.parse_args()

    if args.command == "backup":
        result = create_backup(args.database, args.directory, args.keep)
        print(f"Verified backup created: {result}")
        return 0
    if args.command == "verify":
        valid = verify_backup(args.backup)
        print("Backup integrity: OK" if valid else "Backup integrity: FAILED")
        return 0 if valid else 1
    print("Restore requires the game process to be stopped.")
    result = restore_backup(args.backup, args.database)
    print(f"Verified backup restored to: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
