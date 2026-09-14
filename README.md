# Code Relay

Code Relay lets a Codex host model own architecture, complex implementation and final review while dispatching bounded, repetitive coding tasks to user-configured API models.

**0.1.0 preview.** The runtime uses Python's standard library and MCP over stdio. OpenAI-compatible endpoints and Anthropic Messages are separate protocol adapters. Multiple model profiles can share an endpoint and credential, including an ELM connection supplied by an authorised University of Edinburgh user. Model names are exact user-provided identifiers; availability is never inferred from a brand.

The plugin does not read or depend on ChatGPT account sessions. The selected host has its own authentication requirements. Workers receive only explicitly selected project files and return candidate replacements. They cannot execute commands, modify the workspace, approve their own output, publish changes or call other tools.

Download the runtime-bundled Windows x64 ZIP from [GitHub Releases](https://github.com/saigyujikingyo-png/code-relay/releases). Extract it, double-click **code-relay.exe**, add your model profiles and project folder, and select **Install / reconnect in Codex**. No source checkout, Git or separate Python installation is required for the Windows package. Start a new Codex task after installation.

Ask Codex: “Use Code Relay for independent test and boilerplate work, then review, integrate and test the results.” The host reasons about task boundaries; deterministic routing enforces capabilities, priorities, context limits and call caps. A profile can be selected explicitly when needed. Complex, sensitive and dependent work remains with the host.

The local workflow includes frozen source snapshots, bounded parallel calls, persistent duplicate-call protection, cancellation, source-drift checks and candidate diffs. Windows credentials use user-scoped DPAPI. API workers cannot apply changes. Interrupted plans are never automatically resent, and admission can recover after their owning process exits.

ELM users may configure multiple OPUS, SOL, TERRA, QWEN or other profiles using their actual endpoint and API model identifiers. Their current availability and permissions have not been verified. No paid API or live ELM call is included in the synthetic acceptance results, and no token-cost saving or Terra max benchmark is claimed.

All seven tools publish versioned output schemas and validate results before delivery. Null usage or cost means unavailable; candidate artifact metadata does not establish correctness or host delivery. See [output contracts](docs/OUTPUT_CONTRACTS.md), [installation and recovery](docs/INSTALL.md), [architecture](docs/ARCHITECTURE.md), [compatibility](docs/COMPATIBILITY.md), [privacy](docs/PRIVACY.md) and the [acceptance record](https://github.com/saigyujikingyo-png/code-relay/blob/v0.1.0/verification/2026-09-14-preview.md).

For development, use Python 3.11+ and run:

```sh
python -m unittest discover -s tests -v
python scripts/smoke_mcp.py
python -m code_relay self-test
python scripts/check_release.py
```

The core and portable checks need no third-party packages. Windows packaging uses the isolated versions in build-requirements.txt. This is an independent, MIT-licensed Chembridge plugin; it does not imply OpenAI, Anthropic or university endorsement.
