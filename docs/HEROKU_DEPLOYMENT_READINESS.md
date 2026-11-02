# Heroku Deployment Readiness

**Status: blocked pending persistence and process-model work. No Heroku resources have been provisioned and no deployment has been performed.**

Heroku is the selected hosting target for The Peak Adventure. This document records what is already compatible, what is not, and the checks required before a deployment can safely hold real player data.

## Current repository facts

- `Procfile` declares `web: python main.py`.
- `main.py` reads the platform-provided `PORT` value for its aiohttp server.
- The same process currently starts Telegram long polling and the HTTP server.
- The game database is SQLite through `aiosqlite`; the configured path defaults to a local file.
- The automated backup loop creates SQLite snapshot files under the configured local backup directory.
- The Cloudflare Worker is the Mini App edge gateway; its `BACKEND_ORIGIN` must point to the HTTPS Python backend.
- The Mini App requires a public HTTPS `WEBAPP_URL` registered with BotFather.

## Deployment blockers

### 1. Persistent database

Heroku dyno filesystems are ephemeral and isolated. Local files are not a durable database and are not shared between dynos. The current SQLite database and local backup snapshots therefore cannot be treated as production persistence.

Required work:
- Introduce a PostgreSQL persistence implementation and explicit schema migrations.
- Audit SQLite-specific SQL and APIs, including placeholders, `PRAGMA`, `lastrowid`, row handling, transaction/savepoint semantics and locking.
- Preserve transaction atomicity and idempotency across all gameplay, economy, trading, guild and multiplayer operations.
- Add PostgreSQL integration tests and migration/rollback tests.
- Verify that concurrent requests and multiple application processes cannot duplicate rewards or corrupt state.

Do not attempt to solve this by setting `DATABASE_URL` alone. The current application is not a drop-in PostgreSQL application.

### 2. Durable backups and restore

The current backup loop writes local SQLite snapshots. The SQLite backup utility now takes an online consistent snapshot, runs an integrity check, flushes the verified file and directory metadata before/after atomic publication, rotates old snapshots, and refuses restore while WAL/SHM sidecars exist. These protections improve local snapshot integrity but do not make dyno-local files durable. Before production:
- Choose a durable backup destination or a database-native backup strategy.
- Encrypt and restrict access to backups.
- Verify backup integrity and perform a restore drill against a disposable database.
- Document retention, recovery point and recovery time expectations.
- Keep restore operations separate from normal web requests.

### 3. Bot polling and web process model

The current `web` process runs both Telegram polling and the aiohttp server. Do not scale this combined process to multiple dynos: each instance would start another polling loop, while the current in-process locks do not coordinate between dynos.

Before horizontal scaling:
- Separate Telegram polling into a dedicated worker process type.
- Keep the HTTP API in the web process.
- Use PostgreSQL transactions and database-level coordination for shared state.
- Validate graceful shutdown, restart behavior and duplicate-update handling.

A single combined dyno may be used only for a controlled, explicitly approved test after PostgreSQL and backup prerequisites are met. It is not a production scaling design.

### 4. Cloudflare and Telegram configuration

After the backend has been deployed and verified:
- Set Heroku config vars for `BOT_TOKEN`, `ADMIN_IDS`, and the HTTPS `WEBAPP_URL`.
- Set the Cloudflare Worker secret `BACKEND_ORIGIN` to the Heroku HTTPS origin only, without an API path.
- Set `WEBAPP_URL` to the public Cloudflare Worker URL.
- Register the Worker hostname as the Telegram Mini App domain with BotFather.
- Never place `BOT_TOKEN` in Cloudflare Worker variables or client-side assets.

### 5. Release verification

Required before a public launch:
- CI passes on the exact release commit.
- PostgreSQL migrations succeed on a clean database and on a representative upgraded database.
- Registration, class selection, state loading, exploration, battle, rewards, inventory, quests and world travel pass in a real Telegram bot.
- The Mini App passes Android Telegram WebView and browser/device QA with real initData.
- A dyno restart and redeploy preserve all player progress.
- Backup and restore are demonstrated against a test database.
- Duplicate and concurrent reward, trade, battle and multiplayer actions remain safe.
- Security and load testing are completed against a representative environment.
- Cloudflare-to-Heroku routing and health checks are verified.

## Runtime monitoring implemented in the application

- `/healthz` performs a live database probe and returns HTTP 503 when the database is unavailable.
- `/ops/metrics` requires valid Telegram initData from an ID in `ADMIN_IDS`. It exposes aggregate request/status counts, bounded route latency summaries, database probe state, and backup freshness/error state. It does not retain Telegram IDs or request payloads.
- The runtime monitor sends Telegram admin alerts when database availability or backup health changes, and sends recovery notices when those conditions clear.
- These counters and alert-transition states are in memory and reset when the process restarts. They are operational signals, not a durable monitoring history or an external alerting integration.
- Configure `ADMIN_IDS` to receive alerts. Before public production launch, connect Heroku log drains/metrics or an external monitoring provider and verify alert delivery with a controlled failure drill.

## Intended deployment shape

| Component | Target | Current status |
|---|---|---|
| Python HTTP API | Heroku web dyno | Existing combined bot/API process; not deployed |
| Telegram bot polling | Dedicated Heroku worker after process split | Currently combined with web process |
| Player persistence | Heroku Postgres | Not implemented |
| Durable backups | Database-native or external object storage | Current backups are local files |
| Mini App static/API edge | Cloudflare Worker | Existing Worker; backend origin must be verified |
| Telegram Mini App | HTTPS Worker URL | Requires final backend and BotFather configuration |

## Cost and authorization boundary

- No Heroku app, dyno, database add-on or paid resource has been created by this work.
- Do not run provisioning, scaling or deployment commands until the owner explicitly authorizes the cost and action.
- Telegram Stars purchases remain disabled.
- The existing `render.yaml` is retained as a legacy artifact and is not the selected deployment target.

## Official Heroku references

- [Preparing a Codebase for Heroku Deployment](https://devcenter.heroku.com/articles/preparing-a-codebase-for-heroku-deployment)
- [Heroku Dynos](https://devcenter.heroku.com/articles/dynos)
- [The Procfile](https://devcenter.heroku.com/articles/procfile)
