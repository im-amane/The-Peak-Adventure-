"""Explicit, guarded one-way migration from a SQLite file to an initialized PostgreSQL schema.

Dry-run is the default. Applying requires an empty target and an explicit CLI
confirmation. This utility never provisions databases or changes application runtime
configuration.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from postgres_adapter import PostgresConnection


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_identifier(value: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsupported database identifier: {value!r}")
    return '"' + value + '"'


def _inspect_sqlite_schema(source: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    cursor = source.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    schema: dict[str, list[dict[str, Any]]] = {}
    for row in cursor.fetchall():
        table = row["name"]
        quoted_table = _quote_identifier(table)
        columns = source.execute(f"PRAGMA table_info({quoted_table})").fetchall()
        schema[table] = [
            {
                "name": column["name"],
                "declared_type": column["type"] or "",
                "not_null": bool(column["notnull"]),
                "primary_key_position": int(column["pk"]),
            }
            for column in columns
        ]
    return schema


async def _inspect_postgres_schema(target: PostgresConnection) -> dict[str, list[dict[str, Any]]]:
    cursor = await target.execute(
        """SELECT table_name,column_name,data_type,is_nullable,column_default,is_identity,
                  ordinal_position
           FROM information_schema.columns
           WHERE table_schema=current_schema()
           ORDER BY table_name,ordinal_position"""
    )
    schema: dict[str, list[dict[str, Any]]] = {}
    for column in await cursor.fetchall():
        schema.setdefault(column["table_name"], []).append(
            {
                "name": column["column_name"],
                "data_type": column["data_type"],
                "is_nullable": column["is_nullable"],
                "column_default": column["column_default"],
                "is_identity": column["is_identity"],
            }
        )
    return schema


async def _table_row_count(target: PostgresConnection, table: str) -> int:
    cursor = await target.execute(f"SELECT COUNT(*) AS count FROM {_quote_identifier(table)}")
    return int((await cursor.fetchone())["count"])


async def _postgres_insert_order(
    target: PostgresConnection, tables: set[str]
) -> list[str]:
    cursor = await target.execute(
        """SELECT tc.table_name,ccu.table_name AS referenced_table
           FROM information_schema.table_constraints tc
           JOIN information_schema.constraint_column_usage ccu
             ON ccu.constraint_schema=tc.constraint_schema
            AND ccu.constraint_name=tc.constraint_name
           WHERE tc.constraint_type='FOREIGN KEY'
             AND tc.table_schema=current_schema()
             AND ccu.table_schema=current_schema()"""
    )
    edges: dict[str, set[str]] = {table: set() for table in tables}
    indegree = {table: 0 for table in tables}
    for row in await cursor.fetchall():
        child = row["table_name"]
        parent = row["referenced_table"]
        if child in tables and parent in tables and child != parent and child not in edges[parent]:
            edges[parent].add(child)
            indegree[child] += 1

    ready = sorted(table for table, degree in indegree.items() if degree == 0)
    ordered: list[str] = []
    while ready:
        table = ready.pop(0)
        ordered.append(table)
        for child in sorted(edges[table]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    if len(ordered) != len(tables):
        cyclic = sorted(table for table, degree in indegree.items() if degree > 0)
        raise ValueError(
            "Foreign-key dependency cycle prevents a safe ordered migration: "
            + ", ".join(cyclic)
        )
    return ordered


async def migrate_sqlite_to_postgres(
    sqlite_path: str | Path,
    target: PostgresConnection,
    *,
    apply: bool = False,
    batch_size: int = 500,
) -> dict[str, Any]:
    """Audit a SQLite source and optionally copy its rows into an empty PG target."""
    source_path = Path(sqlite_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {source_path}")
    if type(batch_size) is not int or not 1 <= batch_size <= 10_000:
        raise ValueError("batch_size must be an integer between 1 and 10000")

    source = sqlite3.connect(
        f"file:{source_path.resolve().as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    source.row_factory = sqlite3.Row
    try:
        source.execute("BEGIN")
        sqlite_schema = _inspect_sqlite_schema(source)
        postgres_schema = await _inspect_postgres_schema(target)
        sqlite_tables = set(sqlite_schema)
        postgres_tables = set(postgres_schema)

        missing_tables = sorted(sqlite_tables - postgres_tables)
        missing_source_columns: dict[str, list[str]] = {}
        missing_required_target_columns: dict[str, list[str]] = {}
        for table in sorted(sqlite_tables & postgres_tables):
            source_columns = {column["name"] for column in sqlite_schema[table]}
            target_columns = {column["name"]: column for column in postgres_schema[table]}
            missing = sorted(source_columns - set(target_columns))
            if missing:
                missing_source_columns[table] = missing
            required = sorted(
                column_name
                for column_name, column in target_columns.items()
                if column_name not in source_columns
                and column["is_nullable"] == "NO"
                and column["column_default"] is None
                and column["is_identity"] != "YES"
            )
            if required:
                missing_required_target_columns[table] = required

        table_reports = []
        for table in sorted(postgres_tables | sqlite_tables):
            source_rows = 0
            target_rows = 0
            if table in sqlite_tables:
                source_rows = int(
                    source.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table)}").fetchone()[0]
                )
            if table in postgres_tables:
                target_rows = await _table_row_count(target, table)
            table_reports.append(
                {"table": table, "source_rows": source_rows, "target_rows_before": target_rows}
            )

        compatible = not (
            missing_tables or missing_source_columns or missing_required_target_columns
        )
        report: dict[str, Any] = {
            "compatible": compatible,
            "applied": False,
            "source": str(source_path),
            "sqlite_only_tables": sorted(sqlite_tables - postgres_tables),
            "postgres_only_tables": sorted(postgres_tables - sqlite_tables),
            "missing_postgres_columns": missing_source_columns,
            "missing_required_sqlite_columns": missing_required_target_columns,
            "tables": table_reports,
            "total_source_rows": sum(item["source_rows"] for item in table_reports),
            "total_target_rows_before": sum(item["target_rows_before"] for item in table_reports),
        }
        if not compatible or not apply:
            return report

        nonempty = [
            item["table"] for item in table_reports if item["target_rows_before"] > 0
        ]
        if nonempty:
            raise ValueError(
                "Refusing to migrate into a non-empty PostgreSQL target. "
                "Tables with existing rows: " + ", ".join(nonempty[:20])
            )

        ordered_tables = await _postgres_insert_order(target, sqlite_tables)
        await target.execute("BEGIN")
        try:
            for table in ordered_tables:
                source_columns = [column["name"] for column in sqlite_schema[table]]
                quoted_table = _quote_identifier(table)
                quoted_columns = ", ".join(_quote_identifier(column) for column in source_columns)
                placeholders = ", ".join("?" for _ in source_columns)
                insert_sql = (
                    f"INSERT INTO {quoted_table} ({quoted_columns}) "
                    f"VALUES ({placeholders})"
                )
                cursor = source.execute(
                    f"SELECT {quoted_columns} FROM {quoted_table}"
                )
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break
                    await target.executemany(
                        insert_sql,
                        [tuple(row[column] for column in source_columns) for row in rows],
                    )

            for table in ordered_tables:
                identity_columns = [
                    column["name"]
                    for column in postgres_schema[table]
                    if column["is_identity"] == "YES"
                    or (
                        column["column_default"]
                        and "nextval(" in column["column_default"]
                    )
                ]
                quoted_table = _quote_identifier(table)
                for column in identity_columns:
                    quoted_column = _quote_identifier(column)
                    await target.execute(
                        f"""SELECT setval(
                               pg_get_serial_sequence(
                                 format('%I.%I',current_schema(),?),
                                 ?
                               ),
                               COALESCE(MAX({quoted_column}),1),
                               MAX({quoted_column}) IS NOT NULL
                             )
                             FROM {quoted_table}""",
                        (table, column),
                    )
            await target.commit()
        except Exception:
            await target.rollback()
            raise

        report["applied"] = True
        report["insert_order"] = ordered_tables
        report["tables"] = [
            {
                **item,
                "target_rows_after": await _table_row_count(target, item["table"])
                if item["table"] in postgres_tables
                else 0,
            }
            for item in table_reports
        ]
        report["total_target_rows_after"] = sum(
            item.get("target_rows_after", 0) for item in report["tables"]
        )
        return report
    finally:
        if source.in_transaction:
            source.rollback()
        source.close()


async def _run_cli(args: argparse.Namespace) -> int:
    if not args.postgres_url:
        raise ValueError("Provide --postgres-url or set DATABASE_URL.")
    if args.apply and args.confirm != "MIGRATE":
        raise ValueError("Applying requires --apply --confirm MIGRATE.")
    if not args.apply and args.confirm:
        raise ValueError("--confirm is only valid together with --apply.")

    target = await PostgresConnection.connect(args.postgres_url)
    try:
        report = await migrate_sqlite_to_postgres(
            args.sqlite,
            target,
            apply=args.apply,
            batch_size=args.batch_size,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["compatible"] else 2
    finally:
        await target.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit or explicitly migrate a SQLite database into an initialized PostgreSQL schema."
    )
    parser.add_argument("--sqlite", required=True, help="Path to the source SQLite database file.")
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL connection URL; defaults to DATABASE_URL.",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Copy data. The target must be empty; dry-run is the default.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help="Required literal MIGRATE confirmation when --apply is used.",
    )
    args = parser.parse_args()
    return asyncio.run(_run_cli(args))


if __name__ == "__main__":
    raise SystemExit(main())
