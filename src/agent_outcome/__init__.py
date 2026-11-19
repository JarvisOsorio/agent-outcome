"""Agent Outcome — independent postcondition verification for AI agent side effects."""

from __future__ import annotations

from agent_outcome.cases import case_from_result, load_case, save_case
from agent_outcome.models import (
    AssertionResult,
    AssertionSpec,
    Failure,
    Receipt,
    VerificationCase,
    VerificationResult,
)
from agent_outcome.verify import verify

__all__ = [
    "AssertionResult",
    "AssertionSpec",
    "Failure",
    "Receipt",
    "VerificationCase",
    "VerificationResult",
    "case_from_result",
    "load_case",
    "save_case",
    "verify",
]

__version__ = "0.1.0"
