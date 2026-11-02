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
        table_sql_row = source.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        has_autoincrement = "AUTOINCREMENT" in ((table_sql_row["sql"] or "").upper())
        schema[table] = [
            {
                "name": column["name"],
                "declared_type": column["type"] or "",
                "not_null": bool(column["notnull"]) or bool(column["pk"]),
                "primary_key_position": int(column["pk"]),
                "default": column["dflt_value"],
                "is_autoincrement": bool(column["pk"] and has_autoincrement),
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


def _sqlite_type_affinity(declared_type: str, column_name: str) -> str:
    value = (declared_type or "").upper()
    name = column_name.lower()
    if "BOOL" in value:
        return "boolean"
    if any(token in value for token in ("DATE", "TIME")):
        return "datetime"
    if "INT" in value:
        return "integer"
    if any(token in value for token in ("CHAR", "CLOB", "TEXT")):
        return "text"
    if "BLOB" in value or not value:
        return "blob"
    if any(token in value for token in ("REAL", "FLOA", "DOUB")):
        return "real"
    return "numeric"


def _postgres_type_affinity(data_type: str) -> str:
    value = (data_type or "").lower()
    if value in {"smallint", "integer", "bigint"}:
        return "integer"
    if value in {"text", "character varying", "character"}:
        return "text"
    if value == "bytea":
        return "blob"
    if value in {"real", "double precision"}:
        return "real"
    if value in {"numeric", "decimal"}:
        return "numeric"
    if value == "boolean":
        return "boolean"
    if value.startswith("timestamp") or value == "date":
        return "datetime"
    return value


async def _inspect_schema_constraints(
    source: sqlite3.Connection,
    target: PostgresConnection,
    sqlite_schema: dict[str, list[dict[str, Any]]],
    postgres_schema: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """Compare semantic schema guarantees needed for a safe row migration."""
    shared_tables = set(sqlite_schema) & set(postgres_schema)
    sqlite_primary_keys: dict[str, tuple[str, ...]] = {}
    sqlite_foreign_keys = set()
    sqlite_indexes = set()
    sqlite_check_counts: dict[str, int] = {}

    for table in shared_tables:
        quoted_table = _quote_identifier(table)
        columns = source.execute(f"PRAGMA table_info({quoted_table})").fetchall()
        sqlite_primary_keys[table] = tuple(
            row["name"] for row in sorted(columns, key=lambda item: item["pk"]) if row["pk"]
        )
        table_sql_row = source.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        table_sql = table_sql_row["sql"] or ""
        without_quoted_literals = re.sub(
            r"'(?:''|[^'])*'",
            "",
            table_sql,
        )
        sqlite_check_counts[table] = len(
            re.findall(r"\bCHECK\s*\(", without_quoted_literals, re.IGNORECASE)
        )
        for fk in source.execute(f"PRAGMA foreign_key_list({quoted_table})").fetchall():
            referenced_column = fk["to"]
            if referenced_column is None:
                parent_columns = source.execute(
                    f"PRAGMA table_info({_quote_identifier(fk['table'])})"
                ).fetchall()
                parent_pk = [
                    row["name"] for row in sorted(parent_columns, key=lambda item: item["pk"])
                    if row["pk"]
                ]
                if fk["seq"] >= len(parent_pk):
                    raise ValueError(
                        f"Unable to resolve referenced primary key for {table}.{fk['from']}"
                    )
                referenced_column = parent_pk[fk["seq"]]
            sqlite_foreign_keys.add((
                table, fk["from"], fk["table"], referenced_column,
                fk["on_update"].upper(), fk["on_delete"].upper(),
            ))
        for index in source.execute(f"PRAGMA index_list({quoted_table})").fetchall():
            index_columns = source.execute(
                f"PRAGMA index_info({_quote_identifier(index['name'])})"
            ).fetchall()
            if not index_columns or not all(column["name"] for column in index_columns):
                continue
            ordered_columns = tuple(column["name"] for column in index_columns)
            if index["unique"] and tuple(sorted(ordered_columns)) == tuple(
                sorted(sqlite_primary_keys[table])
            ):
                # Ignore redundant UNIQUE constraints identical to the primary key.
                continue
            signature = (
                table,
                bool(index["unique"]),
                tuple(sorted(ordered_columns)) if index["unique"] else ordered_columns,
                bool(index["partial"]),
            )
            if index["origin"] != "pk":
                sqlite_indexes.add(signature)


    cursor = await target.execute(
        """SELECT tc.table_name,kcu.column_name,kcu.ordinal_position
           FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu
             ON tc.constraint_catalog=kcu.constraint_catalog
            AND tc.constraint_schema=kcu.constraint_schema
            AND tc.constraint_name=kcu.constraint_name
           WHERE tc.constraint_type='PRIMARY KEY'
             AND tc.constraint_schema=current_schema()
           ORDER BY tc.table_name,kcu.ordinal_position"""
    )
    postgres_primary_keys: dict[str, list[str]] = {}
    for row in await cursor.fetchall():
        postgres_primary_keys.setdefault(row["table_name"], []).append(row["column_name"])

    cursor = await target.execute(
        """SELECT child.relname AS table_name,child_column.attname AS column_name,
                  parent.relname AS referenced_table,parent_column.attname AS referenced_column,
                  CASE fk.confupdtype WHEN 'a' THEN 'NO ACTION' WHEN 'r' THEN 'RESTRICT'
                       WHEN 'c' THEN 'CASCADE' WHEN 'n' THEN 'SET NULL'
                       WHEN 'd' THEN 'SET DEFAULT' END AS update_rule,
                  CASE fk.confdeltype WHEN 'a' THEN 'NO ACTION' WHEN 'r' THEN 'RESTRICT'
                       WHEN 'c' THEN 'CASCADE' WHEN 'n' THEN 'SET NULL'
                       WHEN 'd' THEN 'SET DEFAULT' END AS delete_rule
           FROM pg_constraint fk
           JOIN pg_class child ON child.oid=fk.conrelid
           JOIN pg_namespace child_schema ON child_schema.oid=child.relnamespace
           JOIN pg_class parent ON parent.oid=fk.confrelid
           JOIN pg_namespace parent_schema ON parent_schema.oid=parent.relnamespace
           JOIN LATERAL unnest(fk.conkey,fk.confkey)
                WITH ORDINALITY AS key(child_attnum,parent_attnum,ordinality) ON TRUE
           JOIN pg_attribute child_column
             ON child_column.attrelid=child.oid AND child_column.attnum=key.child_attnum
           JOIN pg_attribute parent_column
             ON parent_column.attrelid=parent.oid AND parent_column.attnum=key.parent_attnum
           WHERE fk.contype='f'
             AND child_schema.nspname=current_schema()
             AND parent_schema.nspname=current_schema()"""
    )
    postgres_foreign_keys = {
        (
            row["table_name"], row["column_name"], row["referenced_table"],
            row["referenced_column"], row["update_rule"].upper(), row["delete_rule"].upper(),
        )
        for row in await cursor.fetchall()
        if row["table_name"] in shared_tables
    }

    cursor = await target.execute(
        """SELECT t.relname AS table_name,i.indisunique AS is_unique,
                  i.indpred IS NOT NULL AS is_partial,
                  array_agg(a.attname ORDER BY key.ordinality) AS columns
           FROM pg_index i
           JOIN pg_class t ON t.oid=i.indrelid
           JOIN pg_namespace n ON n.oid=t.relnamespace
           JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS key(attnum,ordinality)
             ON key.ordinality <= i.indnkeyatts
           JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=key.attnum
           WHERE n.nspname=current_schema() AND NOT i.indisprimary
             AND i.indexprs IS NULL
           GROUP BY t.relname,i.indexrelid"""
    )
    postgres_indexes = set()
    for row in await cursor.fetchall():
        if row["table_name"] not in shared_tables:
            continue
        index_columns = tuple(row["columns"])
        if row["is_unique"]:
            index_columns = tuple(sorted(index_columns))
        postgres_indexes.add((
            row["table_name"], bool(row["is_unique"]), index_columns, bool(row["is_partial"])
        ))


    differences: list[str] = []
    for table in sorted(shared_tables):
        source_columns = {column["name"]: column for column in sqlite_schema[table]}
        target_columns = {column["name"]: column for column in postgres_schema[table]}
        for column in sorted(set(source_columns) & set(target_columns)):
            source_column = source_columns[column]
            target_column = target_columns[column]
            source_affinity = _sqlite_type_affinity(
                source_column["declared_type"], column
            )
            target_affinity = _postgres_type_affinity(target_column["data_type"])
            if (
                source_affinity == "text"
                and target_affinity == "datetime"
                and (
                    column.lower().endswith(("_at", "_time", "_date"))
                    or column.lower() in {"last_seen", "created", "updated"}
                )
            ):
                # Some legacy SQLite timestamp values are TEXT while a matching
                # PostgreSQL column is a native timestamp; allow only that pairing.
                source_affinity = "datetime"
            if source_affinity != target_affinity:
                differences.append(
                    f"type mismatch {table}.{column}: SQLite {source_column['declared_type']!r} "
                    f"({source_affinity}) vs PostgreSQL {target_column['data_type']!r} "
                    f"({target_affinity})"
                )
            source_not_null = (
                source_column["not_null"] or source_column["primary_key_position"] > 0
            )
            target_not_null = target_column["is_nullable"] == "NO"
            if source_not_null != target_not_null:
                differences.append(
                    f"nullability mismatch {table}.{column}: "
                    f"SQLite not_null={source_not_null} vs PostgreSQL not_null={target_not_null}"
                )
            source_default = source_column.get("default")
            target_default = target_column.get("column_default")
            source_has_default = (
                source_default is not None
                and str(source_default).strip().upper() not in {"NULL", "(NULL)"}
            )
            target_has_default = (
                target_default is not None
                and str(target_default).strip().upper() not in {"NULL", "(NULL)"}
            )
            source_generated = bool(source_column.get("is_autoincrement"))
            target_generated = (
                target_column.get("is_identity") == "YES"
                or bool(target_default and "nextval(" in str(target_default).lower())
            )
            if source_generated != target_generated:
                differences.append(
                    f"generated-key mismatch {table}.{column}: "
                    f"SQLite autoincrement={source_generated} vs PostgreSQL identity/sequence={target_generated}"
                )
            if not source_generated and source_has_default != target_has_default:
                differences.append(
                    f"default availability mismatch {table}.{column}: "
                    f"SQLite has_default={source_has_default} vs PostgreSQL has_default={target_has_default}"
                )

    cursor = await target.execute(
        """SELECT c.relname AS table_name,COUNT(*) AS check_count
           FROM pg_constraint con
           JOIN pg_class c ON c.oid=con.conrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE con.contype='c' AND n.nspname=current_schema()
           GROUP BY c.relname"""
    )
    postgres_check_counts = {
        row["table_name"]: int(row["check_count"]) for row in await cursor.fetchall()
    }
    for table in sorted(shared_tables):
        source_count = sqlite_check_counts.get(table, 0)
        target_count = postgres_check_counts.get(table, 0)
        if source_count != target_count:
            differences.append(
                f"check constraint count mismatch {table}: "
                f"SQLite={source_count} vs PostgreSQL={target_count}"
            )

    postgres_primary_key_tuples = {
        table: tuple(columns) for table, columns in postgres_primary_keys.items()
        if table in shared_tables
    }
    for table in sorted(shared_tables):
        source_pk = sqlite_primary_keys.get(table, ())
        target_pk = postgres_primary_key_tuples.get(table, ())
        if source_pk != target_pk:
            differences.append(
                f"primary-key mismatch {table}: SQLite {source_pk} vs PostgreSQL {target_pk}"
            )

    sqlite_foreign_keys = {
        item for item in sqlite_foreign_keys if item[0] in shared_tables
    }
    if sqlite_foreign_keys != postgres_foreign_keys:
        for item in sorted(sqlite_foreign_keys - postgres_foreign_keys):
            differences.append(f"PostgreSQL missing foreign key {item}")
        for item in sorted(postgres_foreign_keys - sqlite_foreign_keys):
            differences.append(f"PostgreSQL has extra foreign key {item}")

    sqlite_indexes = {item for item in sqlite_indexes if item[0] in shared_tables}
    if sqlite_indexes != postgres_indexes:
        for item in sorted(sqlite_indexes - postgres_indexes):
            label = "unique index" if item[1] else "index"
            differences.append(f"PostgreSQL missing {label} {item}")
        for item in sorted(postgres_indexes - sqlite_indexes):
            label = "unique index" if item[1] else "index"
            differences.append(f"PostgreSQL has extra {label} {item}")
    return differences


async def _table_row_count(target: PostgresConnection, table: str) -> int:
    cursor = await target.execute(f"SELECT COUNT(*) AS count FROM {_quote_identifier(table)}")
    return int((await cursor.fetchone())["count"])


async def _postgres_insert_order(
    target: PostgresConnection, tables: set[str]
) -> list[str]:
    cursor = await target.execute(
        """SELECT child.relname AS table_name,parent.relname AS referenced_table
           FROM pg_constraint fk
           JOIN pg_class child ON child.oid=fk.conrelid
           JOIN pg_namespace child_schema ON child_schema.oid=child.relnamespace
           JOIN pg_class parent ON parent.oid=fk.confrelid
           JOIN pg_namespace parent_schema ON parent_schema.oid=parent.relnamespace
           WHERE fk.contype='f'
             AND child_schema.nspname=current_schema()
             AND parent_schema.nspname=current_schema()"""
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
    if target.in_transaction:
        raise RuntimeError("PostgreSQL target connection must be idle before migration.")

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
        schema_differences = await _inspect_schema_constraints(
            source, target, sqlite_schema, postgres_schema
        )
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
            or schema_differences
        )
        report: dict[str, Any] = {
            "compatible": compatible,
            "applied": False,
            "source": str(source_path),
            "sqlite_only_tables": sorted(sqlite_tables - postgres_tables),
            "postgres_only_tables": sorted(postgres_tables - sqlite_tables),
            "missing_postgres_columns": missing_source_columns,
            "missing_required_sqlite_columns": missing_required_target_columns,
            "schema_differences": schema_differences,
            "schema_checks": [
                "column_type_affinity",
                "column_nullability",
                "primary_keys",
                "foreign_keys_and_actions",
                "default_availability",
                "generated_key_semantics",
                "check_constraint_counts",
                "indexes_and_partial_flags",
            ],
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
                                 quote_ident(current_schema()) || '.' || quote_ident(?),
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
