# Runtime and connection lifecycle contract

Contract version: **1.0**. Shared rule version: **2026-09-19.1**.

This contract specifies observable semantics and ownership invariants. It does not require a common runtime, Windows startup task, resident service or host adapter. A product records implementation and acceptance separately using [the lifecycle record](templates/LIFECYCLE_RECORD.md). Existing products migrate with explicit gaps; adoption does not retroactively accept a release.

## 1. Classify components, not brand names

| Class | Startup and shutdown owner | Disconnect and OS lifetime | Required acceptance |
| --- | --- | --- | --- |
| persistent_remote_connector | A declared installed supervisor owns startup, crash recovery and owned children; explicit stop overrides automatic recovery | An agent conversation ending normally does not stop the connector. State the actual boot/logon/logoff/shutdown and network/sleep policies | Real remote binding, catalog and calls, plus logon/reboot/network recovery, isolation and stop/upgrade/removal |
| on_demand_local_companion | A local host or explicit user action starts a frontend; the declared owner stops it or it exits on EOF/idle | Declare what EOF cancels, detaches or leaves unknown. No autostart expectation unless separately promised | Host launch/EOF, simultaneous frontends, crash, reinstall and no unintended resident process |
| native_session_bound_bridge | A declared owner attaches to or creates an explicitly identified native session; ownership determines allowed stop/close | Preserve unrelated sessions and unsaved documents. Host disconnect is not permission to terminate user-owned software | Session identity/revision, close/save/reopen, crash, orphan reconciliation and non-interference |
| durable_job_service | An independent coordinator owns accepted jobs; frontend lifetime and job lifetime are distinct | Declare precisely whether durability covers frontend exit, host exit, user logoff or OS failure. Persistence does not promise continuous execution through reboot | Disconnect/cancel/crash and restart recovery, idempotency, effect quarantine, ownership and original artifact readback |

A product may compose these classes (for example an on-demand frontend with a durable coordinator). Additional classes require a demonstrated product need and a small reviewed ADR. Record startup trigger, shutdown/crash owner and resident-process purpose for every component.

## 2. Canonical ownership and cardinality

- Define the owner scope: operating-system user, account/profile, canonical state/profile directory, executable identity and native session/job identity where applicable. Normalize paths and address aliases, case and reparse points according to the platform.
- For a single remote profile plus canonical profile directory, permit at most one active owned tunnel daemon and at most one corresponding logical MCP server child. Packaging launch shims must be declared explicitly; they do not permit extra independent backends. Multiple accounts have separate scopes.
- Multiple host frontends are allowed when documented. They must not create competing execution owners, consume extra licensed sessions or weaken root/session locks. A scheduler setting or wrapper-local mutex alone is not proof of the cross-launcher invariant.
- Prove ownership before stop/reuse/cleanup. Combine actual registry/status with profile/directory, executable, PID and creation/start identity, and parent-child evidence as applicable. PID alone, executable basename alone and a stale parent PID are insufficient. Recheck identity immediately before a destructive action. Preserve unknown or conflicting owners and return a bounded diagnostic.
- Native session and accepted job ownership remain distinct from tunnel ownership. Disconnecting a tunnel must not silently cancel durable work or close an unrelated native application.

## 3. Readiness, health and connection layers

Define states covering absent, spawning, running/starting, locally healthy, locally ready, unhealthy, dead, stale registration and unknown. Distinguish a pre-spawn failure from failure after a process could have been created. Expose timestamp, owner identity and scope with status; stale success files are not current health.

Use bounded readiness polling of the same proven attempt/daemon. Bound each command as well as the total deadline. Clear or invalidate old observations when a probe fails; do not accept yesterday's or an earlier iteration's ready value. Do not spawn a new daemon merely because a live process is still warming. Specify what is supervised after readiness and how ongoing unhealthiness is detected.

