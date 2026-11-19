"""Failure → reusable verification case."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_outcome.models import VerificationCase, VerificationResult, new_id, utc_now_iso
from agent_outcome.storage import Store, load_case_file


def case_from_result(
    result: VerificationResult,
    *,
    name: str | None = None,
    assertions: list[Any] | None = None,
) -> VerificationCase:
    """Build a reusable case from a verification result (typically a failure)."""
    specs = assertions or [ar.assertion for ar in result.assertion_results]
    case_name = name or f"repro-{result.task or result.run_id}"
    return VerificationCase(
        id=new_id("case"),
        name=case_name,
        task=result.task,
        assertions=list(specs),
        source_run_id=result.run_id,
        source_failures=[f.to_dict() for f in result.failures],
        receipt_id=result.receipt_id,
        created_at=utc_now_iso(),
        metadata={"generated_from": "failure" if not result.passed else "result"},
    )


def save_case(case: VerificationCase, store: Store | None = None) -> str:
    st = store or Store()
    if not st.exists:
        st.init()
    return st.save_case(case)


def load_case(case_id_or_path: str, store: Store | None = None) -> VerificationCase:
    path = Path(case_id_or_path)
    if path.is_file():
        return load_case_file(path)
    st = store or Store()
    case = st.get_case(case_id_or_path)
    if case is None:
        raise FileNotFoundError(f"Case not found: {case_id_or_path}")
    return case
