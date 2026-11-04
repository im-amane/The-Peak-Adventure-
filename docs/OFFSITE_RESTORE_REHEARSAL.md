# Off-site PostgreSQL restore rehearsal

`restore_offsite_postgres_backup` connects the existing S3-compatible download path to the guarded PostgreSQL restore utility.

## Safety gates

- The caller must explicitly set `target_database_is_disposable=True`.
- `confirm_database` must exactly match the database name embedded in `database_url`; the existing PostgreSQL restore utility enforces this.
- The helper downloads to a private temporary directory, verifies the remote object length and SHA-256 metadata, writes a local checksum sidecar, and asks `pg_restore --list` to validate the archive before restore.
- The PostgreSQL restore runs with `--single-transaction`, `--exit-on-error`, and destructive object replacement flags only after the explicit target confirmation.
- Temporary archive and checksum files are removed after success or failure.

## Example

```python
from offsite_backup import restore_offsite_postgres_backup

result = restore_offsite_postgres_backup(
    bucket="peak-backups",
    key="nightly/peak-adventure.dump",
    database_url="postgresql://restore_user:secret@db-host/peak_restore_drill",
    confirm_database="peak_restore_drill",
    target_database_is_disposable=True,
)
```

The example target is a disposable restore-drill database. Never point this helper at the live application database. Install PostgreSQL client tools (`pg_restore`) and configure S3 credentials through the normal boto3 provider chain before running a real rehearsal.

## Validation status

Automated tests use a mocked S3 client and mocked PostgreSQL restore commands. They verify checksum gating, exact target confirmation forwarding, refusal when the disposable-target flag is absent, and temporary-file cleanup. They do not claim that a real cloud object has been downloaded or restored; that operational rehearsal still requires the deployment's cloud credentials and a disposable database.