Record these gates separately: local process → local MCP readiness → tunnel/control-plane heartbeat → registered app/binding → app installed in the intended account → app connected → fresh host tool catalog → successful bounded tool call → product live-service/native result. A healthy tunnel, successful HTTP connection or listed tool name proves none of the later gates. Cached university data does not prove live authentication.

## 4. Retry, reconciliation and uncertain effects

- Mark an attempt before invoking anything that may spawn. If connect, status, readiness, child startup or registration fails, reconcile that attempt's owned runtime before the next connect, including failure with incomplete registry state.
- Account for children that can outlive parents and daemons no longer represented by the latest registry entry. A registry stop command must be scoped and verified; supplement it only with proven exact ownership.
- Reuse a verified healthy existing owner. Reconcile proven stale owners. On ambiguous ownership, failed cleanup or unconfirmed startup, stop the retry sequence and report the unresolved state; do not add another worker.
- Declare retry budgets/backoff and recovery after a prolonged network outage. Authentication/permission failures should not become endless reconnect loops. Retain a useful sanitized failure receipt without runtime keys or raw credential-bearing responses.
- Runtime reconnection must not replay an accepted scientific write, job or possibly billed provider request. Keep durable operation identifiers, idempotency keys and unknown-outcome quarantine. Read/reconcile status before any deliberate resubmission.

## 5. Startup, stop and operating-system events

Every class records boot, logon, logout/shutdown, sleep/resume and unavailable/restored network behavior. Mark unsupported events with reasons and user-visible recovery, rather than silently inheriting a different class's policy.

For persistent connectors, identify startup registration, user scope, privilege, trigger, instance policy, readiness dependency, restart budget and who owns each descendant. Network available is not equivalent to DNS/control-plane readiness. A disabled startup task or explicit manual stop must remain stopped until an authorized start; the supervisor must not defeat user intent.

Specify whether stopping the supervisor also stops its owned tunnel/MCP descendants and how abrupt supervisor death is recovered. Declare whether durable jobs continue, cancel, become interrupted or require reconciliation. Avoid shutting down the workstation or interrupting unrelated work to run acceptance; arrange a safe checkpoint first.

## 6. Installation, upgrade, rollback and removal

Maintain a release-owned source of truth for runtime launchers, generated profile adaptations and startup registrations. Do not treat a patched installed file as the fix. Record source/package version and launcher content hash where useful.

Upgrade and reinstall preserve account identities, secret references, profile isolation, enabled/disabled startup preference and active job ownership. Reconcile old workers before replacing their executable/configuration; prevent old and new owners from running concurrently. Migrate every supported profile, preserve rollback and verify launcher/registration readback. Do not assume replacing an engine migrates independently installed wrappers.

Uninstall removes only owned startup registrations and workers, with an explicit retained-data policy. Preserve unrelated plugins, native sessions, accounts, credentials and user outputs. Rollback must address both runtime and lifecycle configuration, not only binary version.

## 7. Evidence and migration

Each product maintains a versioned lifecycle record with exact source/package references, declared versus implemented behavior, owners, gaps and dated evidence. Use confirmed/current, historical, probable, unverified and planned claims accurately. A failure of one class must not impose unnecessary persistence on another.

Persistent-connector acceptance includes normal connect, delayed ready, failure before/after spawn, status failure, readiness timeout, child failure, incomplete registry, daemon crash, retries, healthy/stale existing owners, same-profile duplicate prevention, simultaneous accounts, login/reboot, network unavailable/restored, manual stop, disabled startup, upgrade/reinstall, removal, and sleep/logoff/shutdown where promised. Check non-interference and cardinality after each relevant transition. Portable fixtures establish failure-path behavior; actual installed OS events and host accounts require independent receipts.

Governance reviews cross-product defects and tracks rule adoption. Product owners implement and validate fixes in their own repositories. Incident closure requires the applicable current-device, remote host and OS-event gates as well as source fixes; publishing this contract is not closure.
