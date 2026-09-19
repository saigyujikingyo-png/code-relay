# Code Relay contributor entrypoint

Read DEVELOPMENT_PRINCIPLES.md (2026-09-19.1), README.md and docs/ARCHITECTURE.md before work. For lifecycle or ownership work, also read RUNTIME_LIFECYCLE.md, governance/OWNERSHIP.md and docs/LIFECYCLE.md.

Code Relay is a Chembridge coding-workflow plugin. Codex is the first target host. The core must not read ChatGPT/Codex login tokens, cookies, account files or quota APIs. User-supplied model credentials are independent. Keep architecture, sensitive changes, complex work and final review with the host model; workers produce bounded candidate files only.

Every public MCP tool requires a meaningful outputSchema and server-side result validation. Maintain the versioned contracts and per-tool coverage in docs/OUTPUT_CONTRACTS.md, including lifecycle, error and artifact branches. Structured output checks do not establish model or live-provider acceptance.

One accountable Product Max owner maintains this product; Governance High owns shared contracts and incident review, and Ultra is consultation-only. Preserve the verified checkpoint, private takeover evidence and the open lifecycle backlog. Rule adoption does not establish runtime conformance. Never automatically resend a possibly billed request; keep worker output candidate-only; persistent claims and EOF cancellation do not make this a durable execution service.

Use Python 3.11+ standard library for the runtime and tests. For runtime changes, run `python -m unittest discover -s tests -v`, `python scripts/smoke_mcp.py` and `python scripts/check_release.py`. For documentation-only changes, use the release metadata check, relevant link/parity checks and git diff --check; do not rerun the complete runtime matrix without a material reason. Build tools belong in an isolated environment. Portable, bundled Windows, installed Codex, live providers, ELM entitlements and Terra max acceptance are separate gates.

Source and public documentation are English and MIT licensed. Never commit credentials, private source snapshots, runtime job state or campus data. No provider calls without configured user authorization. No automatic retries after a request might have been billed. Preserve unrelated files and host configuration.
