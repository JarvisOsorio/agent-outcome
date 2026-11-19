"""PostgreSQL assertions and observers."""

from __future__ import annotations

import os
import re
from typing import Any, Mapping

from agent_outcome.adapters.base import PostgresObserver
from agent_outcome.models import AssertionResult, AssertionSpec, Failure

ADAPTER = "postgres"
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def row_exists(*, table: str, where: Mapping[str, Any]) -> AssertionSpec:
    return AssertionSpec(
        kind="row_exists",
        adapter=ADAPTER,
        params={"table": table, "where": dict(where)},
    )


def column_equals(
    *,
    table: str,
    where: Mapping[str, Any],
    column: str,
    expected: Any,
) -> AssertionSpec:
    return AssertionSpec(
        kind="column_equals",
        adapter=ADAPTER,
        params={
            "table": table,
            "where": dict(where),
            "column": column,
            "expected": expected,
        },
    )


def count_equals(
    *,
    table: str,
    expected: int,
    where: Mapping[str, Any] | None = None,
) -> AssertionSpec:
    return AssertionSpec(
        kind="count_equals",
        adapter=ADAPTER,
        params={
            "table": table,
            "where": dict(where or {}),
            "expected": int(expected),
        },
    )


class FakePostgresObserver:
    """In-memory table map for hermetic tests."""

    def __init__(self, tables: Mapping[str, list[Mapping[str, Any]]] | None = None):
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in (tables or {}).items()
        }

    def set_table(self, table: str, rows: list[Mapping[str, Any]]) -> None:
        self._tables[table] = [dict(r) for r in rows]

    def fetch_rows(
        self, table: str, where: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        rows = self._tables.get(table, [])
        if not where:
            return [dict(r) for r in rows]
        out: list[dict[str, Any]] = []
        for row in rows:
            if all(row.get(k) == v for k, v in where.items()):
                out.append(dict(row))
        return out

    def count_rows(self, table: str, where: Mapping[str, Any] | None = None) -> int:
        return len(self.fetch_rows(table, where or {}))


def _quote_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


class LivePostgresObserver:
    """psycopg-backed observer. Requires AGENT_OUTCOME_DATABASE_URL or DATABASE_URL."""

    def __init__(self, dsn: str | None = None, *, connection: Any | None = None):
        self.dsn = dsn or os.environ.get("AGENT_OUTCOME_DATABASE_URL") or os.environ.get(
            "DATABASE_URL", ""
        )
        self._connection = connection

    def _connect(self) -> Any:
        if self._connection is not None:
            return self._connection
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised when optional dep missing
            raise RuntimeError(
                "psycopg is required for live Postgres. Install agent-outcome[postgres]."
            ) from exc
        if not self.dsn:
            raise RuntimeError(
                "No Postgres DSN. Set AGENT_OUTCOME_DATABASE_URL or DATABASE_URL."
            )
        return psycopg.connect(self.dsn)

    def fetch_rows(
        self, table: str, where: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        owns = self._connection is None
        try:
            clauses = []
            values: list[Any] = []
            for idx, (key, value) in enumerate(where.items(), start=1):
                clauses.append(f"{_quote_ident(key)} = %s")
                values.append(value)
            sql = f"SELECT * FROM {_quote_ident(table)}"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            with conn.cursor() as cur:
                cur.execute(sql, values)
                cols = [d.name for d in cur.description] if cur.description else []
                return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
        finally:
            if owns:
                conn.close()

    def count_rows(self, table: str, where: Mapping[str, Any] | None = None) -> int:
        where = where or {}
        conn = self._connect()
        owns = self._connection is None
        try:
            clauses = []
            values: list[Any] = []
            for key, value in where.items():
                clauses.append(f"{_quote_ident(key)} = %s")
                values.append(value)
            sql = f"SELECT COUNT(*) FROM {_quote_ident(table)}"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            with conn.cursor() as cur:
                cur.execute(sql, values)
                row = cur.fetchone()
                return int(row[0]) if row else 0
        finally:
            if owns:
                conn.close()


_KNOWN_KINDS = {"row_exists", "column_equals", "count_equals"}


def evaluate(spec: AssertionSpec, observer: PostgresObserver) -> AssertionResult:
    kind = spec.kind
    params = spec.params

    if kind not in _KNOWN_KINDS:
        return AssertionResult(
            assertion=spec,
            passed=False,
            observation={},
            failure=Failure(
                code="PG_UNKNOWN_ASSERTION",
                assertion=kind,
                message=f"Unknown Postgres assertion kind: {kind}",
            ),
        )

    table = str(params["table"])
    where = dict(params.get("where") or {})

    if kind == "row_exists":
        rows = observer.fetch_rows(table, where)
        if not rows:
            return AssertionResult(
                assertion=spec,
                passed=False,
                observation={"count": 0, "rows": []},
                failure=Failure(
                    code="PG_ROW_NOT_FOUND",
                    assertion=kind,
                    message=f"No row in {table} matching {where}",
                    expected={"table": table, "where": where},
                    actual={"count": 0},
                ),
            )
        return AssertionResult(
            assertion=spec,
            passed=True,
            observation={"count": len(rows), "rows": rows},
        )

    if kind == "column_equals":
        column = str(params["column"])
        expected = params["expected"]
        rows = observer.fetch_rows(table, where)
        if not rows:
            return AssertionResult(
                assertion=spec,
                passed=False,
                observation={"count": 0, "rows": []},
                failure=Failure(
                    code="PG_ROW_NOT_FOUND",
                    assertion=kind,
                    message=f"No row in {table} matching {where}",
                    expected={"table": table, "where": where, "column": column, "value": expected},
                    actual={"count": 0},
                ),
            )
        actual = rows[0].get(column)
        if actual != expected:
            return AssertionResult(
                assertion=spec,
                passed=False,
                observation={"count": len(rows), "rows": rows},
                failure=Failure(
                    code="PG_COLUMN_MISMATCH",
                    assertion=kind,
                    message=f"Column {column!r} mismatch on {table}",
                    expected=expected,
                    actual=actual,
                    details={"table": table, "where": where, "column": column},
                ),
            )
        return AssertionResult(
            assertion=spec,
            passed=True,
            observation={"count": len(rows), "rows": rows},
        )

    if kind == "count_equals":
        expected = int(params["expected"])
        actual = observer.count_rows(table, where)
        if actual != expected:
            return AssertionResult(
                assertion=spec,
                passed=False,
                observation={"count": actual},
                failure=Failure(
                    code="PG_COUNT_MISMATCH",
                    assertion=kind,
                    message=f"Row count mismatch on {table}",
                    expected=expected,
                    actual=actual,
                    details={"table": table, "where": where},
                ),
            )
        return AssertionResult(
            assertion=spec,
            passed=True,
            observation={"count": actual},
        )

    return AssertionResult(
        assertion=spec,
        passed=False,
        observation={},
        failure=Failure(
            code="PG_UNKNOWN_ASSERTION",
            assertion=kind,
            message=f"Unknown Postgres assertion kind: {kind}",
        ),
    )
