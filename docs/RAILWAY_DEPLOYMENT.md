# Railway Deployment Runbook

This repository is prepared for Railway's current Infrastructure as Code workflow and its existing root Dockerfile.

## What the repository defines

- GitHub source: `im-amane/The-Peak-Adventure-`, branch `main`.
- Docker build: root `Dockerfile` (Python 3.11, PostgreSQL client tools, `python main.py`).
- One Singapore replica only: Telegram long polling and SQLite currently run in one process.
- Persistent Railway volume: 1 GB mounted at `/data`.
- SQLite database: `/data/peak_adventure.db`.
- Health check: `/healthz`, with a 300-second startup timeout.
- Cloudflare Worker remains the public Mini App edge.

The Railway project definition is `.railway/railway.ts`. It is applied explicitly through the Railway CLI. Railway does not execute this file as part of each Docker build.

## Create and apply the Railway project

1. Create or sign in to your account at [Railway](https://railway.com/).
2. Install the Railway CLI using Railway's current installation instructions.
3. From the repository root, install the IaC SDK:

   ```bash
   npm install --prefix .railway
   ```

4. Authenticate and link the local repository to the Railway project/environment you intend to use:

   ```bash
   railway login
   railway link
   ```

   If the project does not exist yet, create it in the Railway dashboard first. Select the intended environment when linking.

5. Preview the infrastructure changes:

   ```bash
   railway config plan
   ```

   Confirm the plan creates one service named `peak-adventure`, one volume named `peak-adventure-data`, and exactly one replica in `asia-southeast1-eqsg3a`. Review any proposed deletion or replacement carefully. Do not apply a plan that would destroy an existing volume containing player data.

6. Apply only after reviewing the plan:

   ```bash
   railway config apply
   ```

This creates or manages the service and volume described by `.railway/railway.ts`. It does not create secrets or a public domain.

## Required secret variables

In the Railway service's **Variables** tab, add:

| Variable | Value |
| --- | --- |
| `BOT_TOKEN` | Real Telegram bot token from BotFather |
| `ADMIN_IDS` | Owner's numeric Telegram user ID; comma-separated for multiple admins |

Never place either value in GitHub, this config file, source code, or chat. Do not add `DATABASE_URL` for the initial SQLite deployment.

The IaC file already sets the non-secret runtime values:

| Variable | Value |
| --- | --- |
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

Railway injects `PORT`; the application reads it automatically. Do not set a fixed `PORT` unless Railway support specifically requires it. The configured co-owner default is retained in the application; change `CO_OWNER_IDS` only if needed.

## Connect the Cloudflare Mini App gateway

1. In Railway, open the service's **Networking** settings and generate a public domain.
2. Copy the exact HTTPS origin Railway assigns, without a path or trailing route.
3. In Cloudflare, open Worker `peak-adventure-edge` → **Settings** → **Variables and Secrets**.
4. Set `BACKEND_ORIGIN` as a secret to that exact Railway origin.
5. Keep `WEBAPP_URL` set to the existing Worker URL and confirm its hostname is registered with BotFather as the Telegram Mini App domain.

Do not use a placeholder Railway domain. Do not put `BOT_TOKEN` in Cloudflare.

## Deploy and verify

1. Trigger the initial deployment from the Railway service after variables are set.
2. Confirm the build uses the repository's root `Dockerfile`.
3. Inspect runtime logs. The bot must initialize the database, start the HTTP listener on Railway's injected port, and begin Telegram polling.
4. Open `https://YOUR-REAL-RAILWAY-DOMAIN/healthz`. Expected response is HTTP 200 with `{"ok":true,"service":"peak-adventure","database":"ok"}`.
5. In Telegram, send `/start`, register a test player, and select a class.
6. Open the Mini App and verify the player profile, map, encounter, battle result, rewards, and saved progress.
7. Restart/redeploy once and confirm the same player progress remains. Confirm backup files appear under `/data/backups`.

Do not describe the game as live-tested until these checks pass against the real Telegram bot and Android Telegram client.

## Important operating limits

- Keep exactly one replica and do not run another process with the same bot token. Multiple Telegram polling instances compete for updates; the current SQLite setup is single-instance only.
- The persistent volume is essential. Without it, player progress stored in SQLite is not durable across replacement deployments.
- Railway health checks gate deployment activation; they are not continuous uptime monitoring.
- Backups on the same volume are not disaster recovery. Configure and test an independent off-site backup destination before storing valuable player progress.
- Keep Telegram Stars disabled. Do not enable payments or announce a public launch until restore, security, concurrency, restart, and load checks are complete.
- Railway resources and volume storage may incur charges. Review the current plan and usage before applying paid resources.

## Why this uses Railway IaC

Railway has deprecated legacy `railway.json` / `railway.toml` Config as Code for new services. This repository uses the supported TypeScript Infrastructure as Code file at `.railway/railway.ts`. Use `railway config plan` before every `railway config apply`; the CLI shows the proposed changes and waits for confirmation.
