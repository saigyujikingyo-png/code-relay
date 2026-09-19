# Product lifecycle record

Product / repository / branch / exact commit / package version:
Contract version: 1.0; shared rule version: 2026-09-19.1.
Owner / observation date / status:

## Components and ownership

| Component / lifecycle class | Resident purpose | Startup owner / trigger | Shutdown / crash owner | Profile/session scope and cardinality | Native/job owner |
| --- | --- | --- | --- | --- | --- |
| Fill with actual implementation | | | | | |

Describe the source of truth for each launcher, generated profile and installer registration; canonical identity, locks, executable/PID/start-time fencing, child relationship and multi-account isolation. Distinguish host frontends from execution owners.

## State and recovery contract

Record readiness versus health, probe timestamps/deadlines, failed-connect-before/after-spawn behavior, retry budget, exact owned cleanup, stale/ambiguous registry reconciliation, orphan children, and prevention of uncertain-effect replay. Include explicit stop and disabled-startup behavior.

| Event | Promised behavior / owner | Implemented behavior | Evidence / gap |
| --- | --- | --- | --- |
| Host connect/disconnect | | | |
| Crash / retry / concurrent connect | | | |
| Boot / logon / reboot | | | |
| Network unavailable / restored | | | |
| Sleep / resume / logoff / shutdown | | | |
| Manual stop / startup disabled | | | |
| Upgrade / reinstall / rollback | | | |
| Uninstall / retained data | | | |

## Verification

Separately record portable regression/CI, installed package and launcher parity, current-device native execution, OS-event acceptance, fresh-device acceptance, each remote account binding/catalog/actual call, live external service state, artifact readback and delivery. Include exact commit/package, host/model, observation date, scope and remaining gaps. Mark each claim current, historical, probable, unverified or planned; unsupported events require an explicit reason. Keep private identifiers and credentials out of public evidence.

## Migration

List exact next components, invariant, accountable Product Max owner, prerequisites, required acceptance and rollback. Rule adoption and implementation conformance are separate. Link the shared incident when applicable; do not inherit another product's passing results.
