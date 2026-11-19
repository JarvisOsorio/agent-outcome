# Agent Outcome

**VERIFY · ASSERT · REPRODUCE**

Independent postcondition verification for AI agent side effects — observe GitHub/Postgres, assert expected state, CI-gate PASS/FAIL.

Your agent said “All done!” A green receipt is not proof. Agent Outcome observes the target system (fakes for CI, live adapters opt-in) and runs deterministic assertions so side-effect drift fails closed with machine-readable codes. Receipts are context only — never sole evidence.

Local-first. Python 3.11+. SQLite + portable JSON. Apache-2.0.

[![CI](https://github.com/JarvisOsorio/agent-outcome/actions/workflows/ci.yml/badge.svg)](https://github.com/JarvisOsorio/agent-outcome/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/JarvisOsorio/agent-outcome?include_prereleases)](https://github.com/JarvisOsorio/agent-outcome/releases)

## Install

**v0.1 path:** clone this repo (not published to PyPI yet).

```bash
git clone https://github.com/JarvisOsorio/agent-outcome.git
cd agent-outcome
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python examples/claim_vs_verify/run.py
```

## Minimal API

```python
from agent_outcome import verify
from agent_outcome.adapters import github, postgres

result = verify(
    task="Create a GitHub issue",
    assertions=[
        github.issue_exists(owner="acme", repo="app", number=42),
        github.title_equals(
            owner="acme", repo="app", number=42, expected="Fix authentication"
        ),
        github.label_exists(owner="acme", repo="app", number=42, label="bug"),
        postgres.row_exists(table="orders", where={"id": "ord_1"}),
        postgres.column_equals(
            table="orders",
            where={"id": "ord_1"},
            column="status",
            expected="paid",
        ),
    ],
    # Optional JSON execution receipt — context only, NEVER sole evidence:
    # receipt=receipt,
    observers={"github": github_observer, "postgres": postgres_observer},
)

if not result.passed:
    print(result.failures)  # machine-readable codes + expected/actual
```

Public exports: `verify`, `AssertionSpec`, `Failure`, `Receipt`, `VerificationResult`, `VerificationCase`, `case_from_result`, `load_case`, `save_case`. Observers: `FakeGitHubObserver` / `LiveGitHubObserver`, `FakePostgresObserver` / `LivePostgresObserver`.

A receipt where `agent_claimed_success=true` cannot flip `passed=True` by itself — covered by tests.

## CLI

| Command | Purpose |
|---------|---------|
| `agent-outcome init` | Create `.agent-outcome/` + SQLite store |
| `agent-outcome verify` | Run `--assertions` or `--case` (+ optional `--receipt`, fixtures / `--live`) |
| `agent-outcome test <case>` | Re-run a saved failure case |
| `agent-outcome inspect <target>` | Inspect case, receipt, run, or file |
| `agent-outcome export <path>` | Portable JSON bundle (`agent-outcome.export.v1`) |
| `agent-outcome import <path>` | Import bundle (integrity-checked) |
| `agent-outcome doctor` | Honest readiness (`trusts_agent_success_text=false`) |

Common flags: `--github-fixture`, `--postgres-fixture`, `--live`, `--save-case`, `--save-on-fail`, `--json`.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Pass |
| 1 | Assertion failure |
| 2 | Invalid input / case / receipt |
| 3 | Infrastructure / observer / storage error |

## Honesty

| This product | Not this product |
|--------------|------------------|
| Deterministic assertions against **independent observations** | Trusting `agent_claimed_success` / “Done!” text |
| GitHub issue + Postgres row/column/count checks (v0.1) | Tracing UI, prompt eval, vector similarity |
| Failure → reusable verification case for CI re-runs | Agent framework / orchestration |
| Hermetic fakes in unit tests; optional live adapters | Cassette/replay of tool I/O |

### Sibling boundaries (do not merge)

| Tool | Job |
|------|-----|
| **agent-outcome** (this repo) | Postcondition / side-effect verification against real systems |
| **[agent-replay-lab](https://github.com/JarvisOsorio/agent-replay-lab)** | VCR for **tool I/O** (record / mock-replay / diff) |
| **mcp-pordego** | MCP protocol / gateway |
| **agentscrub** | Transcript secret scrubbing |

Observability (Langfuse, LangSmith, Phoenix, Braintrust) answers “what happened in the run?” Outcome asserts whether the **external world** matches expected postconditions.

## Example (claim vs verify)

`examples/claim_vs_verify` shows:

1. Agent receipt claims success  
2. Independent observations **PASS** against the expected world  
3. Intentional wrong title/label/row → **FAIL** with `GITHUB_TITLE_MISMATCH`, `GITHUB_LABEL_MISSING`, `PG_COLUMN_MISMATCH` — even though the receipt still says success  
4. Failure becomes a reusable case

```bash
python examples/claim_vs_verify/run.py
```

## Live adapters (optional)

Hermetic CI needs **no network**. Live checks are opt-in:

| Env | Purpose |
|-----|---------|
| `GITHUB_TOKEN` + `--live` / `LiveGitHubObserver` | Live GitHub REST |
| `AGENT_OUTCOME_DATABASE_URL` (or `DATABASE_URL`) + `--live` | Live Postgres (`pip install 'agent-outcome[postgres]'`) |
| `AGENT_OUTCOME_LIVE_GITHUB=1` | Enable optional pytest live GitHub tests |
| `AGENT_OUTCOME_LIVE_POSTGRES=1` | Enable optional pytest live Postgres tests |

`agent-outcome doctor` reports readiness honestly without printing secrets.

## Storage

Default: `.agent-outcome/store.sqlite` plus JSON case sidecars. Portable export schema `agent-outcome.export.v1` with integrity hash. No telemetry. Tokens in case metadata are redacted on save.

## What v0.1 does **not** include

MCP adapter (deferred), Slack/filesystem adapters, dashboards, semantic/LLM judges, Agent Assurance policy engines, dual-building Replay Lab cassettes here. Not on PyPI yet.

## License

Apache-2.0 © Jarvis Nelson Osorio Ramos / JarvisOsorio
