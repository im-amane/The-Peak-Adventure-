# Railway Deployment Runbook

This guide deploys the current single-process Telegram bot + HTTP API prototype to Railway.

## Current deployment shape

- Source: `im-amane/The-Peak-Adventure-`, branch `main`.
- Runtime: existing `Dockerfile` (Python 3.11, PostgreSQL client tools, `python main.py`).
- HTTP listener: binds to `0.0.0.0` and reads Railway's injected `PORT`.
- Health check: `/healthz`.
- Telegram updates: long polling in the same process as the HTTP API.
- Database for the first Railway deployment: SQLite on a Railway Volume mounted at `/data`.
- Keep exactly **one replica**. Multiple replicas would compete for Telegram polling and are not supported by this SQLite prototype.

## Create the Railway service

1. Open [Railway](https://railway.com/) and create a project.
2. Choose **Deploy from GitHub Repo** and connect `im-amane/The-Peak-Adventure-`.
3. Select branch `main`. Railway will detect the repository's root `Dockerfile`; do not replace its start command.
4. In the service settings, set the health check path to `/healthz` and allow up to 300 seconds for startup.
5. Keep the service at one replica. Do not enable horizontal scaling.
6. In **Volumes**, create a persistent volume and mount it at `/data`. Do not deploy this SQLite setup without the volume: Railway's container filesystem is not a durable database location.
7. In **Networking**, generate a public domain after the first successful deployment.

## Service variables

Add these in the Railway service's **Variables** tab. Put secret values directly into Railway; never commit them to GitHub or paste them into source files.

| Variable | Value |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token from BotFather |
| `ADMIN_IDS` | Owner's numeric Telegram user ID; comma-separated for multiple admins |
| `WEBAPP_URL` | `https://peak-adventure-edge.thepeakadventure.workers.dev` |
| `DATABASE_PATH` | `/data/peak_adventure.db` |
| `BACKUP_DIR` | `/data/backups` |
| `BACKUP_INTERVAL_SECONDS` | `21600` |
| `BACKUP_RETENTION` | `7` |
| `POSTGRES_BACKUP_DIR` | `/data/postgres_backups` |
| `POSTGRES_BACKUP_RETENTION` | `7` |
| `WEB_HOST` | `0.0.0.0` |
| `ENABLE_TELEGRAM_STARS` | `false` |
| `LOG_LEVEL` | `INFO` |

The app already reads Railway's injected `PORT`; do not hard-code a port or override `PORT` unless Railway specifically requires it.

For this initial SQLite prototype, **leave `DATABASE_URL` unset**. The application treats a configured `DATABASE_URL` as an explicit PostgreSQL selection and will fail startup if that database is unavailable. Do not attach PostgreSQL or run the SQLite-to-PostgreSQL migration as part of a normal deploy. That migration has a separate guarded runbook and requires a verified backup and explicit maintenance approval.

`CO_OWNER_IDS` currently has a code default. Set it in Railway only if the co-owner list needs to be changed.

## Connect the Mini App edge

After Railway generates the service domain:

1. Copy the exact HTTPS origin, for example `https://your-service.up.railway.app` (use the real domain Railway assigns).
2. In Cloudflare, open Worker `peak-adventure-edge` → **Settings** → **Variables and Secrets**.
3. Set `BACKEND_ORIGIN` as a secret to the exact Railway origin, with no trailing path.
4. Keep the Mini App's public URL in `WEBAPP_URL` and ensure its hostname is registered with BotFather as the Telegram Mini App domain.

Do not put a placeholder Railway domain into Cloudflare.

## Deploy and verify

1. Trigger the first deployment from Railway.
2. Check the deployment build and runtime logs. Startup must complete without a missing-token, database, or schema error.
3. Open `https://YOUR-REAL-RAILWAY-DOMAIN/healthz`. Expected response: HTTP 200 with `{"ok":true,"service":"peak-adventure","database":"ok"}`.
4. In Telegram, send `/start`, register a test player, and select a class.
5. Open the Mini App and verify the profile, map, encounter, battle result, rewards, and saved progress.
6. Restart/redeploy the service and confirm the same player progress remains. Confirm backups are written under `/data`.

Do not describe the game as live-tested until these checks have passed against the real Telegram bot and Android Telegram client.

## Important prototype limits

- This is a controlled, single-instance prototype, not production certification.
- Railway's persistent volume is required for SQLite durability. Keep one replica and do not run a second copy of the bot against the same bot token.
- Local backups on the same volume are not off-site disaster recovery. Configure and test an independent backup destination before storing valuable player progress.
- Telegram Stars remain disabled. Do not enable payments or invite public players until security, restore, concurrency, restart, and load checks are complete.
- Railway resources may incur charges. Review the current Railway plan, resource usage, and volume pricing before creating or scaling paid resources.
