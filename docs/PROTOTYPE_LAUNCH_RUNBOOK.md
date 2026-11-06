# Prototype Launch Runbook

## Purpose

This runbook defines the controlled, playable prototype acceptance scope for The Peak Adventure. It is not a production launch certification. The runtime is one Python process for Telegram long polling and the HTTP API, SQLite on a persistent Railway volume, and the existing Cloudflare Worker as the public Mini App edge.

The Railway infrastructure definition, setup commands, environment variables, volume mount, Cloudflare connection, and deployment checklist are maintained in [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md). Use that guide as the source of truth for hosting configuration.

## Prototype acceptance scope

Must work:
1. Telegram bot starts, registers a player, and lets them select Knight, Mage, Archer, or Berserker.
2. The Mini App opens from Telegram and loads the authenticated player's saved state.
3. The player can move around the map, trigger a valid encounter, and complete a server-validated battle.
4. Victory/defeat, XP, coins, HP, inventory, and battle state persist.
5. Basic equipment, potions, quests, and world travel work.
6. Closing and reopening the Mini App does not reset the player's progress.

Defer:
- Production sprite sheets and complete idle/run animation sets.
- Larger connected maps and advanced traversal.
- Full social, guild, matchmaking, auction, and trading polish.
- Premium purchases and Telegram Stars.
- Production-scale load certification, multi-replica operation, and public launch.

## Pre-deploy configuration check

Run the read-only preflight in the same environment where the bot will start:

```bash
python scripts/launch_preflight.py
```

It checks required Telegram token and HTTPS Mini App URL configuration, admin IDs, database path/URL, server port, backup settings, and payment mode. It never prints secret values or connects to live services. Resolve every error before deployment; review warnings before accepting payments or opening the prototype to players.

## Smoke test

Run these checks after deploying with [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md):

1. Open the real Railway service's `/healthz` endpoint. It must return HTTP 200 with `{"ok":true,"service":"peak-adventure","database":"ok"}`.
2. In Telegram, send `/start`; registration and class selection must complete.
3. Open the Mini App from the bot menu. The hero profile, HP, XP, coins, and current world must load.
4. Move using touch controls, approach a monster, start the encounter, and complete one battle.
5. Confirm the server-reported rewards and inventory update.
6. Close and reopen the Mini App; the same player progress must remain.
7. Restart the Railway service once and repeat the state check. The database file must remain on the mounted `/data` volume.

Do not call the prototype live-tested until these steps have actually passed on the real Telegram bot and Android Telegram client.

## Prototype limitations and safety

- Keep exactly one Railway replica. The bot polling loop and HTTP API share one process; multiple instances would create competing Telegram polling loops.
- SQLite is acceptable only for this controlled, single-instance prototype on the mounted persistent volume. Do not use it as the multi-instance or production database.
- The scheduled backup loop writes verified SQLite or PostgreSQL backups to the configured local persistent volume. PostgreSQL archives include SHA-256 sidecars and are checked with `pg_restore --list` before publication; retention is controlled by `POSTGRES_BACKUP_RETENTION`. CI runs a real PostgreSQL dump-and-restore rehearsal against two disposable databases and verifies restored rows. This validates backup tooling, not the live service recovery procedure. Local backups are not off-site disaster recovery; export and securely retain production backups independently.
- Do not collect payments. Telegram Stars are disabled.
- Do not use real customer/player data or announce a public launch until production persistence, external backups, security, concurrency, restart, and load checks are complete.
- The Worker forwards only routes in its explicit allowlist. The Mini App matchmaking route is included in the current prototype and covered by a regression test.

## Optional S3-compatible off-site backups

The scheduler can export each completed local SQLite or PostgreSQL backup to an S3-compatible object store. Configure these environment variables in the hosting provider, not in Git:

- `OFFSITE_BACKUP_BUCKET`: required bucket name to enable export.
- `OFFSITE_BACKUP_REGION`: AWS-style region; defaults to `AWS_REGION` or `us-east-1`.
- `OFFSITE_BACKUP_PREFIX`: object-key prefix; defaults to `peak-adventure-backups`.
- `OFFSITE_BACKUP_ENDPOINT_URL`: optional endpoint for an S3-compatible provider.
- `OFFSITE_BACKUP_KMS_KEY_ID`: optional customer-managed KMS key. Without it, uploads request S3-managed AES-256 encryption.
- Credentials are resolved through boto3's standard credential chain. Prefer a scoped role or dedicated access key limited to writing backups in this bucket. Never commit credentials.

The exporter uploads only after the local backup provider has completed its integrity checks. It attaches a SHA-256 checksum as object metadata and never deletes remote objects. Configure object lifecycle/retention and access controls in the storage provider. If upload fails, the local backup remains and the scheduled backup operation reports failure; monitor logs and alert on that failure.

Preflight warns when no bucket is configured. When configured, a restore rehearsal is still required. CI mocks the S3 client; it does not contact a real cloud account.

The `offsite_backup.download_backup(bucket=..., key=..., destination=...)` helper checks the object's SHA-256 metadata and content length, downloads to a temporary file, and atomically publishes it only after verification. A missing checksum or mismatch leaves an existing destination untouched. After download, rehearse restoration only against an isolated disposable target:
- SQLite: pass the downloaded file to `db_backup.restore_backup(downloaded_path, disposable_database_path)`.
- PostgreSQL: download it with `write_checksum_sidecar=True`, then pass it to `postgres_backup.restore_backup(downloaded_path, disposable_database_url, confirm_database=exact_database_name)`.

Never point a restore rehearsal at the live application database. For PostgreSQL, the downloaded custom-format archive must also have its adjacent `.sha256` sidecar available if using the existing `verify_backup`/restore helper; off-site object metadata verifies the downloaded bytes, but does not replace the archive's local sidecar. CI covers the download checksum path with a mocked S3 client; a real provider download and disposable-database restore remain operational checks.
