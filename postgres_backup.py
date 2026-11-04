"""Verified PostgreSQL logical backups with checksums, rotation, and guarded restore.

Requires PostgreSQL client tools (pg_dump and pg_restore) on PATH. Backups are
created locally; this module never connects to or changes production by itself.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit


_ALLOWED_QUERY = {"sslmode", "application_name", "connect_timeout", "target_session_attrs"}


def _connection_options(database_url: str) -> tuple[list[str], dict[str, str], str]:
    """Convert a PostgreSQL URL into libpq CLI options without exposing its password."""
    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("A PostgreSQL DATABASE_URL is required")
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use postgres:// or postgresql://")
    if not parsed.hostname or not parsed.path.strip("/") or not parsed.username:
        raise ValueError("DATABASE_URL must include host, database name, and username")
    query = parse_qs(parsed.query, keep_blank_values=False)
    unsupported = set(query) - _ALLOWED_QUERY
    if unsupported:
        raise ValueError("Unsupported DATABASE_URL option(s): " + ", ".join(sorted(unsupported)))
    database = unquote(parsed.path.lstrip("/"))
    username = unquote(parsed.username)
    for key in query:
        if len(query[key]) != 1:
            raise ValueError(f"DATABASE_URL option {key!r} must appear once")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    authority = quote(username, safe="") + "@" + host
    if parsed.port:
        authority += f":{parsed.port}"
    safe_url = f"postgresql://{authority}/{quote(database, safe='')}"
    if parsed.query:
        safe_url += "?" + parsed.query
    # Keep credentials out of argv/process listings. libpq reads the password
    # from PGPASSWORD while the password-free URI carries TLS and other options.
    options = ["--dbname", safe_url]
    environment = os.environ.copy()
    password = unquote(parsed.password or "")
    if password:
        environment["PGPASSWORD"] = password
    else:
        environment.pop("PGPASSWORD", None)
    return options, environment, database


def _run(command: list[str], environment: dict[str, str], database_url: str) -> subprocess.CompletedProcess:
    result = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout or "PostgreSQL client command failed").strip()
        parsed = urlsplit(database_url)
        if parsed.password:
            detail = detail.replace(parsed.password, "[REDACTED]")
            detail = detail.replace(unquote(parsed.password), "[REDACTED]")
        raise RuntimeError(f"{Path(command[0]).name} failed (exit {result.returncode}): {detail}")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_backup(backup_path: str | Path, database_url: str) -> bool:
    """Verify the SHA-256 sidecar and that pg_restore can read the archive catalog."""
    path = Path(backup_path)
    checksum_path = Path(str(path) + ".sha256")
    if not path.is_file() or not checksum_path.is_file():
        return False
    try:
        expected = checksum_path.read_text(encoding="ascii").strip().split()[0]
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or _sha256(path) != expected:
            return False
        _, environment, _ = _connection_options(database_url)
        _run(["pg_restore", "--list", str(path)], environment, database_url)
        return True
    except (OSError, ValueError, RuntimeError, IndexError):
        return False


def create_backup(
    database_url: str,
    backup_dir: str | Path,
    keep: int = 7,
    *,
    pg_dump: str = "pg_dump",
    pg_restore: str = "pg_restore",
) -> Path:
    """Create a custom-format dump, validate it, checksum it, then atomically publish."""
    if keep < 1:
        raise ValueError("keep must be at least 1")
    if shutil.which(pg_dump) is None or shutil.which(pg_restore) is None:
        raise FileNotFoundError("PostgreSQL client tools pg_dump and pg_restore must be installed")
    connection_args, environment, database = _connection_options(database_url)
    destination = Path(backup_dir)
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    final_path = destination / f"{database}-{stamp}.dump"
    fd, temporary_name = tempfile.mkstemp(prefix=".postgres-backup-", suffix=".tmp", dir=destination)
    os.close(fd)
    temporary = Path(temporary_name)
    checksum_temporary = temporary.with_suffix(".sha256.tmp")
    try:
        _run(
            [pg_dump, "--format=custom", "--compress=6", "--no-owner", "--no-acl",
             "--file", str(temporary), *connection_args],
            environment,
            database_url,
        )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError("pg_dump completed without producing a non-empty archive")
        _run([pg_restore, "--list", str(temporary)], environment, database_url)
        digest = _sha256(temporary)
        checksum_temporary.write_text(f"{digest}  {final_path.name}\n", encoding="ascii")
        _fsync_file(temporary)
        _fsync_file(checksum_temporary)
        os.replace(temporary, final_path)
        os.replace(checksum_temporary, Path(str(final_path) + ".sha256"))
        _fsync_directory(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        checksum_temporary.unlink(missing_ok=True)
        raise

    backups = sorted(
        (item for item in destination.glob(f"{database}-*.dump") if item.is_file()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    removed = False
    for old in backups[keep:]:
        old.unlink(missing_ok=True)
        Path(str(old) + ".sha256").unlink(missing_ok=True)
        removed = True
    if removed:
        _fsync_directory(destination)
    return final_path


def restore_backup(
    backup_path: str | Path,
    database_url: str,
    *,
    confirm_database: str,
    pg_restore: str = "pg_restore",
) -> None:
    """Restore into a named target only after explicit database-name confirmation.

    This operation replaces objects in the target database. Stop the application and
    take a fresh backup before running it. --single-transaction avoids partial restores.
    """
    path = Path(backup_path)
    connection_args, environment, database = _connection_options(database_url)
    if confirm_database != database:
        raise ValueError(f"Restore confirmation must exactly match target database name: {database}")
    if shutil.which(pg_restore) is None:
        raise FileNotFoundError("PostgreSQL client tool pg_restore must be installed")
    if not verify_backup(path, database_url):
        raise RuntimeError("Refusing to restore an invalid or unreadable PostgreSQL backup")
    _run(
        [pg_restore, "--clean", "--if-exists", "--no-owner", "--no-acl",
         "--exit-on-error", "--single-transaction", *connection_args, str(path)],
        environment,
        database_url,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verified PostgreSQL backup and restore utility")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="create a verified, rotated PostgreSQL backup")
    backup.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    backup.add_argument("--directory", default=os.getenv("POSTGRES_BACKUP_DIR", "postgres_backups"))
    backup.add_argument("--keep", type=int, default=int(os.getenv("POSTGRES_BACKUP_RETENTION", "7")))
    verify = commands.add_parser("verify", help="verify archive checksum and readability")
    verify.add_argument("backup")
    verify.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    restore = commands.add_parser("restore", help="destructively restore a backup into a target database")
    restore.add_argument("backup")
    restore.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    restore.add_argument("--confirm-database", required=True)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("DATABASE_URL or --database-url is required")
    if args.command == "backup":
        result = create_backup(args.database_url, args.directory, args.keep)
        print(f"Verified PostgreSQL backup created: {result}")
        return 0
    if args.command == "verify":
        valid = verify_backup(args.backup, args.database_url)
        print("PostgreSQL backup integrity: OK" if valid else "PostgreSQL backup integrity: FAILED")
        return 0 if valid else 1
    print("WARNING: this replaces objects in the target database. Stop the application first.")
    restore_backup(args.backup, args.database_url, confirm_database=args.confirm_database)
    print(f"Verified PostgreSQL backup restored to database: {_connection_options(args.database_url)[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
