"""Stable CLI / programmatic exit codes."""

from __future__ import annotations

PASS = 0
ASSERTION_FAILURE = 1
INVALID_INPUT = 2
INFRA_ERROR = 3

EXIT_CODE_MEANINGS = {
    PASS: "Pass — all assertions succeeded",
    ASSERTION_FAILURE: "Assertion failure — one or more postconditions failed",
    INVALID_INPUT: "Invalid input — malformed case, receipt, or arguments",
    INFRA_ERROR: "Infrastructure error — storage, observer, or runtime failure",
}
