# Code Relay contributor entrypoint

Read DEVELOPMENT_PRINCIPLES.md (2026-09-13.2), README.md and docs/ARCHITECTURE.md before work.

Code Relay is a Chembridge coding-workflow plugin. Codex is the first target host. The core must not read ChatGPT/Codex login tokens, cookies, account files or quota APIs. User-supplied model credentials are independent. Keep architecture, sensitive changes, complex work and final review with the host model; workers produce bounded candidate files only.

Use Python 3.11+ standard library for the runtime and tests. Run `python -m unittest discover -s tests -v`, `python scripts/smoke_mcp.py` and `python scripts/check_release.py`. Build tools belong in an isolated environment. Portable, bundled Windows, installed Codex, live providers, ELM entitlements and Terra max acceptance are separate gates.

Source and public documentation are English and MIT licensed. Never commit credentials, private source snapshots, runtime job state or campus data. No provider calls without configured user authorization. No automatic retries after a request might have been billed. Preserve unrelated files and host configuration.
