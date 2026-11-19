"""agent-outcome CLI: init | verify | inspect | test | export | import | doctor."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent_outcome import __version__
from agent_outcome.adapters.github import FakeGitHubObserver, LiveGitHubObserver
from agent_outcome.adapters.postgres import FakePostgresObserver, LivePostgresObserver
from agent_outcome.cases import case_from_result, load_case, save_case
from agent_outcome.doctor import run_doctor
from agent_outcome.exit_codes import (
    ASSERTION_FAILURE,
    INFRA_ERROR,
    INVALID_INPUT,
    PASS,
)
from agent_outcome.models import AssertionSpec, Receipt, VerificationCase
from agent_outcome.receipt import ReceiptError, load_receipt
from agent_outcome.storage import StorageError, Store, load_assertions_file, load_case_file
from agent_outcome.verify import verify


def _json_out(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _human_result(result: Mapping[str, Any]) -> None:
    status = "PASS" if result.get("passed") else "FAIL"
    print(f"[{status}] {result.get('task') or '(no task)'}")
    print(f"run_id: {result.get('run_id')}")
    if result.get("case_id"):
        print(f"case_id: {result['case_id']}")
    if result.get("receipt_id"):
        print(f"receipt_id: {result['receipt_id']} (context only)")
    failures = result.get("failures") or []
    if failures:
        print("failures:")
        for f in failures:
            print(f"  - {f.get('code')}: {f.get('message')}")
            print(f"    expected={f.get('expected')!r} actual={f.get('actual')!r}")
    for note in result.get("notes") or []:
        print(f"note: {note}")


def _build_observers(args: argparse.Namespace) -> dict[str, Any]:
    """Resolve observers: fixture JSON overrides, else live if configured, else none."""
    observers: dict[str, Any] = {}

    if getattr(args, "github_fixture", None):
        data = json.loads(Path(args.github_fixture).read_text(encoding="utf-8"))
        fake = FakeGitHubObserver()
        from agent_outcome.adapters.base import IssueSnapshot

        raw_issues = data.get("issues") if isinstance(data, dict) else None
        items = raw_issues if isinstance(raw_issues, list) else (
            data if isinstance(data, list) else []
        )
        for item in items:
            if isinstance(item, dict):
                fake.put(
                    IssueSnapshot(
                        owner=str(item["owner"]),
                        repo=str(item["repo"]),
                        number=int(item["number"]),
                        title=str(item.get("title") or ""),
                        body=str(item.get("body") or ""),
                        labels=tuple(item.get("labels") or []),
                        state=str(item.get("state") or "open"),
                    )
                )
        observers["github"] = fake
    elif os.environ.get("GITHUB_TOKEN") and getattr(args, "live", False):
        observers["github"] = LiveGitHubObserver()

    if getattr(args, "postgres_fixture", None):
        data = json.loads(Path(args.postgres_fixture).read_text(encoding="utf-8"))
        tables = data.get("tables") if isinstance(data, dict) else {}
        observers["postgres"] = FakePostgresObserver(tables)
    elif (
        os.environ.get("AGENT_OUTCOME_DATABASE_URL") or os.environ.get("DATABASE_URL")
    ) and getattr(args, "live", False):
        observers["postgres"] = LivePostgresObserver()

    return observers


def cmd_init(args: argparse.Namespace) -> int:
    store = Store(args.root) if args.root else Store()
    try:
        root = store.init()
    except StorageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return INFRA_ERROR
    payload = {"ok": True, "root": str(root), "schema_version": store.schema_version()}
    if args.json:
        _json_out(payload)
    else:
        print(f"Initialized Agent Outcome store at {root}")
    return PASS


def _resolve_case_and_assertions(
    args: argparse.Namespace, store: Store
) -> tuple[str, list[AssertionSpec], VerificationCase | None, Receipt | None]:
    receipt: Receipt | None = None
    if args.receipt:
        receipt = load_receipt(args.receipt)

    case: VerificationCase | None = None
    task = getattr(args, "task", None) or ""
    assertions: list[AssertionSpec] = []

    if args.case:
        case = load_case(args.case, store=store if store.exists else None)
        task = task or case.task
        assertions = list(case.assertions)
    elif args.assertions:
        file_task, raw = load_assertions_file(args.assertions)
        task = task or file_task
        assertions = [AssertionSpec.from_dict(a) for a in raw]
    else:
        raise ReceiptError("Provide --case or --assertions")

    if not task:
        task = case.name if case else "verification"
    return task, assertions, case, receipt


def cmd_verify(args: argparse.Namespace) -> int:
    store = Store(args.root) if args.root else Store()
    try:
        task, assertions, case, receipt = _resolve_case_and_assertions(args, store)
    except (ReceiptError, StorageError, FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return INVALID_INPUT

    observers = _build_observers(args)
    if not observers:
        # Allow pure case re-verify only when fixtures/live provided; otherwise infra.
        if any(a.adapter in {"github", "postgres"} for a in assertions):
            print(
                "error: no observers configured. Pass --github-fixture / --postgres-fixture "
                "or --live with credentials.",
                file=sys.stderr,
            )
            return INFRA_ERROR

    try:
        result = verify(
            task=task,
            assertions=assertions,
            receipt=receipt,
            observers=observers,
        )
    except Exception as exc:  # pragma: no cover - defensive
        print(f"error: {exc}", file=sys.stderr)
        return INFRA_ERROR

    if args.save_case or (not result.passed and args.save_on_fail):
        if not store.exists:
            try:
                store.init()
            except StorageError:
                pass
        case_obj = case_from_result(result, name=args.case_name)
        save_case(case_obj, store=store)
        result.case_id = case_obj.id

    if store.exists:
        if receipt is not None:
            store.save_receipt(receipt)
        store.save_run(result)

    payload = result.to_dict()
    if args.json:
        _json_out(payload)
    else:
        _human_result(payload)
    return PASS if result.passed else ASSERTION_FAILURE


def cmd_test(args: argparse.Namespace) -> int:
    """Re-run a saved verification case (same as verify --case, CI-friendly)."""
    args.case = args.case_id
    args.assertions = None
    args.receipt = args.receipt
    args.save_case = False
    args.save_on_fail = False
    args.case_name = None
    args.task = getattr(args, "task", None)
    return cmd_verify(args)


def cmd_inspect(args: argparse.Namespace) -> int:
    store = Store(args.root) if args.root else Store()
    target = args.target
    path = Path(target)

    data: Any = None
    kind = "unknown"
    try:
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            schema = raw.get("schema", "")
            if "case" in schema or "assertions" in raw:
                data = VerificationCase.from_dict(raw).to_dict()
                kind = "case"
            elif "receipt" in schema or "agent_claimed_success" in raw:
                data = Receipt.from_dict(raw).to_dict()
                kind = "receipt"
            else:
                data = raw
                kind = "file"
        elif store.exists:
            case = store.get_case(target)
            if case:
                data = case.to_dict()
                kind = "case"
            else:
                receipt = store.get_receipt(target)
                if receipt:
                    data = receipt.to_dict()
                    kind = "receipt"
                else:
                    run = store.get_run(target)
                    if run:
                        data = run
                        kind = "run"
        if data is None:
            print(f"error: nothing found for {target!r}", file=sys.stderr)
            return INVALID_INPUT
    except (json.JSONDecodeError, StorageError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return INVALID_INPUT

    payload = {"kind": kind, "data": data}
    if args.json:
        _json_out(payload)
    else:
        print(f"kind: {kind}")
        print(json.dumps(data, indent=2, sort_keys=True))
    return PASS


def cmd_export(args: argparse.Namespace) -> int:
    store = Store(args.root) if args.root else Store()
    if not store.exists:
        print("error: store not initialized", file=sys.stderr)
        return INFRA_ERROR
    try:
        out = store.export_bundle(args.path)
    except StorageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return INFRA_ERROR
    if args.json:
        _json_out({"ok": True, "path": str(out)})
    else:
        print(f"Exported to {out}")
    return PASS


def cmd_import(args: argparse.Namespace) -> int:
    store = Store(args.root) if args.root else Store()
    if not store.exists:
        try:
            store.init()
        except StorageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return INFRA_ERROR
    try:
        counts = store.import_bundle(args.path, skip_integrity=args.skip_integrity)
    except StorageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return INFRA_ERROR
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return INVALID_INPUT
    if args.json:
        _json_out({"ok": True, "imported": counts})
    else:
        print(
            f"Imported cases={counts['cases']} receipts={counts['receipts']} runs={counts['runs']}"
        )
    return PASS


def cmd_doctor(args: argparse.Namespace) -> int:
    store = Store(args.root) if args.root else Store()
    report = run_doctor(store)
    if args.json:
        _json_out(report)
    else:
        print(f"agent-outcome {report['version']} — {report['tagline']}")
        honesty = report["honesty"]
        print(
            "honesty: trusts_agent_success_text="
            f"{honesty['trusts_agent_success_text']} "
            f"receipt_is_sole_evidence={honesty['receipt_is_sole_evidence']}"
        )
        for check in report["checks"]:
            mark = "ok" if check.get("ok", True) else "FAIL"
            print(f"[{mark}] {check['name']}: {check.get('detail')}")
        print("exit codes:")
        for code, meaning in report["exit_codes"].items():
            print(f"  {code}: {meaning}")
    return PASS if report.get("ok") else INFRA_ERROR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-outcome",
        description=(
            "Independent postcondition verification for AI agent side effects. "
            "Agents do not declare success — you verify external state."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--root",
        help="Store root directory (default: ./.agent-outcome)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize local store")
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(func=cmd_init)

    def add_observer_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--github-fixture", help="JSON fixture for FakeGitHubObserver")
        p.add_argument("--postgres-fixture", help="JSON fixture for FakePostgresObserver")
        p.add_argument(
            "--live",
            action="store_true",
            help="Use live GitHub/Postgres when credentials are present",
        )

    p_verify = sub.add_parser("verify", help="Run verification assertions")
    p_verify.add_argument("--case", help="Case id or JSON path")
    p_verify.add_argument("--assertions", help="Assertions JSON path")
    p_verify.add_argument("--receipt", help="Optional execution receipt JSON (context only)")
    p_verify.add_argument("--task", help="Task label override")
    p_verify.add_argument("--save-case", action="store_true", help="Save a reusable case")
    p_verify.add_argument(
        "--save-on-fail",
        action="store_true",
        help="Save a reusable case when verification fails",
    )
    p_verify.add_argument("--case-name", help="Name for saved case")
    p_verify.add_argument("--json", action="store_true")
    add_observer_flags(p_verify)
    p_verify.set_defaults(func=cmd_verify)

    p_test = sub.add_parser("test", help="Re-run a saved verification case")
    p_test.add_argument("case_id", help="Case id, name, or JSON path")
    p_test.add_argument("--receipt", default=None)
    p_test.add_argument("--task", default=None)
    p_test.add_argument("--json", action="store_true")
    add_observer_flags(p_test)
    p_test.set_defaults(func=cmd_test)

    p_inspect = sub.add_parser("inspect", help="Inspect case, receipt, or run")
    p_inspect.add_argument("target")
    p_inspect.add_argument("--json", action="store_true")
    p_inspect.set_defaults(func=cmd_inspect)

    p_export = sub.add_parser("export", help="Export store bundle to JSON")
    p_export.add_argument("path")
    p_export.add_argument("--json", action="store_true")
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser("import", help="Import store bundle from JSON")
    p_import.add_argument("path")
    p_import.add_argument("--skip-integrity", action="store_true")
    p_import.add_argument("--json", action="store_true")
    p_import.set_defaults(func=cmd_import)

    p_doctor = sub.add_parser("doctor", help="Diagnose environment and store")
    p_doctor.add_argument("--json", action="store_true")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except BrokenPipeError:  # pragma: no cover
        return PASS


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
