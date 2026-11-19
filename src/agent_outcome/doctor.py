"""Environment / store diagnostics."""

from __future__ import annotations

import os
import sys
from typing import Any

from agent_outcome import __version__
from agent_outcome.exit_codes import EXIT_CODE_MEANINGS
from agent_outcome.storage import Store


def run_doctor(store: Store | None = None) -> dict[str, Any]:
    st = store or Store()
    github_token = bool(os.environ.get("GITHUB_TOKEN"))
    db_url = bool(
        os.environ.get("AGENT_OUTCOME_DATABASE_URL") or os.environ.get("DATABASE_URL")
    )
    live_github = os.environ.get("AGENT_OUTCOME_LIVE_GITHUB") == "1"
    live_postgres = os.environ.get("AGENT_OUTCOME_LIVE_POSTGRES") == "1"

    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "name": "python",
            "ok": sys.version_info >= (3, 11),
            "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }
    )
    checks.append(
        {
            "name": "store",
            "ok": st.exists,
            "detail": str(st.root) if st.exists else "not initialized (run agent-outcome init)",
            "schema_version": st.schema_version() if st.exists else None,
        }
    )
    checks.append(
        {
            "name": "github_observer",
            "ok": True,
            "live_ready": github_token,
            "live_opt_in": live_github,
            "detail": (
                "GITHUB_TOKEN set; live tests need AGENT_OUTCOME_LIVE_GITHUB=1"
                if github_token
                else "no GITHUB_TOKEN — use FakeGitHubObserver or inject observers"
            ),
        }
    )
    checks.append(
        {
            "name": "postgres_observer",
            "ok": True,
            "live_ready": db_url,
            "live_opt_in": live_postgres,
            "detail": (
                "DATABASE_URL/AGENT_OUTCOME_DATABASE_URL set; live tests need AGENT_OUTCOME_LIVE_POSTGRES=1"
                if db_url
                else "no database URL — use FakePostgresObserver or inject observers"
            ),
        }
    )
    try:
        import httpx  # noqa: F401

        httpx_ok = True
        httpx_detail = "installed"
    except ImportError:
        httpx_ok = False
        httpx_detail = "missing (required for live GitHub)"
    checks.append({"name": "httpx", "ok": httpx_ok, "detail": httpx_detail})

    try:
        import psycopg  # noqa: F401

        pg_ok = True
        pg_detail = "installed"
    except ImportError:
        pg_ok = False
        pg_detail = "optional — install agent-outcome[postgres] for live Postgres"
    checks.append({"name": "psycopg", "ok": pg_ok or True, "detail": pg_detail, "installed": pg_ok})

    return {
        "product": "agent-outcome",
        "version": __version__,
        "tagline": "VERIFY · ASSERT · REPRODUCE",
        "honesty": {
            "trusts_agent_success_text": False,
            "receipt_is_sole_evidence": False,
            "is_tracing_dashboard": False,
            "is_agent_framework": False,
            "is_agent_replay_lab": False,
            "hermetic_tests_via_fakes": True,
        },
        "exit_codes": {str(k): v for k, v in EXIT_CODE_MEANINGS.items()},
        "checks": checks,
        "ok": all(c.get("ok", True) for c in checks if c["name"] in {"python", "httpx"}),
    }
