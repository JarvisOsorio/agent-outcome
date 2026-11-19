from __future__ import annotations

from agent_outcome.adapters.base import IssueSnapshot
from agent_outcome.adapters.github import (
    FakeGitHubObserver,
    LiveGitHubObserver,
    body_contains,
    evaluate,
    issue_exists,
    label_exists,
    title_equals,
)


def test_fake_put_get():
    obs = FakeGitHubObserver()
    obs.put(
        IssueSnapshot(
            owner="o", repo="r", number=3, title="Hello", body="b", labels=("x",)
        )
    )
    got = obs.get_issue("o", "r", 3)
    assert got is not None
    assert got.title == "Hello"
    assert obs.get_issue("o", "r", 99) is None


def test_live_observer_404(monkeypatch):
    class Resp:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError("should not raise on 404")

        def json(self):
            return {}

    class Client:
        def get(self, url, headers=None):
            assert "/repos/o/r/issues/1" in url
            return Resp()

        def close(self):
            pass

    obs = LiveGitHubObserver(token="fake", client=Client())
    assert obs.get_issue("o", "r", 1) is None


def test_live_observer_success():
    class Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "number": 7,
                "title": "T",
                "body": "Body",
                "labels": [{"name": "bug"}, "extra"],
                "state": "open",
            }

    class Client:
        def get(self, url, headers=None):
            assert headers["Authorization"] == "Bearer tok"
            return Resp()

        def close(self):
            pass

    obs = LiveGitHubObserver(token="tok", client=Client())
    issue = obs.get_issue("o", "r", 7)
    assert issue is not None
    assert issue.title == "T"
    assert issue.labels == ("bug", "extra")


def test_evaluate_unknown_kind(github_ok):
    from agent_outcome.models import AssertionSpec

    spec = AssertionSpec(kind="nope", adapter="github", params={"owner": "a", "repo": "b", "number": 1})
    result = evaluate(spec, github_ok)
    assert not result.passed
    assert result.failure and result.failure.code == "GITHUB_UNKNOWN_ASSERTION"


def test_builders():
    assert issue_exists(owner="a", repo="b", number=1).kind == "issue_exists"
    assert title_equals(owner="a", repo="b", number=1, expected="t").params["expected"] == "t"
    assert label_exists(owner="a", repo="b", number=1, label="bug").params["label"] == "bug"
    assert body_contains(owner="a", repo="b", number=1, substring="x").params["substring"] == "x"
