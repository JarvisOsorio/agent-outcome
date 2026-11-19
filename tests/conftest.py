from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_outcome.adapters.base import IssueSnapshot
from agent_outcome.adapters.github import FakeGitHubObserver
from agent_outcome.adapters.postgres import FakePostgresObserver


@pytest.fixture
def tmp_store(tmp_path: Path):
    from agent_outcome.storage import Store

    store = Store(tmp_path / ".agent-outcome")
    store.init()
    return store


@pytest.fixture
def github_ok() -> FakeGitHubObserver:
    obs = FakeGitHubObserver()
    obs.put(
        IssueSnapshot(
            owner="acme",
            repo="app",
            number=42,
            title="Fix authentication",
            body="Broken oauth callback for users",
            labels=("bug", "security"),
        )
    )
    return obs


@pytest.fixture
def postgres_ok() -> FakePostgresObserver:
    return FakePostgresObserver(
        {
            "orders": [
                {"id": "ord_1", "status": "paid", "amount": 10},
                {"id": "ord_2", "status": "paid", "amount": 20},
                {"id": "ord_3", "status": "pending", "amount": 5},
            ]
        }
    )


@pytest.fixture
def github_fixture_path(tmp_path: Path, github_ok: FakeGitHubObserver) -> Path:
    issue = github_ok.get_issue("acme", "app", 42)
    assert issue is not None
    path = tmp_path / "github.json"
    path.write_text(
        json.dumps({"issues": [issue.to_dict()]}, indent=2),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def postgres_fixture_path(tmp_path: Path, postgres_ok: FakePostgresObserver) -> Path:
    path = tmp_path / "postgres.json"
    path.write_text(
        json.dumps(
            {
                "tables": {
                    "orders": postgres_ok.fetch_rows("orders", {}),
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
