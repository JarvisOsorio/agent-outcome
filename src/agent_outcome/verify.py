"""Core verification engine — independent observation only."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from agent_outcome.adapters import github as github_adapter
from agent_outcome.adapters import postgres as postgres_adapter
from agent_outcome.adapters.base import GitHubObserver, PostgresObserver
from agent_outcome.models import (
    AssertionResult,
    AssertionSpec,
    Failure,
    Receipt,
    VerificationResult,
)


class ObserverRegistry:
    """Named observers available to assertion evaluation."""

    def __init__(
        self,
        *,
        github: GitHubObserver | None = None,
        postgres: PostgresObserver | None = None,
        extras: Mapping[str, Any] | None = None,
    ):
        self.github = github
        self.postgres = postgres
        self.extras = dict(extras or {})

    def get(self, name: str) -> Any:
        if name == "github":
            return self.github
        if name == "postgres":
            return self.postgres
        return self.extras.get(name)


def _coerce_assertions(assertions: Sequence[AssertionSpec | Mapping[str, Any]]) -> list[AssertionSpec]:
    out: list[AssertionSpec] = []
    for item in assertions:
        if isinstance(item, AssertionSpec):
            out.append(item)
        else:
            out.append(AssertionSpec.from_dict(item))
    return out


def _evaluate_one(spec: AssertionSpec, registry: ObserverRegistry) -> AssertionResult:
    observer = registry.get(spec.adapter)
    if observer is None:
        return AssertionResult(
            assertion=spec,
            passed=False,
            observation={},
            failure=Failure(
                code="OBSERVER_MISSING",
                assertion=spec.kind,
                message=(
                    f"No observer registered for adapter {spec.adapter!r}. "
                    "Inject observers=... or configure live credentials."
                ),
                details={"adapter": spec.adapter},
            ),
        )

    if spec.adapter == "github":
        return github_adapter.evaluate(spec, observer)
    if spec.adapter == "postgres":
        return postgres_adapter.evaluate(spec, observer)

    return AssertionResult(
        assertion=spec,
        passed=False,
        observation={},
        failure=Failure(
            code="UNKNOWN_ADAPTER",
            assertion=spec.kind,
            message=f"Unknown adapter: {spec.adapter}",
        ),
    )


def verify(
    *,
    task: str,
    assertions: Sequence[AssertionSpec | Mapping[str, Any]],
    receipt: Receipt | Mapping[str, Any] | None = None,
    observers: Mapping[str, Any] | None = None,
    github: GitHubObserver | None = None,
    postgres: PostgresObserver | None = None,
) -> VerificationResult:
    """Run deterministic assertions via independent observers.

    The optional receipt is attached for context only. An agent claiming
    success in the receipt cannot make this function return passed=True
    without successful independent observations.
    """
    specs = _coerce_assertions(assertions)
    if not specs:
        return VerificationResult(
            task=task,
            passed=False,
            assertion_results=[],
            failures=[
                Failure(
                    code="NO_ASSERTIONS",
                    assertion="verify",
                    message="Verification requires at least one assertion",
                )
            ],
            notes=["empty assertion plan"],
        )

    receipt_obj: Receipt | None = None
    if isinstance(receipt, Receipt):
        receipt_obj = receipt
    elif isinstance(receipt, Mapping):
        receipt_obj = Receipt.from_dict(receipt)

    obs_map = dict(observers or {})
    registry = ObserverRegistry(
        github=github or obs_map.get("github"),
        postgres=postgres or obs_map.get("postgres"),
        extras={k: v for k, v in obs_map.items() if k not in {"github", "postgres"}},
    )

    results: list[AssertionResult] = []
    failures: list[Failure] = []
    for spec in specs:
        result = _evaluate_one(spec, registry)
        results.append(result)
        if not result.passed and result.failure is not None:
            failures.append(result.failure)

    notes: list[str] = []
    if receipt_obj is not None:
        notes.append(
            "Receipt attached as context only; agent_claimed_success is not evidence."
        )
        if receipt_obj.agent_claimed_success and failures:
            notes.append(
                "Agent claimed success but independent verification FAILED — "
                "receipt was not trusted as proof."
            )

    return VerificationResult(
        task=task,
        passed=len(failures) == 0,
        assertion_results=results,
        failures=failures,
        receipt_id=receipt_obj.id if receipt_obj else None,
        notes=notes,
    )
