from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_outcome.cli import main
from agent_outcome.exit_codes import ASSERTION_FAILURE, INFRA_ERROR, INVALID_INPUT, PASS


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / ".agent-outcome"


def test_cli_init_doctor_export_import(
    root: Path, tmp_path: Path, github_fixture_path: Path, postgres_fixture_path: Path
):
    assert main(["--root", str(root), "init", "--json"]) == PASS
    assert main(["--root", str(root), "init"]) == INFRA_ERROR

    assert main(["--root", str(root), "doctor", "--json"]) == PASS

    assertions = tmp_path / "assertions.json"
    assertions.write_text(
        json.dumps(
            {
                "task": "Create GitHub issue and order",
                "assertions": [
                    {
                        "kind": "issue_exists",
                        "adapter": "github",
                        "params": {"owner": "acme", "repo": "app", "number": 42},
                    },
                    {
                        "kind": "title_equals",
                        "adapter": "github",
                        "params": {
                            "owner": "acme",
                            "repo": "app",
                            "number": 42,
                            "expected": "Fix authentication",
                        },
                    },
                    {
                        "kind": "row_exists",
                        "adapter": "postgres",
                        "params": {"table": "orders", "where": {"id": "ord_1"}},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema": "agent-outcome.receipt.v1",
                "task": "Create GitHub issue and order",
                "agent_claimed_success": True,
                "agent_message": "All good",
            }
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "--root",
            str(root),
            "verify",
            "--assertions",
            str(assertions),
            "--receipt",
            str(receipt),
            "--github-fixture",
            str(github_fixture_path),
            "--postgres-fixture",
            str(postgres_fixture_path),
            "--json",
            "--save-case",
            "--case-name",
            "golden",
        ]
    )
    assert code == PASS

    # intentional fail
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "task": "wrong title",
                "assertions": [
                    {
                        "kind": "title_equals",
                        "adapter": "github",
                        "params": {
                            "owner": "acme",
                            "repo": "app",
                            "number": 42,
                            "expected": "Wrong Title",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    code = main(
        [
            "--root",
            str(root),
            "verify",
            "--assertions",
            str(bad),
            "--github-fixture",
            str(github_fixture_path),
            "--save-on-fail",
            "--case-name",
            "title-fail",
            "--json",
        ]
    )
    assert code == ASSERTION_FAILURE

    # test saved case
    code = main(
        [
            "--root",
            str(root),
            "test",
            "title-fail",
            "--github-fixture",
            str(github_fixture_path),
            "--json",
        ]
    )
    assert code == ASSERTION_FAILURE

    # inspect
    assert main(["--root", str(root), "inspect", "golden", "--json"]) == PASS

    export_path = tmp_path / "out.json"
    assert main(["--root", str(root), "export", str(export_path), "--json"]) == PASS
    other = tmp_path / "other-store"
    assert main(["--root", str(other), "import", str(export_path), "--json"]) == PASS


def test_cli_invalid_and_missing_observers(root: Path, tmp_path: Path):
    main(["--root", str(root), "init"])
    assert main(["--root", str(root), "verify", "--json"]) == INVALID_INPUT
    assertions = tmp_path / "a.json"
    assertions.write_text(
        json.dumps(
            {
                "assertions": [
                    {
                        "kind": "issue_exists",
                        "adapter": "github",
                        "params": {"owner": "a", "repo": "b", "number": 1},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(["--root", str(root), "verify", "--assertions", str(assertions)])
        == INFRA_ERROR
    )


def test_cli_inspect_file(tmp_path: Path, root: Path):
    main(["--root", str(root), "init"])
    case_path = tmp_path / "case.json"
    case_path.write_text(
        json.dumps(
            {
                "schema": "agent-outcome.case.v1",
                "name": "c",
                "task": "t",
                "assertions": [],
            }
        ),
        encoding="utf-8",
    )
    assert main(["--root", str(root), "inspect", str(case_path)]) == PASS


def test_doctor_exit_codes_documented(root: Path, capsys):
    main(["--root", str(root), "init"])
    assert main(["--root", str(root), "doctor"]) == PASS
    out = capsys.readouterr().out
    assert "0:" in out
    assert "1:" in out
    assert "trusts_agent_success_text=False" in out
