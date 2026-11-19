"""Local SQLite + JSON storage for cases, receipts, and runs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from agent_outcome.models import (
    Receipt,
    VerificationCase,
    VerificationResult,
    strip_secrets,
    utc_now_iso,
)

SCHEMA_VERSION = "0.1.0"
DEFAULT_DIRNAME = ".agent-outcome"


class StorageError(RuntimeError):
    """Storage / persistence failure."""


def default_root(cwd: str | Path | None = None) -> Path:
    base = Path(cwd) if cwd else Path.cwd()
    return base / DEFAULT_DIRNAME


class Store:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else default_root()
        self.db_path = self.root / "store.sqlite"
        self.export_dir = self.root / "exports"

    @property
    def exists(self) -> bool:
        return self.db_path.is_file()

    def init(self) -> Path:
        if self.exists:
            raise StorageError(f"Store already initialized at {self.root}")
        self.root.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE meta (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );
                CREATE TABLE receipts (
                  id TEXT PRIMARY KEY,
                  json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE cases (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE runs (
                  id TEXT PRIMARY KEY,
                  case_id TEXT,
                  receipt_id TEXT,
                  passed INTEGER NOT NULL,
                  json TEXT NOT NULL,
                  observed_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                ("schema_version", SCHEMA_VERSION),
            )
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                ("created_at", utc_now_iso()),
            )
            conn.commit()
        (self.root / "README.txt").write_text(
            "Agent Outcome local store. Cases, receipts, and verification runs.\n"
            "No telemetry. Secrets must not be stored here.\n",
            encoding="utf-8",
        )
        return self.root

    def _connect(self) -> sqlite3.Connection:
        if not self.root.exists():
            raise StorageError(
                f"Store not initialized at {self.root}. Run `agent-outcome init`."
            )
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def schema_version(self) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", ("schema_version",)
            ).fetchone()
            return str(row["value"]) if row else "unknown"

    def save_receipt(self, receipt: Receipt) -> str:
        payload = json.dumps(receipt.to_dict(), sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO receipts(id, json, created_at) VALUES (?, ?, ?)",
                (receipt.id, payload, receipt.created_at),
            )
            conn.commit()
        return receipt.id

    def get_receipt(self, receipt_id: str) -> Receipt | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT json FROM receipts WHERE id = ?", (receipt_id,)
            ).fetchone()
        if not row:
            return None
        return Receipt.from_dict(json.loads(row["json"]))

    def save_case(self, case: VerificationCase) -> str:
        data = case.to_dict()
        data["metadata"] = strip_secrets(data.get("metadata") or {})
        payload = json.dumps(data, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cases(id, name, json, created_at) VALUES (?, ?, ?, ?)",
                (case.id, case.name or case.id, payload, case.created_at),
            )
            conn.commit()
        # Also write a portable JSON sidecar for easy inspect/export.
        cases_dir = self.root / "cases"
        cases_dir.mkdir(exist_ok=True)
        (cases_dir / f"{case.id}.json").write_text(payload + "\n", encoding="utf-8")
        return case.id

    def get_case(self, case_id: str) -> VerificationCase | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT json FROM cases WHERE id = ?", (case_id,)
            ).fetchone()
        if not row:
            # Fall back to name match
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT json FROM cases WHERE name = ?", (case_id,)
                ).fetchone()
        if not row:
            return None
        return VerificationCase.from_dict(json.loads(row["json"]))

    def list_cases(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, created_at FROM cases ORDER BY created_at"
            ).fetchall()
        return [
            {"id": r["id"], "name": r["name"], "created_at": r["created_at"]}
            for r in rows
        ]

    def save_run(self, result: VerificationResult) -> str:
        payload = json.dumps(result.to_dict(), sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs(id, case_id, receipt_id, passed, json, observed_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    result.run_id,
                    result.case_id,
                    result.receipt_id,
                    1 if result.passed else 0,
                    payload,
                    result.observed_at,
                ),
            )
            conn.commit()
        return result.run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT json FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if not row:
            return None
        return json.loads(row["json"])

    def export_bundle(self, path: str | Path) -> Path:
        out = Path(path)
        cases = []
        receipts = []
        runs = []
        with self._connect() as conn:
            for row in conn.execute("SELECT json FROM cases").fetchall():
                cases.append(json.loads(row["json"]))
            for row in conn.execute("SELECT json FROM receipts").fetchall():
                receipts.append(json.loads(row["json"]))
            for row in conn.execute("SELECT json FROM runs").fetchall():
                runs.append(json.loads(row["json"]))
        bundle = {
            "schema": "agent-outcome.export.v1",
            "schema_version": SCHEMA_VERSION,
            "exported_at": utc_now_iso(),
            "cases": cases,
            "receipts": receipts,
            "runs": runs,
        }
        body = json.dumps(bundle, sort_keys=True, indent=2)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        bundle["integrity"] = {"alg": "sha256", "hash": digest}
        # Re-serialize with integrity included (hash covers pre-integrity body).
        final = json.dumps(bundle, sort_keys=True, indent=2) + "\n"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(final, encoding="utf-8")
        return out

    def import_bundle(self, path: str | Path, *, skip_integrity: bool = False) -> dict[str, int]:
        raw = Path(path).read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StorageError(f"Invalid export JSON: {exc}") from exc
        if data.get("schema") != "agent-outcome.export.v1":
            raise StorageError(f"Unsupported export schema: {data.get('schema')}")
        if not skip_integrity:
            integrity = data.get("integrity") or {}
            check = {k: v for k, v in data.items() if k != "integrity"}
            body = json.dumps(check, sort_keys=True, indent=2)
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            expected = integrity.get("hash")
            if expected and expected != digest:
                raise StorageError("Export integrity hash mismatch")
        counts = {"cases": 0, "receipts": 0, "runs": 0}
        for item in data.get("cases") or []:
            self.save_case(VerificationCase.from_dict(item))
            counts["cases"] += 1
        for item in data.get("receipts") or []:
            self.save_receipt(Receipt.from_dict(item))
            counts["receipts"] += 1
        for item in data.get("runs") or []:
            # Persist run JSON as-is via minimal VerificationResult-shaped save
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO runs(id, case_id, receipt_id, passed, json, observed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        item.get("run_id") or item.get("id"),
                        item.get("case_id"),
                        item.get("receipt_id"),
                        1 if item.get("passed") else 0,
                        json.dumps(item, sort_keys=True),
                        item.get("observed_at") or utc_now_iso(),
                    ),
                )
                conn.commit()
            counts["runs"] += 1
        return counts


def load_case_file(path: str | Path) -> VerificationCase:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") not in {None, "agent-outcome.case.v1"} and not data.get(
        "assertions"
    ):
        raise StorageError(f"Not a verification case: {path}")
    return VerificationCase.from_dict(data)


def load_assertions_file(path: str | Path) -> tuple[str, list[Mapping[str, Any]]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return "", data
    if isinstance(data, Mapping):
        task = str(data.get("task") or "")
        assertions = data.get("assertions")
        if not isinstance(assertions, list):
            raise StorageError("assertions file must contain an assertions list")
        return task, assertions
    raise StorageError("assertions file must be a JSON object or list")
