from __future__ import annotations

from agent_outcome import verify
from agent_outcome.adapters import github, postgres
from agent_outcome.adapters.base import IssueSnapshot
from agent_outcome.adapters.github import FakeGitHubObserver
from agent_outcome.models import Receipt


def test_verify_pass_github_and_postgres(github_ok, postgres_ok):
    result = verify(
        task="Create issue and record order",
        assertions=[
            github.issue_exists(owner="acme", repo="app", number=42),
            github.title_equals(
                owner="acme", repo="app", number=42, expected="Fix authentication"
            ),
            github.label_exists(owner="acme", repo="app", number=42, label="bug"),
            github.body_contains(owner="acme", repo="app", number=42, substring="oauth"),
            github.repo_equals(owner="acme", repo="app", number=42),
            postgres.row_exists(table="orders", where={"id": "ord_1"}),
            postgres.column_equals(
                table="orders", where={"id": "ord_1"}, column="status", expected="paid"
            ),
            postgres.count_equals(table="orders", where={"status": "paid"}, expected=2),
        ],
        observers={"github": github_ok, "postgres": postgres_ok},
    )
    assert result.passed
    assert result.failures == []
    assert len(result.assertion_results) == 8


def test_verify_fail_wrong_title_has_code(github_ok):
    result = verify(
        task="Wrong title should fail",
        assertions=[
            github.title_equals(
                owner="acme", repo="app", number=42, expected="Completely wrong"
            )
        ],
        github=github_ok,
    )
    assert not result.passed
    assert result.failures[0].code == "GITHUB_TITLE_MISMATCH"
    assert result.failures[0].expected == "Completely wrong"
    assert result.failures[0].actual == "Fix authentication"


def test_verify_fail_missing_label(github_ok):
    result = verify(
        task="Missing label",
        assertions=[
            github.label_exists(owner="acme", repo="app", number=42, label="wontfix")
        ],
        github=github_ok,
    )
    assert not result.passed
    assert result.failures[0].code == "GITHUB_LABEL_MISSING"


def test_verify_fail_wrong_row(postgres_ok):
    result = verify(
        task="Wrong row",
        assertions=[
            postgres.column_equals(
                table="orders",
                where={"id": "ord_1"},
                column="status",
                expected="cancelled",
            )
        ],
        postgres=postgres_ok,
    )
    assert not result.passed
    assert result.failures[0].code == "PG_COLUMN_MISMATCH"
    assert result.failures[0].actual == "paid"


def test_agent_claim_alone_cannot_pass():
    """Hard rule: receipt/agent success text is never sole evidence."""
    receipt = Receipt(
        task="Create issue",
        agent_claimed_success=True,
        agent_message="Done! Issue created successfully.",
    )
    empty = FakeGitHubObserver()  # no issues observed
    result = verify(
        task="Create issue",
        assertions=[github.issue_exists(owner="acme", repo="app", number=1)],
        receipt=receipt,
        github=empty,
    )
    assert not result.passed
    assert result.failures[0].code == "GITHUB_ISSUE_NOT_FOUND"
    assert result.receipt_id == receipt.id
    assert any("not trusted" in n.lower() or "FAILED" in n for n in result.notes)


def test_missing_observer_fails_closed():
    result = verify(
        task="No observer",
        assertions=[github.issue_exists(owner="a", repo="b", number=1)],
    )
    assert not result.passed
    assert result.failures[0].code == "OBSERVER_MISSING"


def test_empty_assertions_fail():
    result = verify(task="empty", assertions=[])
    assert not result.passed
    assert result.failures[0].code == "NO_ASSERTIONS"


def test_issue_not_found_for_dependent_assertion():
    obs = FakeGitHubObserver()
    result = verify(
        task="missing",
        assertions=[
            github.title_equals(owner="a", repo="b", number=9, expected="x"),
        ],
        github=obs,
    )
    assert result.failures[0].code == "GITHUB_ISSUE_NOT_FOUND"


def test_body_equals_and_repo_mismatch():
    obs = FakeGitHubObserver()
    obs.put(
        IssueSnapshot(
            owner="other",
            repo="place",
            number=1,
            title="t",
            body="exact",
            labels=(),
        )
    )
    # body ok
    ok = verify(
        task="body",
        assertions=[github.body_equals(owner="other", repo="place", number=1, expected="exact")],
        github=obs,
    )
    assert ok.passed
    # repo mismatch: observer returns different owner than asserted params after fetch —
    # Fake returns keyed by params; simulate by putting under expected key with wrong owner fields
    obs2 = FakeGitHubObserver()
    obs2.put(
        IssueSnapshot(
            owner="wrong",
            repo="place",
            number=1,
            title="t",
            body="",
            labels=(),
        )
    )
    # Look up uses owner/repo/number from assertion — so put under acme/app/1 with wrong owner field
    obs3 = FakeGitHubObserver()
    snap = IssueSnapshot(owner="evil", repo="x", number=1, title="t", body="", labels=())
    obs3._issues[("acme", "app", 1)] = snap  # type: ignore[attr-defined]
    bad = verify(
        task="repo",
        assertions=[github.repo_equals(owner="acme", repo="app", number=1)],
        github=obs3,
    )
    assert not bad.passed
    assert bad.failures[0].code == "GITHUB_REPO_MISMATCH"
