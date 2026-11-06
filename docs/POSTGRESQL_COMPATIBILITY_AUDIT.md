# PostgreSQL Compatibility Audit

**Status updated:** 2026-11-04  
**Scope:** PostgreSQL runtime adapter, schema initialization/parity, service integration tests, SQLite migration tooling, and backup/restore implementation.

This is an engineering status report. Passing PostgreSQL tests does not mean the live prototype has switched databases or that production recovery has been proven.

## Executive finding

The repository has a PostgreSQL 16 adapter, dialect-aware game schema initialization, SQLite/PostgreSQL schema-parity checks, service-level PostgreSQL integration tests, a guarded SQLite-to-PostgreSQL migration utility, and database-aware scheduled backups. `DATABASE_URL` explicitly selects PostgreSQL; SQLite remains the default when it is unset. PostgreSQL connection or schema initialization failures stop startup rather than silently falling back.

**PostgreSQL support is implemented and CI-tested, but is not production-approved or production-verified.** The documented prototype target remains a single Railway service using SQLite on a persistent disk. No live database migration, runtime database switch, or deployment has occurred.

## Verified progress

| Area | Verified status |
|---|---|
| PostgreSQL adapter | Supports qmark conversion, dict rows, transaction state, nested savepoints, `BEGIN IMMEDIATE` normalization, `INSERT OR IGNORE` normalization, and explicit generated IDs |
| Core and game schemas | Dialect-aware schema initialization for SQLite and PostgreSQL; Telegram user/chat identifiers use PostgreSQL `BIGINT` |
| Schema parity | CI initializes SQLite and PostgreSQL schemas and compares table/column structure; migration audit additionally checks selected keys, foreign keys, indexes, nullability, defaults, and type affinity |
| Service integration | PostgreSQL 16 CI covers adapter behavior, matchmaking, Mini App HTTP flows, and selected gameplay/service mutations |
| Migration utility | Read-only by default; guarded apply to an empty target, bounded batches, FK dependency ordering, sequence reset, and transaction rollback |
| SQLite backups | Online SQLite backup API with integrity checking and retention |
| PostgreSQL backups | `backup_scheduler.py` dispatches to logical `pg_dump` custom-format archives; checksums, archive readability verification, and local retention are implemented |
| PostgreSQL restore | Guarded `pg_restore` command verifies checksum/archive and requires exact target database-name confirmation; a real restore rehearsal is still outstanding |
| Runtime selection | `DATABASE_URL` selects PostgreSQL; otherwise SQLite is selected. No live environment has been switched |
| Hosting | `.railway/railway.ts` describes a single-instance Railway prototype with persistent disk; no live deployment or Telegram/device acceptance test has been performed |

## Remaining compatibility and release blockers

### 1. Runtime connection, lifecycle and concurrency

- `main.init_db()` selects Psycopg only when `DATABASE_URL` is explicitly configured. PostgreSQL startup failures fail closed.
- CI exercises PostgreSQL 16 adapter and selected service integration paths. This is not full production workload certification.
- The application currently combines Telegram polling and the HTTP API in one process. Keep the prototype to one instance; multiple instances could create competing Telegram polling loops.
- Player-scoped PostgreSQL actions use session advisory locks on dedicated lock connections. Group, guild, party, multi-account and other cross-entity workflows still need a complete cross-process locking and concurrency review before splitting processes or horizontal scaling.
- PostgreSQL is not the documented default for the initial Railway prototype. Do not switch the runtime merely because CI is green.

### 2. Backup, restore and disaster recovery

