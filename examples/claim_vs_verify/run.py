#!/usr/bin/env python3
"""Demonstrate: agent claims success → independent PASS and FAIL paths."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agent_outcome import verify
from agent_outcome.adapters.base import IssueSnapshot
from agent_outcome.adapters.github import FakeGitHubObserver
from agent_outcome.adapters.postgres import FakePostgresObserver
from agent_outcome.cases import case_from_result
from agent_outcome.models import AssertionSpec, Receipt

HERE = Path(__file__).resolve().parent


def load_assertions(name: str) -> tuple[str, list[AssertionSpec]]:
    data = json.loads((HERE / name).read_text(encoding="utf-8"))
    specs = [AssertionSpec.from_dict(a) for a in data["assertions"]]
    return str(data["task"]), specs


def build_observers() -> dict:
    gh_data = json.loads((HERE / "github_world.json").read_text(encoding="utf-8"))
    gh = FakeGitHubObserver()
    for item in gh_data["issues"]:
        gh.put(
            IssueSnapshot(
                owner=item["owner"],
                repo=item["repo"],
                number=int(item["number"]),
                title=item["title"],
                body=item.get("body", ""),
                labels=tuple(item.get("labels") or []),
                state=item.get("state", "open"),
            )
        )
    pg_data = json.loads((HERE / "postgres_world.json").read_text(encoding="utf-8"))
    pg = FakePostgresObserver(pg_data["tables"])
    return {"github": gh, "postgres": pg}


def main() -> int:
    receipt = Receipt.from_dict(
        json.loads((HERE / "receipt_claim_success.json").read_text(encoding="utf-8"))
    )
    observers = build_observers()

    print("=== Agent receipt (context only) ===")
    print(f"agent_claimed_success={receipt.agent_claimed_success}")
    print(f"agent_message={receipt.agent_message!r}")
    print()

    task, pass_assertions = load_assertions("assertions_pass.json")
    pass_result = verify(
        task=task,
        assertions=pass_assertions,
        receipt=receipt,
        observers=observers,
    )
    print("=== Independent verify (expected world) ===")
    print(f"passed={pass_result.passed} failures={len(pass_result.failures)}")
    assert pass_result.passed, pass_result.failures
    print("PASS — observations match expected postconditions")
    print()

    _, fail_assertions = load_assertions("assertions_fail.json")
    fail_result = verify(
        task=task,
        assertions=fail_assertions,
        receipt=receipt,
        observers=observers,
    )
    print("=== Independent verify (intentional wrong expectations) ===")
    print(f"passed={fail_result.passed} failures={len(fail_result.failures)}")
    for f in fail_result.failures:
        print(f"  {f.code}: {f.message}")
    assert not fail_result.passed
    codes = {f.code for f in fail_result.failures}
    assert "GITHUB_TITLE_MISMATCH" in codes
    assert "GITHUB_LABEL_MISSING" in codes
    assert "PG_COLUMN_MISMATCH" in codes
    assert any("not trusted" in n.lower() or "FAILED" in n for n in fail_result.notes)
    case = case_from_result(fail_result, name="claim-lie")
    print(f"Reusable failure case id={case.id} assertions={len(case.assertions)}")
    print("FAIL path OK — agent claim ignored; machine-readable failures produced")
    print()
    print("Demo complete.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"DEMO ASSERTION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
