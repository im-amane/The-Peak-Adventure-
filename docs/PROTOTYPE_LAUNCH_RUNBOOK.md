# Prototype Launch Runbook

## Purpose

This is the shortest safe path to a **controlled, playable prototype** of The Peak Adventure. It is not a production launch plan. The prototype uses one Python process for Telegram polling and the HTTP API, SQLite on a persistent disk, and the existing Cloudflare Worker as the public Mini App edge.

The existing game already contains the core gameplay journey. The immediate launch blockers are hosting configuration, the Telegram bot secret, and connecting the Worker to the backend.

## Prototype scope

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
- Production-scale load certification, multi-dyno operation, and public launch.

## Hosting shape

The repository's `render.yaml` defines a single Docker web service in Singapore with:
- Render Starter web service plan and a 1 GB persistent disk mounted at `/data`.
- SQLite database at `/data/peak_adventure.db`.
- Local SQLite snapshots at `/data/backups` when SQLite is selected.
- PostgreSQL logical backups at `/data/postgres_backups` when `DATABASE_URL` is selected; the container includes `pg_dump` and `pg_restore`.
- `/healthz` health check.
- Telegram Stars explicitly disabled.

**Cost note:** Render Starter and its persistent disk are paid resources. Review the current price in Render before applying the Blueprint. Do not switch this prototype to a free ephemeral filesystem: player progress would be lost on restart or redeploy.

## Pre-deploy configuration check

Run the read-only preflight in the same environment where the bot will start:

```bash
python scripts/launch_preflight.py
```

It checks required Telegram token and HTTPS Mini App URL configuration, admin IDs, database path/URL, server port, backup settings, and payment mode. It never prints secret values and does not connect to or modify live services. Resolve every error before deployment; review warnings before accepting payments or opening the prototype to players.

## Deploy steps

1. In Render, choose **New → Blueprint** and connect `im-amane/The-Peak-Adventure-` on branch `main`.
2. Review the Blueprint plan and persistent-disk cost before creating resources. The Blueprint uses the repository's `render.yaml`.
3. Set the secret `BOT_TOKEN` to the token from BotFather. Never put it in GitHub, this document, Cloudflare, or chat.
4. Set `ADMIN_IDS` to the owner's Telegram numeric ID (comma-separated if more than one admin).
5. Set `WEBAPP_URL` to `https://peak-adventure-edge.thepeakadventure.workers.dev`.
6. Keep `ENABLE_TELEGRAM_STARS=false`. Leave `DATABASE_URL` unset for this single-instance SQLite prototype.
7. Wait for the Render deploy to finish. Copy the exact HTTPS service origin shown by Render, without a path.
8. In the Cloudflare dashboard, open Worker `peak-adventure-edge` → Settings → Variables and Secrets. Add `BACKEND_ORIGIN` as a **secret** containing that exact Render origin, for example `https://your-service.onrender.com`. Do not use a placeholder.
9. Confirm the Worker hostname is registered as the Telegram Mini App domain with BotFather, then open the bot and press `/start`.

## Smoke test

Run these checks in order:

1. Open `https://YOUR-RENDER-SERVICE.onrender.com/healthz`. It must return HTTP 200 with `{"ok":true,"service":"peak-adventure","database":"ok"}`.
2. In Telegram, send `/start`; registration and class selection must complete.
3. Open the Mini App from the bot menu. The hero profile, HP, XP, coins, and current world must load.
4. Move using touch controls, approach a monster, start the encounter, and complete one battle.
5. Confirm the server-reported rewards and inventory update.
6. Close and reopen the Mini App; the same player progress must remain.
7. Restart the Render service once and repeat the state check. The database file must remain on `/data`.

Do not call the prototype live-tested until these steps have actually passed on the real Telegram bot and Android Telegram client.

## Prototype limitations and safety

- Keep exactly one Render instance. The bot polling loop and HTTP API share one process; multiple instances would create competing Telegram polling loops.
- SQLite is acceptable only for this controlled, single-instance prototype on the mounted persistent disk. Do not use it as the multi-instance or production database.
- The scheduled backup loop writes verified SQLite or PostgreSQL backups to the configured local persistent disk. PostgreSQL archives include SHA-256 sidecars and are checked with `pg_restore --list` before publication; retention is controlled by `POSTGRES_BACKUP_RETENTION`. CI runs a real PostgreSQL dump-and-restore rehearsal against two disposable databases and verifies restored rows. This validates the backup tooling, not the live service recovery procedure. Local backups are still not off-site disaster recovery; export and securely retain production backups independently.
- Do not collect payments. Telegram Stars are disabled.
- Do not use real customer/player data or announce a public launch until production persistence, external backups, security, concurrency, restart, and load checks are complete.
- The Worker forwards only routes in its explicit allowlist. The Mini App matchmaking route is included in the current prototype patch and covered by a regression test.


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
- PostgreSQL: pass it to `postgres_backup.restore_backup(downloaded_path, disposable_database_url, confirm_database=exact_database_name)`.

Never point a restore rehearsal at the live application database. For PostgreSQL, the downloaded custom-format archive must also have its adjacent `.sha256` sidecar available if using the existing `verify_backup`/restore helper; off-site object metadata verifies the downloaded bytes, but does not replace the archive's local sidecar. CI covers the download checksum path with a mocked S3 client; a real provider download and disposable-database restore remain operational checks.
