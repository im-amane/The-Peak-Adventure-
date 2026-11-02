# PostgreSQL Compatibility Audit

**Audit scope:** 30 top-level Python source files on `main`, covering the game backend, persistence helpers and service modules. This is a source-level compatibility inventory, not a completed migration and not proof of runtime compatibility.

## Executive finding

The application is deeply coupled to SQLite and `aiosqlite`. Heroku Postgres cannot be enabled safely by adding a `DATABASE_URL` setting or changing one connection call. A deliberate persistence-layer migration is required before the Heroku deployment target can hold real player data.

## Source scan

The following counts are approximate lexical scan results across the 30 root Python files. Question-mark counts can include non-SQL text; they indicate the scale of the qmark-placeholder footprint, not an exact count of SQL parameters.

| Compatibility surface | Observed footprint | Migration impact |
|---|---:|---|
| Root Python source files reviewed | 30 | Full backend source inventory |
| Files containing qmark `?` tokens | 26 | SQL parameter syntax must be converted or safely adapted |
| Qmark tokens | ~1,085 | Large query-conversion surface |
| Direct `aiosqlite` references | 11 modules | Connection and cursor APIs are coupled to SQLite |
| Direct `sqlite3` references | 4 modules | Backup, exception and database-specific behavior need replacement |
| `SAVEPOINT` tokens | ~420 | Nested transaction semantics must be preserved |
| `BEGIN IMMEDIATE` statements | 40 | SQLite writer-lock assumptions need redesign |
| `lastrowid` references | 17 | Inserts need explicit `RETURNING` identifiers |
| `PRAGMA` references | 5 | Schema introspection and backup checks are SQLite-specific |
| `executescript` calls | 1 | Multi-statement schema initialization needs migrations |

## High-risk modules

| Module | Current coupling | Priority |
|---|---|---|
| `main.py` | Owns the global `aiosqlite.Connection`, row factory, schema bootstrap, inline migrations, 200+ execute calls, 74 savepoint tokens, 10 `BEGIN IMMEDIATE` statements and 3 `lastrowid` references | Critical |
| `account_system.py` | Direct connection transaction state, savepoints, schema introspection and SQLite-specific table discovery | High |
| `auction_system.py` | Transaction/savepoint logic, generated IDs and optional-table discovery; escrow must remain atomic | High |
| `guild_system.py` | Generated IDs, SQLite-specific date arithmetic, transactions and idempotent event settlement | High |
| `group_system.py` | Generated IDs, `INSERT OR IGNORE/REPLACE`, date arithmetic and transactional rewards | High |
| `party_system.py` | Generated IDs, date arithmetic, transactions and multiplayer state transitions | High |
| `db_backup.py` | Uses the SQLite online backup API and `PRAGMA integrity_check`; it cannot back up PostgreSQL | Critical |
| `friend_system.py`, `presence_system.py`, `security_system.py` | Direct `aiosqlite` references and transaction-aware service calls | Medium |
| `character_system.py`, `secret_area_system.py`, `world_system.py` | SQLite schema introspection or exception/API assumptions | Medium |

## SQLite-specific behavior to replace

1. **Connection and cursor API:** `aiosqlite.connect`, `aiosqlite.Row`, `db.execute`, `fetchone/fetchall`, `db.in_transaction`, `commit` and `rollback`.
2. **Parameter syntax:** SQLite qmark placeholders (`?`) are used throughout the repository.
3. **Transactions:** `BEGIN IMMEDIATE`, nested savepoints and process-local `db_lock` / `player_locks` are part of current correctness assumptions. PostgreSQL needs explicit transaction ownership and row-level or advisory locking where required.
4. **Generated identifiers:** `cursor.lastrowid` must be replaced with explicit `INSERT ... RETURNING id` behavior.
5. **Schema lifecycle:** `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE` with swallowed duplicate-column errors, `PRAGMA table_info`, `sqlite_master` and the startup `executescript` need versioned, ordered migrations.
6. **Conflict handling:** `INSERT OR IGNORE` and `INSERT OR REPLACE` do not translate mechanically to PostgreSQL. `REPLACE` semantics especially require explicit review.
7. **Date/time SQL:** `julianday`, SQLite `datetime('now', ...)` and SQLite date arithmetic need PostgreSQL equivalents with timezone-consistent behavior.
8. **Backup/restore:** the current `sqlite3.Connection.backup` and `PRAGMA integrity_check` workflow must be replaced with a PostgreSQL backup/restore and verification strategy.
9. **Error handling:** code that catches `aiosqlite.OperationalError`, `sqlite3.IntegrityError` or other SQLite exceptions must use driver-neutral domain errors or mapped PostgreSQL exceptions.

## Recommended migration sequence

### Phase 1: persistence contract and test fixtures
- Define a small asynchronous database contract for execute/fetch, transaction scopes and generated identifiers.
- Keep the existing SQLite implementation as the reference adapter while the contract is introduced.
- Add contract tests for nested transactions, rollback, row access, unique constraints, generated IDs and concurrent updates.
- Do not hide SQL differences behind an untested global string-replacement layer.

### Phase 2: schema migrations
- Move startup DDL and inline `ALTER TABLE` statements into ordered, versioned migrations.
- Add PostgreSQL types, constraints, indexes and foreign keys deliberately.
- Test clean installation and upgrade from a representative existing SQLite schema/data export.
- Preserve player IDs, inventory, currencies, quest state, guilds, parties, trades, auctions and idempotency records.

### Phase 3: service migration
- Migrate one domain at a time, beginning with player/profile and simple read-only services.
- Follow with inventory/economy, battle/rewards, social/multiplayer, guild/auction and admin/moderation.
- Replace generated IDs and SQLite conflict/date operations explicitly.
- Run the same domain test suite against both adapters until parity is demonstrated.

### Phase 4: concurrency and recovery
- Replace process-local correctness assumptions with database-enforced uniqueness, transactions and row-level/advisory locks where needed.
- Test duplicate and concurrent reward claims, trades, auctions, guild wars and party battles across independent connections.
- Implement durable backup, restore and migration rollback procedures.
- Verify restart and redeploy persistence against a disposable PostgreSQL environment.

### Phase 5: Heroku release gates
- Add the PostgreSQL adapter and migration tooling to the Heroku build.
- Configure secrets and database URL only after the adapter is complete.
- Separate Telegram polling from the web process before horizontal scaling.
- Verify Cloudflare Worker routing to the Heroku HTTPS origin.
- Perform real Telegram, Android WebView, backup/restore, concurrency and load checks before public launch.

## Architecture decision still required

Two viable approaches need a small proof-of-concept before choosing:

- **Explicit driver-neutral repository/database layer:** clearer semantics and easier long-term testing, but requires touching many service modules.
- **Compatibility adapter around an async PostgreSQL driver:** may reduce repetitive call-site changes, but must explicitly handle placeholder conversion, cursor behavior, generated IDs, transaction state, exception mapping and SQLite-only SQL. A blind qmark-to-PostgreSQL rewrite is not sufficient.

The proof-of-concept should migrate one small service and its tests, demonstrate transaction rollback and concurrent writes, and compare maintainability before the full migration is approved.

## Safety boundary

- No PostgreSQL service, Heroku add-on, dyno or paid resource has been provisioned.
- No live database migration or deployment has been performed.
- SQLite remains the current prototype database.
- Telegram Stars purchases remain disabled.
