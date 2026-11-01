"""Verified SQLite online backups with rotation and safe restore validation."""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
import tempfile
from datetime import datetime, timezone
from pathlib import Path


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
        os.replace(temporary_path, final_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    backups = sorted(
        (p for p in destination_dir.glob(f"{source_path.stem}-*.sqlite3") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[keep:]:
        old_backup.unlink(missing_ok=True)
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
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination
