# Tool output contracts

Public contract version: **1.0** (unchanged). Shared rule baseline: **2026-09-19.1**, section 12. This documentation adoption does not refresh historical contract-test evidence or establish runtime lifecycle conformance.

Each of the seven MCP tools publishes a meaningful `outputSchema` through
`tools/list`. The schemas and the server validator share the definitions in
`code_relay/contracts.py`. They use bounded objects, arrays and strings,
required fields, integer ranges, enums, `anyOf`, and local `$defs`/`$ref`.
There is no generic operation dispatcher or economy mode in this preview.

Every tool result includes `contract_version: "1.0"` in `structuredContent`.
The text content is the same serialized JSON, for hosts that need a text
fallback. Existing result fields retain their meanings. A future incompatible
change requires a new contract version and documented migration. Protocol
negotiation is separate from contract versioning; older MCP hosts can use the
text fallback, but actual acceptance in those hosts remains unverified.

The standard-library validator intentionally implements only the JSON Schema
vocabulary used by these fixed local contracts. It does not load remote schemas.
The server checks the entire result, including errors, before delivery. Unknown
fields, incorrect types, missing required fields, invalid states, oversized
payloads and invalid JSON values fail closed as `invalid_output` with `isError`.
No operation is repeated to repair a malformed result. Valid plan/task IDs
already known from arguments or the returned result are preserved in the error.

## Meanings and units

- `input_bytes`, `size_bytes` and byte limits are UTF-8/storage bytes, not tokens.
  `elapsed_ms` is elapsed milliseconds. Stored lifecycle timestamps use UTC
  ISO 8601. Observations are local runtime observations, not provider receipts.
- `usage` is null when unavailable, or contains four required counters, each
  an integer or null: `input_tokens`, `output_tokens`, `cached_input_tokens`,
  `reasoning_tokens`. Null means unavailable, not zero. Missing optional row
  usage means the runtime has not recorded usage for that lifecycle branch.
  Anthropic cache-read counts remain separate from its input-token count.
- `actual_cost` is always null in this preview: monetary cost was not calculated.
  `submission_attempts` and `reserved_requests` are local counters and are not
  proof of successful service execution, billing or savings.
- Plan tasks have `owner: host` with null profile/model/endpoint when retained.
  Zero `output_token_limit` means no API output budget applies to that host row.
  API rows name an exact configured profile, model and endpoint. `input_bytes`
  describes the prepared prompt, including for a retained task.
- `planned` means no run receipt exists. `interrupted_or_starting` means a
  claim exists without a complete run receipt. Optional
  `cancellation_requested: true` applies even before execution; a cancelled
  plan is never dispatched. Cancellation of an in-flight request does not
  establish a refund or that the provider stopped processing it.
- `queued`/`running` describe active or possibly interrupted work. `observation`
  records when another process might own it. `completed`, `needs_attention`,
  `cancelled`, and `interrupted` are terminal batch states. A recovered
  interrupted batch may retain stale queued/running task rows as evidence.
- `needs_host_review` is candidate availability, not correctness. Candidate
  summary, files and diff are untrusted. `source_still_matches` checks the
  frozen source at read time. `workspace_modified` is false because this core
  never applies candidates. Host review, application and tests are separate.
- `artifact` describes the persisted candidate JSON, using media type
  `application/json`, actual file bytes, SHA-256 and a local path.
  `artifact_path` is retained for compatibility. This is metadata for a local
  artifact; it does not claim upload or host file delivery. Code text is the
  tool's text result; there are no image/binary results or paginated operations.
- `relay_setup` status `opened` means the local settings process was launched;
  it does not prove credentials were saved or a live API call succeeded.

Errors have a stable `error.code`, bounded human-readable `error.message`,
and `recovery`: either `check_settings_or_arguments` or
`inspect_status_before_retry`. All error results set `isError: true`.
Input mistakes use `invalid_arguments`/`invalid_argument`; configuration,
authorization, source drift, limits, provider and candidate errors keep their
specific codes. Unexpected execution failures use `internal_error`.
Malformed server output uses `invalid_output` and never includes the rejected
payload. Do not blindly resend work in response to any of these errors.

## Per-tool coverage

| Tool | Declared and validated success branches | Failure and lifecycle checks | Actual host acceptance |
| --- | --- | --- | --- |
| `relay_status` | Empty and configured profiles, workspace grants, bounded limits | Invalid arguments, unavailable credentials, malformed output | Recorded separately |
| `relay_plan` | API/host ownership, destinations, scope and dispatch count | Validation, retained work, frozen-plan IDs after malformed output | Recorded separately |
| `relay_run` | Full queued/running/terminal jobs; planned/interrupted stubs on replay | No resend, cancelled-before-run, output failure after side effects | Recorded separately |
| `relay_job` | Stub and full lifecycle records, nullable usage/timestamps | Cancellation marker, interrupted records, unknown plan | Recorded separately |
| `relay_result` | Candidate text/diff and artifact size/hash | Source drift, unavailable/cancelled candidate, malformed output | Recorded separately |
| `relay_cancel` | Cancellation acknowledgement or unchanged terminal job | Pre-run cancellation, repeated cancel, queued/in-flight limits | Recorded separately |
| `relay_setup` | Local settings process launch | Launch exception and malformed output, no key accepted in arguments | Recorded separately |

Focused tests live in `tests/test_contracts.py`; risk/failure integration tests
also exercise the core and providers. `scripts/smoke_mcp.py` discovers all seven
schemas from a real subprocess and validates actual status/error responses and
the JSON fallback. It runs for source and the bundled executable. This is
protocol acceptance, not a Codex model workflow or a live API/model benchmark.
Schema catalog bytes are recorded in the release receipt; they do not establish
quota savings. See [compatibility](COMPATIBILITY.md) and the dated
[release evidence](https://github.com/saigyujikingyo-png/code-relay/blob/v0.1.1/verification/2026-09-14-preview-0.1.1.md) for actual results.
