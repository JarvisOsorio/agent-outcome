# Security

Agent Outcome is local-first verification software.

- No telemetry / no automatic upload of cases or receipts
- Treat receipts and imported bundles as **untrusted input** (never executed)
- Do not commit tokens, `DATABASE_URL` values, or live credentials
- Case metadata redacts common secret key names on save; this is best-effort, not a scanner — pair with agentscrub for store remediation
- Live GitHub/Postgres adapters are opt-in; CI hermetic path uses fakes only

Report vulnerabilities privately to the maintainer (JarvisOsorio).
