# Changelog

## 0.1.0 — 2026-11-19

Initial private release.

- Core `verify()` with deterministic PASS/FAIL and machine-readable failure codes
- Optional JSON execution receipt (context only — never sole evidence)
- GitHub adapter: issue exists / title / labels / body / repo (+ fake & live observers)
- PostgreSQL adapter: row exists / column equals / count (+ fake & live observers)
- Failure → reusable verification case; local SQLite/JSON storage; export/import
- CLI: `init | verify | inspect | test | export | import | doctor` (human + `--json`)
- Exit codes 0/1/2/3
- Hermetic pytest suite + GitHub Actions CI
- Example `examples/claim_vs_verify` (agent claim → independent PASS and FAIL)
