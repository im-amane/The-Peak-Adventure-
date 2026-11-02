"""Small Psycopg 3 adapter proof-of-concept for the SQLite migration.

This is not yet wired into the game runtime. It demonstrates only the connection,
cursor, row-mapping, transaction-state and legacy qmark-placeholder surface needed
for a staged PostgreSQL migration.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row


_DOLLAR_QUOTE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def _first_keyword(sql: str) -> str | None:
    """Read the first SQL keyword after whitespace and leading comments."""
    index = 0
    while index < len(sql):
        if sql[index].isspace():
            index += 1
        elif sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            if newline < 0:
                return None
            index = newline + 1
        elif sql.startswith("/*", index):
            depth = 1
            index += 2
            while index < len(sql) and depth:
                if sql.startswith("/*", index):
                    depth += 1
                    index += 2
                elif sql.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise ValueError("Unterminated SQL comment")
        else:
            match = re.match(r"[A-Za-z]+", sql[index:])
            return match.group(0).upper() if match else None
    return None


_WRITE_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE",
    "CREATE", "ALTER", "DROP", "TRUNCATE",
    "GRANT", "REVOKE", "COMMENT",
}


def _contains_sql_keyword(sql: str, keywords: set[str]) -> bool:
    """Find SQL keywords without matching text inside literals or comments."""
    index = 0
    length = len(sql)
    while index < length:
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            if newline < 0:
                return False
            index = newline + 1
        elif sql.startswith("/*", index):
            depth = 1
            index += 2
            while index < length and depth:
                if sql.startswith("/*", index):
                    depth += 1
                    index += 2
                elif sql.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise ValueError("Unterminated SQL comment")
        elif sql[index] in {"'", '"'}:
            quote = sql[index]
            escape_string = (
                quote == "'"
                and index > 0
                and sql[index - 1] in {"E", "e"}
                and (index < 2 or not (sql[index - 2].isalnum() or sql[index - 2] == "_"))
            )
            index += 1
            while index < length:
                if quote == "'" and escape_string and sql[index] == "\\":
                    index += 2
                elif sql[index] == quote:
                    if index + 1 < length and sql[index + 1] == quote:
                        index += 2
                    else:
                        index += 1
                        break
                else:
                    index += 1
        elif sql[index] == "$":
            match = _DOLLAR_QUOTE.match(sql, index)
            if match:
                delimiter = match.group(0)
                end = sql.find(delimiter, match.end())
                if end < 0:
                    raise ValueError("Unterminated SQL dollar-quoted string")
                index = end + len(delimiter)
            else:
                index += 1
        elif sql[index].isalpha() or sql[index] == "_":
            end = index + 1
            while end < length and (sql[end].isalnum() or sql[end] in {"_", "$"}):
                end += 1
            if sql[index:end].upper() in keywords:
                return True
            index = end
        else:
            index += 1
    return False


def _is_write_statement(sql: str) -> bool:
    """Classify supported writes, including data-modifying CTEs."""
    keyword = _first_keyword(sql)
    if keyword in _WRITE_KEYWORDS:
        return True
    if keyword == "WITH":
        return _contains_sql_keyword(sql, {"INSERT", "UPDATE", "DELETE", "MERGE"})
    if keyword == "SELECT":
        # SELECT ... FOR UPDATE takes a row lock and must run inside a transaction.
        return _contains_sql_keyword(sql, {"UPDATE"})
    return False


def _normalize_sqlite_insert_ignore(sql: str) -> str:
    """Translate SQLite's INSERT OR IGNORE form to PostgreSQL conflict handling.

    The application uses this legacy form for idempotent player/discovery rows.
    PostgreSQL's unqualified ON CONFLICT DO NOTHING preserves its ignore-on-any-
    unique/exclusion-conflict behavior without needing table-specific constraints.
    """
    if not re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", sql, re.IGNORECASE):
        return sql
    statement = re.sub(
        r"^(\s*)INSERT\s+OR\s+IGNORE\s+INTO\b",
        r"\1INSERT INTO",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )
    stripped = statement.rstrip()
    has_semicolon = stripped.endswith(";")
    if has_semicolon:
        stripped = stripped[:-1].rstrip()
    return stripped + " ON CONFLICT DO NOTHING" + (";" if has_semicolon else "")


def _prepare_statement(sql: str) -> str:
    """Translate legacy SQL syntax and the SQLite-only explicit write-begin form."""
    statement = qmark_to_pyformat(sql)
    statement = _normalize_sqlite_insert_ignore(statement)
    if re.fullmatch(r"\s*BEGIN\s+IMMEDIATE\s*;?\s*", statement, re.IGNORECASE):
        return "BEGIN"
    return statement


def qmark_to_pyformat(sql: str) -> str:
    """Convert legacy qmark parameters while preserving quoted text and comments.

    This intentionally supports positional legacy SQL only. PostgreSQL-native
    operators such as jsonb's '?' operator must not be passed through this helper.
    """
    if not isinstance(sql, str):
        raise TypeError("SQL statement must be a string")

    output: list[str] = []
    index = 0
    length = len(sql)
    quote: str | None = None
    escape_string = False
    dollar_quote: str | None = None
    block_depth = 0
    line_comment = False

    while index < length:
        if line_comment:
            char = sql[index]
            output.append(char)
            index += 1
            if char == "\n":
                line_comment = False
            continue

        if block_depth:
            if sql.startswith("/*", index):
                output.append("/*")
                index += 2
                block_depth += 1
            elif sql.startswith("*/", index):
                output.append("*/")
                index += 2
                block_depth -= 1
            else:
                output.append(sql[index])
                index += 1
            continue

        if dollar_quote is not None:
            if sql.startswith(dollar_quote, index):
                output.append(dollar_quote)
                index += len(dollar_quote)
                dollar_quote = None
            else:
                output.append(sql[index])
                index += 1
            continue

        if quote is not None:
            char = sql[index]
            output.append(char)
            index += 1
            if char == quote:
                if index < length and sql[index] == quote:
                    output.append(sql[index])
                    index += 1
                else:
                    quote = None
            elif quote == "'" and escape_string and char == "\\" and index < length:
                output.append(sql[index])
                index += 1
            else:
                continue
            continue

        if sql.startswith("--", index):
            output.append("--")
            index += 2
            line_comment = True
        elif sql.startswith("/*", index):
            output.append("/*")
            index += 2
            block_depth = 1
        elif sql[index] in {"'", '"'}:
            quote = sql[index]
            escape_string = (
                quote == "'"
                and index > 0
                and sql[index - 1] in {"E", "e"}
                and (index < 2 or not (sql[index - 2].isalnum() or sql[index - 2] == "_"))
            )
            output.append(sql[index])
            index += 1
        elif sql[index] == "$":
            match = _DOLLAR_QUOTE.match(sql, index)
            if match:
                dollar_quote = match.group(0)
                output.append(dollar_quote)
                index = match.end()
            else:
                output.append(sql[index])
                index += 1
        elif sql[index] == "?":
            output.append("%s")
            index += 1
        else:
            output.append(sql[index])
            index += 1

    if quote is not None or dollar_quote is not None or block_depth:
        raise ValueError("Unterminated SQL quoted string or comment")
    return "".join(output)


class PostgresConnection:
    """Minimal async connection wrapper used only by the migration proof-of-concept."""

    dialect = "postgres"

    def __init__(self, connection: psycopg.AsyncConnection):
        self._connection = connection

    @classmethod
    async def connect(cls, conninfo: str) -> "PostgresConnection":
        if not isinstance(conninfo, str) or not conninfo.strip():
            raise ValueError("A PostgreSQL connection string is required")
        connection = await psycopg.AsyncConnection.connect(
            conninfo,
            row_factory=dict_row,
            autocommit=True,
        )
        return cls(connection)

    @property
    def in_transaction(self) -> bool:
        return self._connection.info.transaction_status != TransactionStatus.IDLE

    async def execute(self, sql: str, parameters: Sequence[Any] | None = None):
        statement = _prepare_statement(sql)
        # SQLite starts implicit transactions for writes, but not for SELECTs.
        # Psycopg autocommit mode plus this explicit write detection preserves
        # that observable in_transaction behavior for the supported SQL subset.
        is_write = _is_write_statement(statement)
        if is_write and not self.in_transaction:
            await self._connection.execute("BEGIN")
        return await self._connection.execute(statement, parameters)

    async def executemany(
        self, sql: str, parameters: Iterable[Sequence[Any]]
    ):
        statement = _prepare_statement(sql)
        is_write = _is_write_statement(statement)
        if is_write and not self.in_transaction:
            await self._connection.execute("BEGIN")
        cursor = self._connection.cursor()
        await cursor.executemany(statement, parameters)
        return cursor

    async def commit(self) -> None:
        await self._connection.commit()

    async def rollback(self) -> None:
        await self._connection.rollback()

    @staticmethod
    def _validate_advisory_lock_key(user_id: int) -> int:
        if (
            not isinstance(user_id, int)
            or isinstance(user_id, bool)
            or not 1 <= user_id <= 9_223_372_036_854_775_807
        ):
            raise ValueError("Advisory lock key must be a positive signed 64-bit integer.")
        return user_id

    async def acquire_player_lock(self, user_id: int) -> None:
        """Acquire a session-scoped lock shared by every process using this database."""
        key = self._validate_advisory_lock_key(user_id)
        await self.execute("SELECT pg_advisory_lock(?)", (key,))

    async def release_player_lock(self, user_id: int) -> None:
        """Release a previously acquired session-scoped player lock."""
        key = self._validate_advisory_lock_key(user_id)
        cursor = await self.execute(
            "SELECT pg_advisory_unlock(?) AS released",
            (key,),
        )
        row = await cursor.fetchone()
        if row is None or not row["released"]:
            raise RuntimeError("PostgreSQL player advisory lock was not held by this connection.")

    async def close(self) -> None:
        await self._connection.close()
