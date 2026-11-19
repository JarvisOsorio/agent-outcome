"""Built-in adapters: GitHub and PostgreSQL."""

from __future__ import annotations

from agent_outcome.adapters import github, postgres
from agent_outcome.adapters.base import GitHubObserver, IssueSnapshot, PostgresObserver

__all__ = [
    "GitHubObserver",
    "IssueSnapshot",
    "PostgresObserver",
    "github",
    "postgres",
]
