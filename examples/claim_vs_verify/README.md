# Example: agent claims success → independent verify PASS / FAIL

This example shows the product rule:

> An agent saying “done” is **not** proof. Agent Outcome observes GitHub + Postgres state independently.

## Run

From the repo root (after `pip install -e ".[dev]"`):

```bash
python examples/claim_vs_verify/run.py
```

Or via CLI with fixtures:

```bash
agent-outcome init
agent-outcome verify \
  --assertions examples/claim_vs_verify/assertions_pass.json \
  --receipt examples/claim_vs_verify/receipt_claim_success.json \
  --github-fixture examples/claim_vs_verify/github_world.json \
  --postgres-fixture examples/claim_vs_verify/postgres_world.json \
  --json

agent-outcome verify \
  --assertions examples/claim_vs_verify/assertions_fail.json \
  --receipt examples/claim_vs_verify/receipt_claim_success.json \
  --github-fixture examples/claim_vs_verify/github_world.json \
  --postgres-fixture examples/claim_vs_verify/postgres_world.json \
  --save-on-fail --case-name claim-lie --json
```

Expected: first command exit `0`, second exit `1` with `GITHUB_TITLE_MISMATCH` (agent claimed success anyway).
