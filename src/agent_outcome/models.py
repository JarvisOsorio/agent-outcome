"""Core data models for Agent Outcome."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
import uuid


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class Failure:
    """Machine-readable assertion failure."""

    code: str
    assertion: str
    message: str
    expected: Any = None
    actual: Any = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "assertion": self.assertion,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class AssertionSpec:
    """Serializable assertion plan entry."""

    kind: str
    adapter: str
    params: Mapping[str, Any]
    id: str = field(default_factory=lambda: new_id("asrt"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "adapter": self.adapter,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AssertionSpec:
        return cls(
            id=str(data.get("id") or new_id("asrt")),
            kind=str(data["kind"]),
            adapter=str(data["adapter"]),
            params=dict(data.get("params") or {}),
        )


@dataclass(frozen=True)
class AssertionResult:
    """Outcome of a single assertion."""

    assertion: AssertionSpec
    passed: bool
    observation: Mapping[str, Any] = field(default_factory=dict)
    failure: Failure | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion": self.assertion.to_dict(),
            "passed": self.passed,
            "observation": dict(self.observation),
            "failure": self.failure.to_dict() if self.failure else None,
        }


@dataclass
class Receipt:
    """Optional execution receipt — context only, never sole evidence of success."""

    schema: str = "agent-outcome.receipt.v1"
    id: str = field(default_factory=lambda: new_id("rcpt"))
    task: str = ""
    agent_claimed_success: bool | None = None
    agent_message: str | None = None
    tools: list[Mapping[str, Any]] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "id": self.id,
            "task": self.task,
            "agent_claimed_success": self.agent_claimed_success,
            "agent_message": self.agent_message,
            "tools": [dict(t) for t in self.tools],
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Receipt:
        return cls(
            schema=str(data.get("schema") or "agent-outcome.receipt.v1"),
            id=str(data.get("id") or new_id("rcpt")),
            task=str(data.get("task") or ""),
            agent_claimed_success=data.get("agent_claimed_success"),
            agent_message=data.get("agent_message"),
            tools=[dict(t) for t in (data.get("tools") or [])],
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class VerificationResult:
    """Aggregate verification outcome."""

    task: str
    passed: bool
    assertion_results: list[AssertionResult]
    failures: list[Failure]
    receipt_id: str | None = None
    case_id: str | None = None
    run_id: str = field(default_factory=lambda: new_id("run"))
    observed_at: str = field(default_factory=utc_now_iso)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "passed": self.passed,
            "assertion_results": [r.to_dict() for r in self.assertion_results],
            "failures": [f.to_dict() for f in self.failures],
            "receipt_id": self.receipt_id,
            "case_id": self.case_id,
            "observed_at": self.observed_at,
            "notes": list(self.notes),
        }


@dataclass
class VerificationCase:
    """Reusable verification case (often generated from a failure)."""

    schema: str = "agent-outcome.case.v1"
    id: str = field(default_factory=lambda: new_id("case"))
    name: str = ""
    task: str = ""
    assertions: list[AssertionSpec] = field(default_factory=list)
    source_run_id: str | None = None
    source_failures: list[dict[str, Any]] = field(default_factory=list)
    receipt_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "id": self.id,
            "name": self.name,
            "task": self.task,
            "assertions": [a.to_dict() for a in self.assertions],
            "source_run_id": self.source_run_id,
            "source_failures": list(self.source_failures),
            "receipt_id": self.receipt_id,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VerificationCase:
        assertions = [
            AssertionSpec.from_dict(a) for a in (data.get("assertions") or [])
        ]
        return cls(
            schema=str(data.get("schema") or "agent-outcome.case.v1"),
            id=str(data.get("id") or new_id("case")),
            name=str(data.get("name") or ""),
            task=str(data.get("task") or ""),
            assertions=assertions,
            source_run_id=data.get("source_run_id"),
            source_failures=[dict(f) for f in (data.get("source_failures") or [])],
            receipt_id=data.get("receipt_id"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            metadata=dict(data.get("metadata") or {}),
        )


def strip_secrets(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop obvious secret-bearing keys before persistence."""
    if not mapping:
        return {}
    blocked = {
        "token",
        "password",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "database_url",
        "dsn",
        "github_token",
    }
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        lowered = key.lower().replace("-", "_")
        if lowered in blocked or any(b in lowered for b in ("token", "password", "secret", "api_key")):
            out[key] = "[REDACTED]"
        elif isinstance(value, Mapping):
            out[key] = strip_secrets(value)
        else:
            out[key] = value
    return out


def dataclass_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()  # type: ignore[no-any-return]
    return asdict(obj)
