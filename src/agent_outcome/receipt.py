"""JSON execution receipt load/validate — context only, never sole evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from agent_outcome.models import Receipt


class ReceiptError(ValueError):
    """Invalid receipt input."""


SUPPORTED_SCHEMAS = {"agent-outcome.receipt.v1"}


def load_receipt(path: str | Path) -> Receipt:
    raw_path = Path(path)
    try:
        data = json.loads(raw_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReceiptError(f"Receipt not found: {raw_path}") from exc
    except json.JSONDecodeError as exc:
        raise ReceiptError(f"Receipt is not valid JSON: {raw_path}: {exc}") from exc
    return parse_receipt(data)


def parse_receipt(data: Mapping[str, Any] | Any) -> Receipt:
    if not isinstance(data, Mapping):
        raise ReceiptError("Receipt must be a JSON object")
    schema = str(data.get("schema") or "agent-outcome.receipt.v1")
    if schema not in SUPPORTED_SCHEMAS:
        raise ReceiptError(f"Unsupported receipt schema: {schema}")
    # Soft validation: task recommended but not hard-required for inspect.
    return Receipt.from_dict(data)


def receipt_cannot_prove_success(receipt: Receipt) -> bool:
    """Documentation helper / test hook: receipts never prove success alone."""
    return True
