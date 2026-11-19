"""GitHub assertions and observers."""

from __future__ import annotations

import os
from typing import Any, Mapping

from agent_outcome.adapters.base import GitHubObserver, IssueSnapshot
from agent_outcome.models import AssertionResult, AssertionSpec, Failure

ADAPTER = "github"


def issue_exists(*, owner: str, repo: str, number: int) -> AssertionSpec:
    return AssertionSpec(
        kind="issue_exists",
        adapter=ADAPTER,
        params={"owner": owner, "repo": repo, "number": int(number)},
    )


def title_equals(*, owner: str, repo: str, number: int, expected: str) -> AssertionSpec:
    return AssertionSpec(
        kind="title_equals",
        adapter=ADAPTER,
        params={
            "owner": owner,
            "repo": repo,
            "number": int(number),
            "expected": expected,
        },
    )


def label_exists(*, owner: str, repo: str, number: int, label: str) -> AssertionSpec:
    return AssertionSpec(
        kind="label_exists",
        adapter=ADAPTER,
        params={
            "owner": owner,
            "repo": repo,
            "number": int(number),
            "label": label,
        },
    )


def body_contains(
    *, owner: str, repo: str, number: int, substring: str
) -> AssertionSpec:
    return AssertionSpec(
        kind="body_contains",
        adapter=ADAPTER,
        params={
            "owner": owner,
            "repo": repo,
            "number": int(number),
            "substring": substring,
        },
    )


def body_equals(*, owner: str, repo: str, number: int, expected: str) -> AssertionSpec:
    return AssertionSpec(
        kind="body_equals",
        adapter=ADAPTER,
        params={
            "owner": owner,
            "repo": repo,
            "number": int(number),
            "expected": expected,
        },
    )


def repo_equals(*, owner: str, repo: str, number: int) -> AssertionSpec:
    """Assert the observed issue belongs to owner/repo."""
    return AssertionSpec(
        kind="repo_equals",
        adapter=ADAPTER,
        params={"owner": owner, "repo": repo, "number": int(number)},
    )


class FakeGitHubObserver:
    """In-memory GitHub observer for hermetic tests."""

    def __init__(self, issues: Mapping[tuple[str, str, int], IssueSnapshot] | None = None):
        self._issues: dict[tuple[str, str, int], IssueSnapshot] = dict(issues or {})

    def put(self, issue: IssueSnapshot) -> None:
        self._issues[(issue.owner, issue.repo, issue.number)] = issue

    def get_issue(self, owner: str, repo: str, number: int) -> IssueSnapshot | None:
        return self._issues.get((owner, repo, number))