- The scheduled backup loop dispatches according to the active database dialect: SQLite snapshots use `db_backup.py`; PostgreSQL uses `postgres_backup.py`.
- PostgreSQL backups are custom-format logical archives. The backup utility writes SHA-256 sidecars, verifies archive readability with `pg_restore --list` before publication, and rotates local archives according to `POSTGRES_BACKUP_RETENTION`.
- The restore utility checks the archive and checksum, requires an exact database-name confirmation, and uses a single transaction. Restore replaces objects in the target database; it must only be rehearsed against a separate disposable database.
- The current Railway prototype configuration stores backups on the same persistent disk as the service. **This is local backup protection, not off-site disaster recovery.** Disk loss or account-level failure could affect both the database and its backups.
- Still required: choose an off-site storage provider, define encryption/key handling and access controls, export backups off the service disk, alert on failed/missed backups, and complete a documented restore rehearsal with measured recovery time.
- Do not migrate or accept production data until an independently stored backup has been restored successfully.

### 3. Migration tooling limits

The script `scripts/migrate_sqlite_to_postgres.py`:

- Defaults to read-only audit mode and requires an already initialized PostgreSQL target schema.
- Compares schema compatibility, including type affinity, nullability, default availability, generated-key behavior, primary keys, foreign-key mappings/actions, CHECK constraint counts, and selected index signatures.
- Reports source/target row counts and refuses apply when the target is not empty or required schema checks fail.
- Copies rows in bounded batches ordered by foreign-key dependencies, resets identity/serial sequences, and rolls back the copy transaction on failure.
- Requires explicit `--apply --confirm MIGRATE` flags.

It is a one-way data-copy tool, not live replication or zero-downtime migration. It does not provision PostgreSQL, switch application configuration, or execute itself during startup. The audit does not prove exact CHECK expressions, default expressions, partial-index predicates, expression indexes, triggers, views, or every stored-value conversion. A representative dry-run and disposable copy using a backed-up source are required.

### 4. SQL and service behavior

- The adapter intentionally supports a defined subset of the aiosqlite connection/cursor API.
- SQLite-specific conflict handling, date expressions, schema introspection and scalar SQL must continue to be reviewed as new gameplay code is added.
- PostgreSQL integration tests cover meaningful service and concurrency paths, but not every Telegram command, Mini App mutation, or production-scale workload.
- Schema parity is not a proof of identical database semantics. Review constraints, defaults, indexes, query plans, transaction boundaries and race behavior for critical workflows.
- Continue adding regression tests for idempotent rewards, multi-player operations and failure/retry behavior.

### 5. Prototype and production release gates

- The current prototype runbook targets one Railway Docker web service, one persistent disk, SQLite, and the Cloudflare Worker as the public Mini App edge.
- Keep one instance while Telegram polling and HTTP serving share a process.
- Complete real Telegram bot and Android Telegram WebView smoke tests, including registration, Mini App authentication, movement, battle rewards, persistence after restart, and health checks.
- Before production: complete off-site backup/restore, PostgreSQL migration rehearsal, full cross-process concurrency/security review, monitoring/alerting, load tests, and a separate bot-worker/web-process architecture.
- No live Railway deployment, PostgreSQL cutover, Telegram Stars payment enablement, or public production launch is authorized by this document.

## Recommended next sequence

1. Select an off-site backup destination and implement secure export, access controls, failure alerting and retention.
2. Rehearse PostgreSQL restore to a disposable database and document measured recovery steps.
3. Run a representative SQLite-to-PostgreSQL dry-run and disposable migration; investigate all schema and data-conversion warnings.
4. Expand PostgreSQL smoke coverage for remaining Telegram and Mini App mutation paths; continue the SQL/transaction audit.
5. Complete cross-process locking and idempotency review for group, guild, party, trade, auction and multi-account workflows.
6. Run real Telegram/Android device acceptance, monitoring, security and load tests.
7. Only after explicit approval, schedule a controlled migration and production release.

## Safety boundary

- SQLite remains the default unless `DATABASE_URL` is explicitly configured for a process.
- No live SQLite data has been migrated.
- No production runtime has been switched to PostgreSQL.
- Local scheduled backups exist, but off-site recovery and a real restore drill are not complete.
- The Railway prototype has not been deployed or live-tested.
- Telegram Stars purchases remain disabled.
