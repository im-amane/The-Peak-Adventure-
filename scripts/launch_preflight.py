"""Read-only preflight checks for a controlled Telegram Mini App launch.

This utility never connects to Telegram, Cloudflare, Render, or a database. It
validates local environment configuration without printing secret values.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


def inspect_environment(environ: dict[str, str] | None = None) -> list[dict[str, str]]:
    env = os.environ if environ is None else environ
    issues: list[dict[str, str]] = []

    def add(code: str, severity: str, message: str) -> None:
        issues.append({"code": code, "severity": severity, "message": message})

    token = str(env.get("BOT_TOKEN", "")).strip()
    if not token:
        add("bot_token_missing", "error", "BOT_TOKEN is required.")
    elif "replace_with" in token.lower() or token.startswith("123456:"):
        add("bot_token_placeholder", "error", "BOT_TOKEN still looks like the example placeholder.")

    webapp_url = str(env.get("WEBAPP_URL", "")).strip()
    if not webapp_url:
        add("webapp_url_missing", "error", "WEBAPP_URL is required to expose the Mini App in Telegram.")
    else:
        try:
            parsed = urlsplit(webapp_url)
            valid = parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None and parsed.password is None and not parsed.fragment
        except ValueError:
            valid = False
        if not valid:
            add("webapp_url_invalid", "error", "WEBAPP_URL must be a valid public HTTPS URL without credentials or a fragment.")

    raw_port = str(env.get("PORT", env.get("WEB_PORT", "8080"))).strip()
    try:
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        add("web_port_invalid", "error", "PORT/WEB_PORT must be an integer from 1 to 65535.")

    admin_ids = str(env.get("ADMIN_IDS", "")).strip()
    if not admin_ids:
        add("admin_ids_missing", "warning", "ADMIN_IDS is empty; operational admin alerts and admin commands will not have a recipient.")
    else:
        values = [value.strip() for value in admin_ids.split(",")]
        if any(not re.fullmatch(r"[1-9][0-9]*", value) for value in values):
            add("admin_ids_invalid", "error", "ADMIN_IDS must contain comma-separated positive Telegram numeric IDs.")

    stars_enabled = str(env.get("ENABLE_TELEGRAM_STARS", "false")).strip().lower()
    if stars_enabled in {"1", "true", "yes", "on"}:
        add("telegram_stars_enabled", "warning", "Telegram Stars payments are enabled; verify payment ownership, refunds, and launch policy before accepting payments.")

    database_url = str(env.get("DATABASE_URL", "")).strip()
    if database_url:
        try:
            parsed_db = urlsplit(database_url)
            valid_db = parsed_db.scheme in {"postgres", "postgresql"} and bool(parsed_db.hostname) and bool(parsed_db.username) and bool(parsed_db.path.strip("/"))
        except ValueError:
            valid_db = False
        if not valid_db:
            add("database_url_invalid", "error", "DATABASE_URL must be a valid PostgreSQL URL with host, username, and database name.")
    else:
        database_path = str(env.get("DATABASE_PATH", "")).strip()
        if not database_path:
            add("database_path_missing", "error", "Set DATABASE_PATH for persistent SQLite storage or configure DATABASE_URL for PostgreSQL.")
        elif not Path(database_path).is_absolute():
            add("database_path_not_absolute", "warning", "DATABASE_PATH is relative; use an absolute path on a persistent mounted volume for hosted deployments (for example: /data/peak_adventure.db).")

    backup_interval = str(env.get("BACKUP_INTERVAL_SECONDS", "21600")).strip()
    try:
        if int(backup_interval) < 3600:
            raise ValueError
    except (TypeError, ValueError):
        add("backup_interval_invalid", "error", "BACKUP_INTERVAL_SECONDS must be at least 3600 seconds.")

    offsite_bucket = str(env.get("OFFSITE_BACKUP_BUCKET", "")).strip()
    if not offsite_bucket:
        add("offsite_backup_not_configured", "warning", "Backups remain on local storage; configure OFFSITE_BACKUP_BUCKET and credentials for independent off-site copies.")
    elif not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", offsite_bucket):
        add("offsite_backup_bucket_invalid", "error", "OFFSITE_BACKUP_BUCKET must be a valid S3 bucket name.")
    else:
        endpoint = str(env.get("OFFSITE_BACKUP_ENDPOINT_URL", "")).strip()
        if endpoint:
            try:
                parsed_endpoint = urlsplit(endpoint)
                valid_endpoint = parsed_endpoint.scheme in {"https", "http"} and bool(parsed_endpoint.hostname) and parsed_endpoint.username is None and parsed_endpoint.password is None
            except ValueError:
                valid_endpoint = False
            if not valid_endpoint:
                add("offsite_backup_endpoint_invalid", "error", "OFFSITE_BACKUP_ENDPOINT_URL must be an HTTP(S) endpoint without embedded credentials.")
        region = str(env.get("OFFSITE_BACKUP_REGION", env.get("AWS_REGION", "us-east-1"))).strip()
        if not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", region):
            add("offsite_backup_region_invalid", "error", "OFFSITE_BACKUP_REGION must be a valid AWS-style region identifier.")
        add("offsite_restore_rehearsal_required", "warning", "Off-site upload is configured, but periodically download an archived object and rehearse a restore before production use.")

    backup_retention = str(env.get("BACKUP_RETENTION", "7")).strip()
    try:
        if int(backup_retention) < 1:
            raise ValueError
    except (TypeError, ValueError):
        add("backup_retention_invalid", "error", "BACKUP_RETENTION must be a positive integer.")

    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        database_path = str(env.get("DATABASE_PATH", "peak_adventure.db")).strip()
        default_postgres_dir = str(Path(database_path).parent / "postgres_backups")
        postgres_backup_dir = str(env.get("POSTGRES_BACKUP_DIR", default_postgres_dir)).strip()
        if not postgres_backup_dir:
            add("postgres_backup_dir_missing", "error", "POSTGRES_BACKUP_DIR must name a directory for PostgreSQL logical backups.")
        elif not Path(postgres_backup_dir).is_absolute():
            add("postgres_backup_dir_not_absolute", "warning", "POSTGRES_BACKUP_DIR is relative; use a persistent mounted path for hosted deployments.")
        postgres_retention = str(env.get("POSTGRES_BACKUP_RETENTION", backup_retention)).strip()
        try:
            if int(postgres_retention) < 1:
                raise ValueError
        except (TypeError, ValueError):
            add("postgres_backup_retention_invalid", "error", "POSTGRES_BACKUP_RETENTION must be a positive integer.")

    return issues


def main() -> int:
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description="Validate launch configuration without exposing secrets.")
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args()
    load_dotenv()
    issues = inspect_environment()
    errors = [issue for issue in issues if issue["severity"] == "error"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    if args.json:
        print(json.dumps({"ok": not errors and (not args.strict or not warnings), "issues": issues}, indent=2))
    else:
        if not issues:
            print("Launch preflight passed. Required configuration is present.")
        else:
            for issue in issues:
                print(f"[{issue['severity'].upper()}] {issue['code']}: {issue['message']}")
            print(f"Preflight: {len(errors)} error(s), {len(warnings)} warning(s).")
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
