# SQLite to PostgreSQL Migration Runbook

**Status:** Preparation only. This runbook has not been executed against production data.

The migration utility is intentionally read-only by default. Do not run the apply command against a live database without an approved maintenance window, a verified source backup, a verified PostgreSQL restore path, and explicit authorization.

## What the tool does

`scripts/migrate_sqlite_to_postgres.py`:

- Reads a SQLite database file in read-only mode.
- Compares source tables and columns with an already-initialized PostgreSQL schema.
- Checks compatible column type affinity, nullability, default availability, generated-key semantics, ordered primary keys, foreign-key mappings/actions, CHECK constraint counts, and index column signatures/uniqueness/partial flags before allowing an apply.
- Reports row counts on both sides.
- Refuses to apply if source tables are missing in PostgreSQL or required target columns cannot be populated.
- Requires every PostgreSQL target table to be empty before applying.
- Copies rows in bounded batches and orders tables by foreign-key dependencies.
- Resets identity/serial sequences after explicit IDs are copied.
- Uses one PostgreSQL transaction for the data copy and rolls it back if a copy step fails.

It does not provision PostgreSQL, initialize the target schema automatically, switch the app runtime, copy SQLite triggers/views or arbitrary custom indexes, or provide live replication.

## 1. Prepare the source

1. Stop all processes that can write to the SQLite database.
2. Create a separate, verified backup of the SQLite file.
3. Confirm the source database is the latest schema version. The normal application schema initialization should have completed successfully before the source is frozen.
4. Record the source file path and retain the backup until the migration and restore checks are complete.

Do not point this tool at a database that is actively receiving writes.

## 2. Prepare an empty PostgreSQL target

Provisioning a PostgreSQL database is a separate, explicitly authorized operation. Use a dedicated empty target for the migration.

Initialize the application schema once on that target:

```bash
python - <<'PY'
import asyncio
import os

from postgres_adapter import PostgresConnection
import main

async def run():
    connection = await PostgresConnection.connect(os.environ["DATABASE_URL"])
    try:
        await main.init_game_schema(connection)
    finally:
        await connection.close()

asyncio.run(run())
PY
```

This creates the schema only. It does not copy player data and does not change the application's runtime database.

## 3. Run the read-only audit

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite ./data/peak_adventure.db \
  --postgres-url "$DATABASE_URL"
```

Review the JSON report. Continue only when:

- `compatible` is `true`.
- `sqlite_only_tables` is empty.
- `missing_postgres_columns` is empty.
- `missing_required_sqlite_columns` is empty.
- `schema_differences` is empty.
- The report's `schema_checks` list contains the expected compatibility checks.
- All expected source row counts are present.
- Every target table has zero rows.

The audit checks type affinity, nullability, default availability, generated-key semantics, primary keys, foreign-key mappings/actions, CHECK constraint counts, and simple index column signatures/uniqueness/partial flags. It does not compare exact CHECK expressions, default expressions, partial-index predicates, expression indexes, triggers, or views. It also does not prove every stored SQLite value can be converted to its PostgreSQL target type. A representative copy in a disposable database is required before any production migration.

## 4. Apply only with explicit authorization

The apply command is intentionally guarded:

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite ./data/peak_adventure.db \
  --postgres-url "$DATABASE_URL" \
  --apply \
  --confirm MIGRATE
```

The tool refuses a non-empty target. If the copy fails, it rolls back the PostgreSQL data transaction. A successful migration populates the target and a second apply attempt will be refused.

Do not run this command as part of ordinary app startup or a Heroku release command.

## 5. Verify the result

Review:

- `applied: true`.
- Source and target row totals.
- Per-table `source_rows` and `target_rows_after`.
- The reported insert order.
- Representative player IDs above the 32-bit range.
- Player inventory, currencies, progression, quests, guilds, parties, trades, auctions and other critical state.
- New inserts on identity-backed tables to confirm sequences advance beyond migrated IDs.

Then perform a full application smoke test against a disposable copy of the migrated target. Do not change the production runtime based only on row counts.

## 6. Recovery and rollback

- Keep the original SQLite file and its verified backup unchanged.
- Keep the PostgreSQL target isolated until validation is complete.
- If validation fails after a successful copy, do not rerun the tool and do not drop the target automatically. Preserve the report and logs, investigate the mismatch, and use an explicitly approved reset/retry procedure.
- Before any production cutover, verify PostgreSQL backup retention and complete a restore rehearsal to a separate database.
- The app still defaults to SQLite; this tool does not change that behavior.

## Railway PostgreSQL operations after an approved cutover

The current Railway prototype uses SQLite on a persistent volume. Do not attach a PostgreSQL database or set `DATABASE_URL` as part of an ordinary deployment. A PostgreSQL cutover is a separate migration with a verified SQLite backup, an empty target database, a successful compatibility audit, and explicit maintenance approval.

If PostgreSQL is selected later, the application container includes `pg_dump` and `pg_restore` through the root Dockerfile. Configure the application's PostgreSQL backup settings and an independent off-site destination, then rehearse downloading and restoring a backup into a disposable database. Railway volume backups and local logical dumps should not be treated as a substitute for an independently tested recovery copy.

No Railway database resource, paid plan, or production cutover is selected or provisioned by this runbook.

## Current limitations

- No production or user database has been migrated.
- No PostgreSQL runtime switch has occurred.
- The migration tool does not perform backup/restore or live replication.
- The compatibility gate compares CHECK constraint counts, not expressions; it compares default availability, not exact default expressions; and it compares partial-index flags, not predicates. Expression indexes, triggers, and views are not audited.
- Data type conversion edge cases require a representative dry-run/copy.
- SQLite triggers, views and custom indexes are not copied by the tool.
- Foreign-key dependency cycles are rejected rather than guessed.
- Heroku provisioning and deployment remain separate, unauthorized actions.
