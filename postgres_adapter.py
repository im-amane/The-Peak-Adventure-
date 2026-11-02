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
            elif quote == "'" and char == "\\" and index < length:
                # Conservatively preserve escaped characters in E-strings.
                output.append(sql[index])
                index += 1
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
        statement = qmark_to_pyformat(sql)
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            statement = "BEGIN"

        # SQLite starts implicit transactions for writes, but not for SELECTs.
        # Psycopg autocommit mode plus this explicit write detection preserves
        # that observable in_transaction behavior for the supported SQL subset.
        keyword = _first_keyword(statement)
        write_keywords = {
            "INSERT", "UPDATE", "DELETE", "MERGE",
            "CREATE", "ALTER", "DROP", "TRUNCATE",
            "GRANT", "REVOKE", "COMMENT",
        }
        is_write = keyword in write_keywords
        if keyword == "WITH":
            is_write = re.search(r"\b(INSERT|UPDATE|DELETE|MERGE)\b", statement, re.IGNORECASE) is not None
        if is_write and not self.in_transaction:
            await self._connection.execute("BEGIN")
        return await self._connection.execute(statement, parameters)

    async def executemany(
        self, sql: str, parameters: Iterable[Sequence[Any]]
    ):
        statement = qmark_to_pyformat(sql)
        keyword = _first_keyword(statement)
        write_keywords = {
            "INSERT", "UPDATE", "DELETE", "MERGE",
            "CREATE", "ALTER", "DROP", "TRUNCATE",
            "GRANT", "REVOKE", "COMMENT",
        }
        is_write = keyword in write_keywords
        if keyword == "WITH":
            is_write = re.search(
                r"\\b(INSERT|UPDATE|DELETE|MERGE)\\b",
                statement,
                re.IGNORECASE,
            ) is not None
        if is_write and not self.in_transaction:
            await self._connection.execute("BEGIN")
        cursor = self._connection.cursor()
        await cursor.executemany(statement, parameters)
        return cursor

    async def commit(self) -> None:
        await self._connection.commit()

    async def rollback(self) -> None:
        await self._connection.rollback()

    async def close(self) -> None:
        await self._connection.close()
