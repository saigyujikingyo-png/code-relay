# Compatibility and acceptance

Version: 0.1.1 preview. Each row requires its own evidence.

| Surface | Implementation | Acceptance |
| --- | --- | --- |
| Shared core, Python 3.11+ | Standard-library runtime | Dated test results are recorded in verification/; documentation adoption does not refresh runtime acceptance |
| Runtime lifecycle | On-demand stdio frontend with persistent submission receipts | Shared rules 2026-09-19.1 adopted; conformance partial, with unreproduced risks and pending installed/OS-event gates in [the lifecycle record](LIFECYCLE.md) |
| OpenAI-compatible Chat Completions | Exact model IDs; configurable token parameter | Synthetic HTTP integration; live endpoints unverified |
| Anthropic Messages | Independent adapter, key and version header | Synthetic HTTP integration; live endpoint unverified |
| ELM multiple models | Shared endpoint/key reference with per-model profiles | Official OpenAI-compatible example checked; endpoint, OPUS/SOL/TERRA/QWEN IDs and account entitlements unverified |
| Codex plugin | Manifest, seven MCP tools with validated output schemas, workflow skill | Installed runtime/stdio and real model status call passed; constrained status-only workflow had an extra read-only call; full coding workflow unverified |
| Windows x64 package | Runtime-bundled executable and local settings | Build and executable checks recorded separately |
| Linux/macOS settings | Source runtime; environment keys | GUI/system acceptance unverified |
| Other stdio MCP hosts | Same shared core | Connection and model acceptance unverified |
| ChatGPT Chat / local Work / cloud Work | Future thin host adapters | Not supported by this preview |
| Terra max benchmark | GPT-5.6 Terra, max is the project target | Not performed; no substitute result claimed |
| Fresh device / upgrade / removal | Preservation-oriented install path | Separate actual acceptance required |

The plugin never reads ChatGPT or Codex login state. A user choosing a particular host still needs that host's own valid access. No subscription or API quota savings have been established. Actual money charges remain unknown unless independently supplied; token counts are reported only when returned by the provider.
