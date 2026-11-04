"""Database-engine-aware backup dispatch for the application runtime."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from db_backup import create_backup as create_sqlite_backup


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
    """Create a verified backup using the active database engine."""
    if database is None:
        raise RuntimeError("Database connection is not initialized; refusing to back up.")

    dialect = getattr(database, "dialect", "sqlite")
    if dialect == "postgres":
        if not postgres_url:
            raise RuntimeError("PostgreSQL is active but DATABASE_URL is missing.")
        from postgres_backup import create_backup as create_postgres_backup

        return create_postgres_backup(postgres_url, postgres_directory, postgres_keep)

    if dialect != "sqlite":
        raise RuntimeError(f"Unsupported database dialect for backups: {dialect!r}")

    return create_sqlite_backup(sqlite_path, sqlite_directory, sqlite_keep)
