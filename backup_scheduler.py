"""Database-engine-aware backup dispatch for the application runtime."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from db_backup import create_backup as create_sqlite_backup

logger = logging.getLogger(__name__)


def _export_offsite(path: Path) -> None:
    # Optional by design: local verified backups continue to work without a
    # configured provider. If configured, failures are surfaced to the caller.
    from offsite_backup import upload_backup_from_environment

    object_key = upload_backup_from_environment(path)
    if object_key:
        logger.info("Off-site database backup uploaded: %s", object_key)


def create_database_backup(
    database: Any,
    *,
    sqlite_path: str | Path,
    sqlite_directory: str | Path,
    sqlite_keep: int,
    postgres_url: str,
    postgres_directory: str | Path,
    postgres_keep: int,
) -> Path:
    """Create a verified backup using the active database engine, then export it."""
    if database is None:
        raise RuntimeError("Database connection is not initialized; refusing to back up.")

    dialect = getattr(database, "dialect", "sqlite")
    if dialect == "postgres":
        if not postgres_url:
            raise RuntimeError("PostgreSQL is active but DATABASE_URL is missing.")
        from postgres_backup import create_backup as create_postgres_backup

        backup_path = create_postgres_backup(postgres_url, postgres_directory, postgres_keep)
    elif dialect == "sqlite":
        backup_path = create_sqlite_backup(sqlite_path, sqlite_directory, sqlite_keep)
    else:
        raise RuntimeError(f"Unsupported database dialect for backups: {dialect!r}")

    _export_offsite(Path(backup_path))
    return Path(backup_path)
