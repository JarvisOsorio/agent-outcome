from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_outcome import verify
from agent_outcome.adapters import github
from agent_outcome.cases import case_from_result, load_case, save_case
from agent_outcome.models import Receipt
from agent_outcome.storage import StorageError, Store


def test_init_idempotent_fails(tmp_path: Path):
    store = Store(tmp_path / ".agent-outcome")
    store.init()
    with pytest.raises(StorageError):
        store.init()


def test_failure_saves_reusable_case(tmp_store, github_ok):
    result = verify(
        task="bad title",
        assertions=[
            github.title_equals(
                owner="acme", repo="app", number=42, expected="Nope"
            )
        ],
        github=github_ok,
    )
    assert not result.passed
    case = case_from_result(result, name="title-regression")
    case_id = save_case(case, store=tmp_store)
    loaded = load_case(case_id, store=tmp_store)
    assert loaded.name == "title-regression"
    assert len(loaded.assertions) == 1
    assert loaded.source_failures[0]["code"] == "GITHUB_TITLE_MISMATCH"

    # Re-run against same world still fails
    again = verify(
        task=loaded.task,
        assertions=loaded.assertions,
        github=github_ok,
    )
    assert not again.passed
    assert again.failures[0].code == "GITHUB_TITLE_MISMATCH"


def test_export_import_roundtrip(tmp_store, github_ok, tmp_path: Path):
    receipt = Receipt(task="t", agent_claimed_success=True, agent_message="ok")
    tmp_store.save_receipt(receipt)
    result = verify(
        task="t",
        assertions=[github.issue_exists(owner="acme", repo="app", number=42)],
        receipt=receipt,
        github=github_ok,
    )
    tmp_store.save_run(result)
    case = case_from_result(result, name="ok-case")
    tmp_store.save_case(case)

    export_path = tmp_path / "bundle.json"
    tmp_store.export_bundle(export_path)

    other = Store(tmp_path / "other")
    other.init()
    counts = other.import_bundle(export_path)
    assert counts["cases"] == 1
    assert counts["receipts"] == 1
    assert counts["runs"] == 1
    assert other.get_case(case.id) is not None


def test_import_tampered_integrity(tmp_store, tmp_path: Path):
    tmp_store.export_bundle(tmp_path / "ok.json")
    # Create a fresh store export then tamper hash
    path = tmp_path / "bad.json"
    tmp_store.export_bundle(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["integrity"]["hash"] = "0" * 64
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    other = Store(tmp_path / "imp")
    other.init()
    with pytest.raises(StorageError, match="integrity"):
        other.import_bundle(path)


def test_strip_secrets_on_case_metadata(tmp_store, github_ok):
    result = verify(
        task="t",
        assertions=[github.issue_exists(owner="acme", repo="app", number=42)],
        github=github_ok,
    )
    case = case_from_result(result, name="sec")
    case.metadata = {"github_token": "tok_test_not_a_real_secret", "note": "safe"}
    tmp_store.save_case(case)
    loaded = tmp_store.get_case(case.id)
    assert loaded is not None
    assert loaded.metadata["github_token"] == "[REDACTED]"
    assert loaded.metadata["note"] == "safe"