class LiveGitHubObserver:
    """GitHub REST observer. Requires GITHUB_TOKEN (or explicit token)."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = "https://api.github.com",
        client: Any | None = None,
    ):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self.base_url = base_url.rstrip("/")
        self._client = client

    def get_issue(self, owner: str, repo: str, number: int) -> IssueSnapshot | None:
        import httpx

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agent-outcome/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{number}"
        client = self._client
        owns_client = False
        if client is None:
            client = httpx.Client(timeout=30.0)
            owns_client = True
        try:
            response = client.get(url, headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            labels = tuple(
                str(lbl["name"] if isinstance(lbl, dict) else lbl)
                for lbl in (data.get("labels") or [])
            )
            return IssueSnapshot(
                owner=owner,
                repo=repo,
                number=int(data.get("number", number)),
                title=str(data.get("title") or ""),
                body=str(data.get("body") or ""),
                labels=labels,
                state=str(data.get("state") or "open"),
                raw=data,
            )
        finally:
            if owns_client:
                client.close()


def _require_issue(
    observer: GitHubObserver, params: Mapping[str, Any]
) -> tuple[IssueSnapshot | None, AssertionResult | None]:
    owner = str(params["owner"])
    repo = str(params["repo"])
    number = int(params["number"])
    issue = observer.get_issue(owner, repo, number)
    if issue is None:
        failure = Failure(
            code="GITHUB_ISSUE_NOT_FOUND",
            assertion="issue_exists",
            message=f"Issue {owner}/{repo}#{number} not found via independent observation",
            expected={"owner": owner, "repo": repo, "number": number},
            actual=None,
        )
        # Caller may remap assertion kind; return sentinel failure for missing issue.
        return None, AssertionResult(
            assertion=AssertionSpec(
                kind="issue_exists",
                adapter=ADAPTER,
                params=dict(params),
            ),
            passed=False,
            observation={"found": False},
            failure=failure,
        )
    return issue, None


_KNOWN_KINDS = {
    "issue_exists",
    "title_equals",
    "label_exists",
    "body_contains",
    "body_equals",
    "repo_equals",
}


def evaluate(spec: AssertionSpec, observer: GitHubObserver) -> AssertionResult:
    """Evaluate a GitHub assertion against an independent observer."""
    kind = spec.kind
    params = spec.params

    if kind not in _KNOWN_KINDS:
        return AssertionResult(
            assertion=spec,
            passed=False,
            observation={},
            failure=Failure(
                code="GITHUB_UNKNOWN_ASSERTION",
                assertion=kind,
                message=f"Unknown GitHub assertion kind: {kind}",
            ),
        )

    if kind == "issue_exists":
        issue, missing = _require_issue(observer, params)
        if missing is not None:
            return AssertionResult(
                assertion=spec,
                passed=False,
                observation={"found": False},
                failure=Failure(
                    code="GITHUB_ISSUE_NOT_FOUND",
                    assertion=spec.kind,
                    message=missing.failure.message if missing.failure else "not found",
                    expected=missing.failure.expected if missing.failure else None,
                    actual=None,
                ),
            )
        assert issue is not None
        return AssertionResult(
            assertion=spec,
            passed=True,
            observation=issue.to_dict(),
        )

    issue, missing = _require_issue(observer, params)
    if issue is None:
        assert missing is not None and missing.failure is not None
        return AssertionResult(
            assertion=spec,
            passed=False,
            observation={"found": False},
            failure=Failure(
                code="GITHUB_ISSUE_NOT_FOUND",
                assertion=spec.kind,
                message=missing.failure.message,
                expected=missing.failure.expected,
                actual=None,
            ),
        )

    if kind == "title_equals":
        expected = str(params["expected"])
        if issue.title != expected:
            return AssertionResult(
                assertion=spec,
                passed=False,
                observation=issue.to_dict(),
                failure=Failure(
                    code="GITHUB_TITLE_MISMATCH",
                    assertion=kind,
                    message=f"Title mismatch for {issue.owner}/{issue.repo}#{issue.number}",
                    expected=expected,
                    actual=issue.title,
                ),
            )
        return AssertionResult(assertion=spec, passed=True, observation=issue.to_dict())

    if kind == "label_exists":
        label = str(params["label"])
        if label not in issue.labels:
            return AssertionResult(
                assertion=spec,
                passed=False,
                observation=issue.to_dict(),
                failure=Failure(
                    code="GITHUB_LABEL_MISSING",
                    assertion=kind,
                    message=f"Label {label!r} missing on {issue.owner}/{issue.repo}#{issue.number}",
                    expected=label,
                    actual=list(issue.labels),
                ),
            )
        return AssertionResult(assertion=spec, passed=True, observation=issue.to_dict())

    if kind == "body_contains":
        substring = str(params["substring"])
        if substring not in (issue.body or ""):
            return AssertionResult(
                assertion=spec,
                passed=False,
                observation=issue.to_dict(),
                failure=Failure(
                    code="GITHUB_BODY_MISMATCH",
                    assertion=kind,
                    message=f"Body does not contain {substring!r}",
                    expected={"contains": substring},
                    actual=issue.body,
                ),
            )
        return AssertionResult(assertion=spec, passed=True, observation=issue.to_dict())

    if kind == "body_equals":
        expected = str(params["expected"])
        if issue.body != expected:
            return AssertionResult(
                assertion=spec,
                passed=False,
                observation=issue.to_dict(),
                failure=Failure(
                    code="GITHUB_BODY_MISMATCH",
                    assertion=kind,
                    message="Body does not equal expected value",
                    expected=expected,
                    actual=issue.body,
                ),
            )
        return AssertionResult(assertion=spec, passed=True, observation=issue.to_dict())

    if kind == "repo_equals":
        expected_owner = str(params["owner"])
        expected_repo = str(params["repo"])
        if issue.owner != expected_owner or issue.repo != expected_repo:
            return AssertionResult(
                assertion=spec,
                passed=False,
                observation=issue.to_dict(),
                failure=Failure(
                    code="GITHUB_REPO_MISMATCH",
                    assertion=kind,
                    message="Issue repo does not match expected owner/repo",
                    expected={"owner": expected_owner, "repo": expected_repo},
                    actual={"owner": issue.owner, "repo": issue.repo},
                ),
            )
        return AssertionResult(assertion=spec, passed=True, observation=issue.to_dict())

    # All known kinds handled above.
    return AssertionResult(
        assertion=spec,
        passed=False,
        observation={},
        failure=Failure(
            code="GITHUB_UNKNOWN_ASSERTION",
            assertion=kind,
            message=f"Unknown GitHub assertion kind: {kind}",
        ),
    )
