# Heroku Deployment Readiness (Historical)

**This document is retained for reference only. Heroku is not the selected hosting target.** The controlled playable prototype currently targets the single-instance Render Blueprint in `render.yaml`; follow [PROTOTYPE_LAUNCH_RUNBOOK.md](PROTOTYPE_LAUNCH_RUNBOOK.md) for that path. The README records the longer-term production blockers.

No Heroku resources have been provisioned and no Heroku deployment has been performed.

## Historical Heroku compatibility notes

- `Procfile` declares `web: python main.py`.
- `main.py` reads the platform-provided `PORT` value for its aiohttp server.
- The same process currently starts Telegram long polling and the HTTP server. Do not scale this combined process to multiple dynos.
- SQLite is the default when `DATABASE_URL` is unset. Setting `DATABASE_URL` selects the Psycopg 3 PostgreSQL adapter. Runtime selection is implemented, but full production PostgreSQL compatibility and concurrency safety have not been certified.
- The Cloudflare Worker is the Mini App edge gateway; its `BACKEND_ORIGIN` must point to the HTTPS Python backend.
- The Mini App requires a public HTTPS `WEBAPP_URL` registered with BotFather.

## Current backup implementation

The earlier statement that PostgreSQL backup automation was missing is obsolete.

- `backup_scheduler.py` dispatches scheduled backups according to the active database dialect.
- SQLite uses the existing online snapshot utility.
- PostgreSQL uses `postgres_backup.py` to create custom-format `pg_dump` archives, verify archive readability with `pg_restore --list`, publish SHA-256 sidecars, and rotate retained local backups.
- The Docker image installs PostgreSQL client tools for this workflow.
- The launch preflight validates PostgreSQL backup directory and retention configuration.

**Remaining backup blocker:** scheduled backups currently land on the configured local filesystem/persistent disk. Off-site storage, encryption/access policy for exported archives, and a demonstrated restore drill against a disposable database are still required before production. A local backup on the same disk is not disaster recovery.

## Remaining production blockers

### 1. PostgreSQL validation and migrations

The PostgreSQL adapter is opt-in and covered by automated adapter tests, but this is not equivalent to production verification. Complete:
- A full audit of SQLite-specific SQL and APIs, including placeholders, `PRAGMA`, `lastrowid`, row handling, transaction/savepoint semantics and locking.
- Explicit, versioned schema migrations and migration/rollback tests.
- Integration tests against a representative PostgreSQL service.
- Atomicity, idempotency and cross-process coordination checks for gameplay, economy, trading, guild and multiplayer mutations.
- A clean-database and representative-upgrade validation.

Do not assume setting `DATABASE_URL` alone makes every application path production-safe.

### 2. Off-site backups and restore

Before production:
- Select a durable off-site backup destination or managed database backup strategy.
- Encrypt backups and restrict access.
- Export scheduled archives away from the application disk.
- Verify integrity and perform a restore drill against a disposable database.
- Document retention, recovery point and recovery time objectives.
- Keep restore operations separate from normal web requests.

### 3. Bot polling and web process model

The current process runs Telegram polling and the aiohttp server together. A single instance is required for the controlled prototype. Before horizontal scaling:
- Separate Telegram polling into a dedicated worker process type.
- Keep the HTTP API in the web process.
- Use database-level coordination and verify idempotency for group, guild, party and multi-account mutations.
- Validate graceful shutdown, restart behavior and duplicate-update handling.

### 4. Cloudflare and Telegram configuration

After the backend has been deployed and verified:
- Set backend secrets for `BOT_TOKEN` and `ADMIN_IDS`, and set the HTTPS `WEBAPP_URL`.
- Set the Cloudflare Worker secret `BACKEND_ORIGIN` to the backend HTTPS origin only, without an API path.
- Set `WEBAPP_URL` to the public Cloudflare Worker URL.
- Register the Worker hostname as the Telegram Mini App domain with BotFather.
- Never place `BOT_TOKEN` in Cloudflare Worker variables or client-side assets.

For the current Render prototype values and exact sequence, use the prototype runbook rather than this historical Heroku note.

### 5. Release verification

Required before a public launch:
- CI passes on the exact release commit.
- PostgreSQL migrations succeed on clean and upgraded databases.
- Registration, class selection, state loading, exploration, battle, rewards, inventory, quests and world travel pass in a real Telegram bot.
- The Mini App passes Android Telegram WebView and browser/device QA with real initData.
- A restart and redeploy preserve all player progress.
- Backup and restore are demonstrated against a test database.
- Duplicate and concurrent reward, trade, battle and multiplayer actions remain safe.
- Security and load testing are completed against a representative environment.
- Cloudflare-to-backend routing and health checks are verified.

## Runtime monitoring implemented in the application

- `/healthz` performs a live database probe and returns HTTP 503 when the database is unavailable.
- `/ops/metrics` requires valid Telegram initData from an ID in `ADMIN_IDS`. It exposes aggregate request/status counts, bounded route latency summaries, database probe state, and backup freshness/error state. It does not retain Telegram IDs or request payloads.
- The runtime monitor sends Telegram admin alerts when database availability or backup health changes, and sends recovery notices when those conditions clear.
- These counters and alert-transition states are in memory and reset when the process restarts. They are operational signals, not a durable monitoring history or an external alerting integration.
- Configure `ADMIN_IDS` to receive alerts. Before public production launch, connect host log drains/metrics or an external monitoring provider and verify alert delivery with a controlled failure drill.

## Cost and authorization boundary

- No Heroku app, dyno, database add-on or paid resource has been created by this work.
- Do not run provisioning, scaling or deployment commands until the owner explicitly authorizes the cost and action.
- Telegram Stars remain disabled by default.
- The current controlled prototype target is Render, defined by `render.yaml`; this file is not the active deployment guide.

## Official Heroku references

- [Preparing a Codebase for Heroku Deployment](https://devcenter.heroku.com/articles/preparing-a-codebase-for-heroku-deployment)
- [Heroku Dynos](https://devcenter.heroku.com/articles/dynos)
- [The Procfile](https://devcenter.heroku.com/articles/procfile)
