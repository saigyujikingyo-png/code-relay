# Governance and product ownership

Effective shared baseline: **2026-09-19.1**.

Chembridge Governance & Architecture uses **Astra High** (`gpt-6-astra`, high) for shared principles, contracts, RFC/ADR, cross-product classification, migration audits, regression requirements and incident closure. Each product has exactly one accountable long-term **Astra Max** (`gpt-6-astra`, max) development owner for implementation, debugging, tests, installers, releases and routine architecture.

**Astra Ultra** is reserved for bounded exceptional consultations with a specific hard question and return path to Governance High or Product Max. It does not retain parallel long-term product ownership. Record actual model/effort availability; a task title or requested preset is not execution evidence. This division does not replace the separate Terra max end-user benchmark.

## Transfer procedure

1. Inventory the actual task, repository/branch/HEAD, model/effort, stage, active work and uncommitted changes. Keep private task/account identifiers in private coordination records.
2. Reach a safe checkpoint before switching or retiring an owner. Preserve a commit or explicit complete diff/untracked-file manifest and relevant acceptance receipt. Do not force-stop native experiments, stash unrelated work or archive a source task early.
3. The outgoing owner produces a bounded A–I handoff: identity; current state; architecture/ownership; preserve/do-not-regress; layered verification; deployment; exact next work/invariant/gate; cross-product dependencies; claims boundaries. Do not copy the entire conversation or treat reasoning as factual evidence.
4. Product Max reads the handoff, product instructions and current shared rules; rechecks GitHub/default/working branches, HEAD, PRs/issues and recent commits; checks applicable installed runtime/remote state; and minimally verifies material claims.
5. Max writes a takeover receipt: accepted/partially accepted, verified repository/branch/HEAD/stage, stale items, blockers, first concrete task and acceptance gate. Only then does ordinary engineering resume.
6. After verified takeover, the outgoing Ultra context is consultation-only (or archived if appropriate). Keep one product owner; other architecture/native contributors have bounded scopes under that owner. Do not erase historical evidence or collapse branch and native acceptance boundaries.

Migration states: `NOT_STARTED`, `HANDOFF_REQUESTED`, `HANDOFF_READY`, `MAX_VERIFYING`, `MIGRATED`, `BLOCKED`, `ULTRA_CONSULT_ONLY`. An already-Max task still needs the relevant verified ownership/checkpoint receipt; do not claim it underwent an Ultra transition.

## Governance loop

Review current source/runtime evidence → classify product defect versus shared gap → assign concrete Product Max requirements → review source fix and regressions → audit other products → update shared contract/templates/version → verify migration and layered acceptance → close only satisfied incident gates.

Recheck current GitHub default branch/HEAD, shared baseline/templates/catalog/profiles, relevant product HEAD/open items/releases, and applicable installed/remote state at the start of a work cycle. Historical passes are leads. Keep unresolved items open with an owner, next action and evidence requirement.

Product-specific graph/toolbox/parser/layout behavior normally stays with Product Max. Worker ownership, retry cleanup, profile isolation, installer lifecycle, credentials, host binding, MCP transport, artifact delivery and acceptance methodology require shared-gap assessment. Do not turn governance into the main product implementation task.

## Active incident

[CB-2026-001](incidents/CB-2026-001.md) remains open. Its initial audit is dated and must not be silently rewritten as current acceptance. Subsequent checkpoints belong in the migration ledger and incident addenda.
