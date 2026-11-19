"""Observer protocols — adapters observe independently; agents do not self-certify."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class IssueSnapshot:
    """Observed GitHub issue state (independent of agent claims)."""

    owner: str
    repo: str
    number: int
    title: str
    body: str = ""
    labels: tuple[str, ...] = ()
    state: str = "open"
    raw: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "repo": self.repo,
            "number": self.number,
            "title": self.title,
            "body": self.body,
            "labels": list(self.labels),
            "state": self.state,
        }


@runtime_checkable
class GitHubObserver(Protocol):
    def get_issue(self, owner: str, repo: str, number: int) -> IssueSnapshot | None:
        """Return the issue as observed now, or None if missing."""


@runtime_checkable
class PostgresObserver(Protocol):
    def fetch_rows(
        self, table: str, where: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        """Return matching rows as dicts (independent DB observation)."""

    def count_rows(self, table: str, where: Mapping[str, Any] | None = None) -> int:
        """Return COUNT(*) for the filter."""
