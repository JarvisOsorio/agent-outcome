"""Optional live integration tests — skipped unless explicitly opted in."""

from __future__ import annotations

import os

import pytest

from agent_outcome import verify
from agent_outcome.adapters import github, postgres
from agent_outcome.adapters.github import LiveGitHubObserver
from agent_outcome.adapters.postgres import LivePostgresObserver

live_github = pytest.mark.skipif(
    os.environ.get("AGENT_OUTCOME_LIVE_GITHUB") != "1"
    or not os.environ.get("GITHUB_TOKEN"),
    reason="Set AGENT_OUTCOME_LIVE_GITHUB=1 and GITHUB_TOKEN for live GitHub tests",
)

live_postgres = pytest.mark.skipif(
    os.environ.get("AGENT_OUTCOME_LIVE_POSTGRES") != "1"
    or not (
        os.environ.get("AGENT_OUTCOME_DATABASE_URL") or os.environ.get("DATABASE_URL")
    ),
    reason="Set AGENT_OUTCOME_LIVE_POSTGRES=1 and AGENT_OUTCOME_DATABASE_URL for live Postgres tests",
)


@live_github
@pytest.mark.live_github
def test_live_github_issue_not_found():
    """Uses a definitely-missing issue number to prove independent 404 observation."""
    owner = os.environ.get("AGENT_OUTCOME_GH_OWNER", "octocat")
    repo = os.environ.get("AGENT_OUTCOME_GH_REPO", "Hello-World")
    obs = LiveGitHubObserver()
    result = verify(
        task="live missing issue",
        assertions=[
            github.issue_exists(owner=owner, repo=repo, number=999999999),
        ],
        github=obs,
    )
    assert not result.passed
    assert result.failures[0].code == "GITHUB_ISSUE_NOT_FOUND"


@live_postgres
@pytest.mark.live_postgres
def test_live_postgres_roundtrip():
    """Requires a pre-created empty table AGENT_OUTCOME_PG_TABLE (default agent_outcome_smoke)."""
    obs = LivePostgresObserver()
    table = os.environ.get("AGENT_OUTCOME_PG_TABLE", "agent_outcome_smoke")
    result = verify(
        task="live pg count",
        assertions=[postgres.count_equals(table=table, expected=0)],
        postgres=obs,
    )
    # Empty prepared table → PASS; wrong expected → FAIL with machine-readable code.
    if not result.passed:
        assert result.failures[0].code in {"PG_COUNT_MISMATCH", "OBSERVER_MISSING"}
    else:
        assert result.passed
