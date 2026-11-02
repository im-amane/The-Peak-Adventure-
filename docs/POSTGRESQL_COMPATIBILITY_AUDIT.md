# PostgreSQL Compatibility Audit

**Status updated:** 2026-11-02  
**Scope:** 30 top-level Python source files, service schema initialization, main Mini App gameplay reads, and SQLite-to-PostgreSQL migration tooling.

This is an engineering status report. PostgreSQL compatibility tests do not mean the production runtime has switched databases.

## Executive finding

The project has a PostgreSQL 16 adapter, dialect-aware full-game schema initialization, SQLite/PostgreSQL schema-parity tests, broad service-level PostgreSQL integration coverage, selected main gameplay smoke tests, and a guarded SQLite-to-PostgreSQL data migration utility. PR #93 has now wired explicit runtime selection through `DATABASE_URL`; SQLite remains the default when that variable is unset, and PostgreSQL connection/schema failures stop startup rather than falling back silently.

**PostgreSQL runtime support is implemented but is not production-approved or production-verified.** The active deployment remains unchanged; no live data migration, Heroku provisioning, or deployment has occurred.

## Verified progress

| Area | Verified status |
|---|---|
| PostgreSQL adapter | Supports qmark conversion, dict rows, transaction state, nested savepoints, `BEGIN IMMEDIATE` normalization, `INSERT OR IGNORE` normalization, and explicit generated IDs |
| Core schema | `init_core_schema(connection)` creates/upgrades core tables for SQLite and PostgreSQL; Telegram user/chat identifiers use PostgreSQL `BIGINT` |
| Full schema bootstrap | `init_game_schema(connection)` initializes the ordered set of game service schemas on either backend |
| Schema parity | CI initializes a full in-memory SQLite schema and an isolated PostgreSQL schema, then compares table and column names |
| Main gameplay smoke tests | PostgreSQL tests exercise `miniapp_state()`, large Telegram IDs, quest/achievement upserts, and idempotent daily rewards |
| Combat and guild SQL | PostgreSQL tests cover portable HP/cooldown updates and capped guild mission progress |
| Data migration utility | Dry-run, bounded batch copy, FK dependency ordering, identity sequence reset, rollback and non-empty target refusal are tested against PostgreSQL 16 |
| Runtime database | `DATABASE_URL` explicitly selects PostgreSQL; otherwise SQLite is selected. The deployed/current environment has not been switched |
| Backup/restore | Existing `db_backup.py` is SQLite-specific; a PostgreSQL backup/restore and recovery procedure is still required |
| Deployment | No Heroku deployment or live Telegram/device QA has been performed |

## Remaining compatibility and release blockers

### 1. Runtime connection and lifecycle

- `main.init_db()` selects Psycopg when `DATABASE_URL` is explicitly set and otherwise retains SQLite. PostgreSQL startup errors fail closed and close a partially initialized connection.
- Backend-selection and failure-cleanup tests cover the runtime selection path; CI also runs the PostgreSQL adapter and service integration suites against PostgreSQL 16.
- The app still owns one global connection per process and uses process-local locks. Cross-process transaction/locking behavior must be audited before separate web/worker processes or horizontal scaling.
- The runtime deliberately disables the SQLite snapshot loop when PostgreSQL is selected. The operations monitor reports that no durable PostgreSQL backup provider is configured.

### 2. Backup, restore and recovery

- `db_backup.py` uses SQLite's online backup API and `PRAGMA integrity_check`; it is never run against a PostgreSQL connection.
- PostgreSQL backup/restore is not implemented. The runtime reports this gap rather than writing a misleading SQLite file.
- The current migration utility does not create a source backup, migrate triggers/views, or prove a restore.
- A PostgreSQL backup strategy, durable backup destination, restore rehearsal, retention policy, and rollback runbook are still required.
- Do not migrate a production database until a recoverable backup has been verified.

### 3. Migration tooling limits

The script `scripts/migrate_sqlite_to_postgres.py`:

- Defaults to read-only audit mode.
- Requires the PostgreSQL target schema to be initialized separately with `main.init_game_schema(connection)`.
- Checks table/column compatibility and row counts.
- Requires an empty PostgreSQL target before applying.
- Copies rows in bounded batches and orders tables by foreign-key dependencies.
- Resets identity/serial sequences after copying explicit IDs.
- Rolls back the data-copy transaction on failure.
- Requires `--apply --confirm MIGRATE` in CLI mode.

It is a one-way data-copy tool, not a live replication or zero-downtime migration system. It does not provision PostgreSQL, alter app runtime configuration, or execute itself against production. Its schema audit compares names and required-column availability; data-type conversion edge cases still need a real-source dry run.

### 4. SQL and service behavior

- The adapter intentionally supports a defined subset of SQLite's async connection/cursor surface.
- SQLite-specific conflict, date, schema-introspection and scalar SQL behavior must continue to be reviewed explicitly.
- Current PostgreSQL integration tests cover many service transactions and concurrency paths, but they are not a substitute for real Telegram and browser acceptance testing.
- Schema-parity coverage compares table and column names; it does not prove identical indexes, constraints, defaults, triggers or runtime semantics.

### 5. Heroku release gates

- Keep the current SQLite runtime until the PostgreSQL runtime path and recovery plan are approved.
- Separate Telegram polling from the web process only after shared persistent storage is ready.
- Configure Heroku secrets and database URL only after the runtime switch is explicitly authorized.
- Verify HTTPS/Cloudflare routing, worker/web health checks, restart behavior, Telegram bot polling, Android WebView, multiplayer concurrency, security and load.
- No Heroku add-on, paid resource, deployment or Telegram Stars purchase has been enabled.

## Recommended next sequence

1. Complete a dry-run against a representative, backed-up SQLite database and review all schema/count/type warnings.
2. Select and implement a durable PostgreSQL backup destination plus verified restore rehearsal; the storage provider must be chosen before this can be completed safely.
3. Expand PostgreSQL smoke coverage to the remaining main-command and Mini App mutation paths, and finish the SQLite-specific SQL/transaction audit.
4. Audit all cross-process locking and idempotency assumptions before adding separate web and Telegram worker process roles.
5. Run browser/device, Telegram, multiplayer concurrency, security and load acceptance tests.
6. Only after explicit approval, schedule a controlled data migration and Heroku release.

## Safety boundary

- SQLite remains the default and active prototype backend unless `DATABASE_URL` is explicitly configured for a process.
- No live SQLite data has been migrated.
- No production environment has been switched to PostgreSQL.
- No Heroku resource has been provisioned and no deployment has occurred.
- Telegram Stars purchases remain disabled.
