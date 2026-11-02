# SQLite to PostgreSQL Migration Runbook

**Status:** Preparation only. This runbook has not been executed against production data.

The migration utility is intentionally read-only by default. Do not run the apply command against a live database without an approved maintenance window, a verified source backup, a verified PostgreSQL restore path, and explicit authorization.

## What the tool does

`scripts/migrate_sqlite_to_postgres.py`:

- Reads a SQLite database file in read-only mode.
- Compares source tables and columns with an already-initialized PostgreSQL schema.
- Checks compatible column type affinity, nullability, ordered primary keys, foreign-key mappings/actions, and unique-index column signatures before allowing an apply.
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

The audit also checks type affinity, nullability, primary keys, foreign-key mappings/actions, and unique-index column signatures. It does not yet compare CHECK constraint expressions, default expressions, partial-index predicates, non-unique index definitions, triggers, or views. It also does not prove every stored SQLite value can be converted to its PostgreSQL target type. A representative copy in a disposable database is required before any production migration.

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

## Heroku PostgreSQL backup plan after an approved cutover

Once a Heroku Postgres database has been provisioned and the runtime cutover is separately approved, configure and verify backups outside the application process:

- Capture a manual logical backup with `heroku pg:backups:capture --app <app>`.
- Schedule daily logical backups with `heroku pg:backups:schedule DATABASE_URL --at '02:00 UTC' --app <app>`.
- Inspect backup status and history with the Heroku PGBackups commands before relying on the schedule.
- Scheduled backup failures do not generate notifications, so verification must be part of operations.
- Backup schedules are associated with database attachment names and can be lost when the database is swapped or attachments change.
- Heroku recommends PGBackups for moderately loaded databases up to 20 GB; PGBackups is not supported on Heroku Postgres Advanced.
- A restore replaces the contents of the target database. Rehearse restores against a separate disposable database, never the active production database.

Heroku's Standard tier and higher include continuous protection for disaster recovery. Logical PGBackups provide portable backups for testing and migration. Essential plans have fewer recovery capabilities, so plan selection must account for the required recovery objective. No plan or add-on is selected by this runbook.

Official references:
- [Heroku PGBackups](https://devcenter.heroku.com/articles/heroku-postgres-backups)
- [Heroku Postgres data safety and continuous protection](https://devcenter.heroku.com/articles/heroku-postgres-data-safety-and-continuous-protection)
- [Heroku Postgres logical backups](https://devcenter.heroku.com/articles/heroku-postgres-logical-backups)

## Current limitations

- No production or user database has been migrated.
- No PostgreSQL runtime switch has occurred.
- The migration tool does not perform backup/restore or live replication.
- The compatibility gate does not yet compare CHECK constraints, default expressions, partial-index predicates, or non-unique index definitions.
- Data type conversion edge cases require a representative dry-run/copy.
- SQLite triggers, views and custom indexes are not copied by the tool.
- Foreign-key dependency cycles are rejected rather than guessed.
- Heroku provisioning and deployment remain separate, unauthorized actions.
