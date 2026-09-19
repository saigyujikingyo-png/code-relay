# Code Relay lifecycle record

Record date: **2026-09-19**. Owner: the single Code Relay **Product Max** owner.
Shared rules: **2026-09-19.1**; lifecycle contract: **1.0**.
[Canonical hub source](https://github.com/saigyujikingyo-png/chembridge/commit/922d95041b3b857f6ba11fbfb2817b18712ef605):
922d95041b3b857f6ba11fbfb2817b18712ef605.
Product source observed: codex/initial-preview at
60e3dcbe35b762be44f2812b64f7035963a50ffb; runtime implementation
30ed044c3371732c99772b67a8ec0ed68234f9af; package **0.1.1 preview**.

**Rule adoption is documented; runtime lifecycle conformance is PARTIAL.**
This record changes no runtime behavior, installation or acceptance result.

## Components and ownership

| Component | Class / purpose | Startup and shutdown owner | Scope / cardinality |
| --- | --- | --- | --- |
| MCP frontend: server.py | on_demand_local_companion; one host stdio connection | Host launches it; normal EOF requests cancellation. Exceptional cleanup remains open. | Multiple host frontends may share state; no competing batch owners are permitted. |
| Batch: core.py | In-process worker with persistent plans/claims/receipts | Relay owns the worker; execution depends on its process. | One active-run lease per state directory; PID liveness lacks process-start/boot identity. |
| Transport: providers.py | Request-scoped helper; 16 transport slots per process | Attempt owns deadline, cancellation and connection cleanup. | One request per task, configured concurrency/call caps; no provider retry/failover. |
| Settings: gui.py / open_setup | Explicitly launched local UI | User/tool starts the window; UI controls its lifetime. | Spawn is reported without child readiness/failure reconciliation. |
| Frozen executable | PyInstaller one-file shim and child | Host launches executable; packaging creates child. | A packaging pair is not two independent backends; teardown needs acceptance. |

Account scope is the OS user and configured API credential references, independent
of host login/cookie/quota state. No native scientific session, remote tunnel,
hosted account binding, boot service or startup task is owned by this adapter.

Launch sources are .mcp.json and installer.py. The installer writes a versioned
runtime binding, preserves metadata backups and uses the official host plugin
command. Windows keys use per-user DPAPI; source hosts can use environment keys.
Keep credentials, job snapshots and private installation/process receipts out of source.

State-directory identity, plan IDs and exclusive lease/claim files govern admission.
Canonical aliases, PID reuse and active-worker upgrades lack complete acceptance.
Before any future stop/cleanup, prove scope, executable and process-start identity;
preserve ambiguous owners and unrelated sessions.

## State and recovery

1. **No automatic resend of possibly billed requests.** Preserve claims/IDs and
   uncertain outcomes; inspect/reconcile before deliberate new work.
2. **Candidate-only workspace boundary.** Host reviews, applies, tests and integrates.
3. **EOF does not imply a durable execution service.** Receipts persist; execution
   is not independently supervised across host exit, reboot or power loss.

| Event | Implemented behavior / recovery | Gap |
| --- | --- | --- |
| Startup / readiness | Host spawns stdio; initialize establishes protocol identity; relay_status loads config. | Spawn/catalog/status is not provider readiness or model access. |
| EOF / disconnect | Normal loop exit signals the current Relay's active events; reconnect does not replay claimed work. Inspect existing job IDs. | Exceptional exit, bounded drain and older Relay generations: CLR-LC-01. |
| Crash / concurrent connect | Claims suppress resend; state lease admits one batch. Later admission can mark a dead owner's run interrupted. | PID-only identity and partial start/finalization: CLR-LC-02. Do not blindly delete locks or reset budgets. |
| Boot / logon / reboot | No autostart or execution resume promised. Host reconnect starts a frontend; read old receipts first. | Actual restart/owner reconciliation pending. On-demand operation needs no resident supervisor. |
| Network loss / restored | One bounded attempt with sanitized failure; restoration does not trigger resend. | Possibly billed outcomes remain uncertain; blocked DNS/connect: CLR-LC-03. |
| Sleep / resume / logoff / shutdown | No event supervisor; execution depends on process/OS. Reconnect and inspect owner/receipt. | No continuous-execution promise or real OS-event acceptance. |
| Manual stop / startup disabled | Host/user controls frontend; no product startup preference exists. | Exact-owner stop/child teardown unverified. Never kill unrelated sessions by basename. |
| Settings startup | open_setup reports opened after spawn. | Ready/healthy/failure reconciliation absent: CLR-LC-04. |
| Upgrade / reinstall / rollback | Versioned runtime and metadata backups preserve prior material. | Active old/new owner reconciliation and lifecycle rollback: CLR-LC-05. |
| Uninstall / retained data | No automated data-removal workflow or full removal acceptance. | Retained-data policy and exact-owned removal: CLR-LC-05; preserve credentials, outputs and other plugins. |

Budget lock acquisition retries at most 20 times with 10 ms waits, then returns
budget_busy. Those local retries cannot resend provider work. Transport closes the
response/connection and releases its slot when its helper exits. Caller timeout
does not interrupt every OS resolver/connect operation; a lingering helper retains
a bounded slot and checks stop/deadline before send. No tunnel/reconnect loop applies.

## Open backlog

All entries are **OPEN, unreproduced and unfixed** at the recorded runtime commit.
Source structures are observed; fault manifestation and severity require targeted
reproduction. Owner for every entry: Code Relay Product Max. They do not expand
this documentation-only task.

| ID | Source / static risk | Future acceptance gate |
| --- | --- | --- |
| CLR-LC-01 | server.py serve/get_relay: cleanup outside finally, unlocked iteration/no bounded join, old Relay instances replaced | Synthetic EOF, broken pipe and reload during work; all owned generations accounted for, bounded drain, valid receipts, no replay/unrelated stop |
| CLR-LC-02 | core.py run/_execute/_claim_lease: partial start/finalization cleanup, PID without start/boot identity | Thread-start/receipt/release failures, PID reuse/unknown owner, concurrent frontends; one admitted owner, preserved reservations/claims and correlated status |
| CLR-LC-03 | providers.py complete/_perform: DNS/connect can outlive timeout before socket registration | Synthetic blocked connect/DNS, timeout/cancel/recovery; bounded capacity, no late send after cancellation, eventual owned cleanup |
| CLR-LC-04 | server.py open_setup: settings child not tracked through readiness/failure | Delayed/failed startup and repeated launch; truthful spawned/ready/failed state and ownership reconciliation before retry |
| CLR-LC-05 | installer.py and lifecycle acceptance: active-worker upgrade/removal, profile and OS events | Source/package/installed parity; safe upgrade/rollback, manual stop, reconnect, OS events/removal; preserve credentials, data and other sessions |

## Evidence and migration

- [Current documentation adoption](../verification/2026-09-19-rules-adoption.md):
  normative copies pinned to hub 922d950; the incident dependency is link-only.
- [Historical 0.1.1 acceptance](../verification/2026-09-14-preview-0.1.1.md) and
  [compatibility](COMPATIBILITY.md): original dates/skips/boundaries remain.
  Documentation checks do not refresh runtime tests, CI or build acceptance.
- Private takeover, installed runtime and host observations remain outside public
  source/releases. No source document claims full host or OS-event acceptance.
- Pending separate gates: future failure regressions/CI; package/installed parity;
  actual host and OS transitions; fresh-device/upgrade/removal; each host/model;
  live service; artifact readback/delivery. No scientific-native gate applies.
- Governance accepted the existing single Product Max owner without an Ultra model
  transition. Rule adoption records gaps. Future runtime scope starts with
  CLR-LC-01/02 when assigned; no conformance, incident, benchmark or savings closure.

Roll back this documentation adoption by reverting its commit after checking later
owner changes. Do not reinstall/downgrade binaries, clear state or replay requests
to restore documents. The [shared incident reference](../governance/incidents/CB-2026-001.md)
keeps governance scope separate from product implementation and acceptance.
