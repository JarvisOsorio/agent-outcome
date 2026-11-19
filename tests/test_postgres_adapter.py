from __future__ import annotations

import pytest

from agent_outcome.adapters.postgres import (
    FakePostgresObserver,
    LivePostgresObserver,
    column_equals,
    count_equals,
    evaluate,
    row_exists,
)
from agent_outcome.models import AssertionSpec


def test_fake_filters(postgres_ok):
    rows = postgres_ok.fetch_rows("orders", {"status": "paid"})
    assert len(rows) == 2
    assert postgres_ok.count_rows("orders", {"status": "pending"}) == 1


def test_evaluate_row_missing(postgres_ok):
    spec = row_exists(table="orders", where={"id": "missing"})
    result = evaluate(spec, postgres_ok)
    assert not result.passed
    assert result.failure and result.failure.code == "PG_ROW_NOT_FOUND"


def test_evaluate_count(postgres_ok):
    spec = count_equals(table="orders", expected=3)
    assert evaluate(spec, postgres_ok).passed
    bad = count_equals(table="orders", expected=99)
    result = evaluate(bad, postgres_ok)
    assert result.failure and result.failure.code == "PG_COUNT_MISMATCH"


def test_column_equals_builders():
    spec = column_equals(
        table="orders", where={"id": "1"}, column="status", expected="paid"
    )
    assert spec.adapter == "postgres"


def test_unknown_kind(postgres_ok):
    spec = AssertionSpec(kind="nope", adapter="postgres", params={"table": "orders"})
    result = evaluate(spec, postgres_ok)
    assert result.failure and result.failure.code == "PG_UNKNOWN_ASSERTION"


def test_live_invalid_ident():
    obs = LivePostgresObserver(dsn="postgresql://unused")

    class Conn:
        def cursor(self):
            raise AssertionError("should fail before execute")

        def close(self):
            pass

    obs._connection = Conn()
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        obs.fetch_rows("orders;drop", {"id": 1})
