# Documentation installation refresh: docs.1

Date: 2026-09-19. Runtime and MCP server version remain **0.1.1**;
output contract remains **1.0**. The docs.1 release identifies an installation
and bundled-document revision, not a provider or task-execution upgrade.

## Reproduced gap and correction

The 77469d2 governance adoption updated public source and archive document lists.
The installer still copied only the skill, README and license; its frozen resource
list also omitted the new documents. The source-install cache fingerprint ignored
documentation changes. Source adoption therefore did not update installed rules.

The installer and frozen builder now share one explicit public resource list,
including rules, lifecycle/ownership documents and offline dependencies. Missing
resources fail preflight before installation changes. Existing documents are
backed up; source cache versions incorporate document and manifest content.
Frozen versions use the complete executable hash, including embedded resources.
Existing marketplace entries are not rewritten during updates.

No provider, budget, job, credential, MCP contract or shutdown code changed.
CLR-LC-01 through CLR-LC-05 remain open; this corrects document delivery and
installation content, not their wider lifecycle acceptance requirements.

## Focused source evidence

Five new isolated checks failed against the prior installer: governance document
delivery, document-only cache refresh, missing-document preflight, existing
marketplace preservation and recoverable document replacement. These use synthetic
homes and a fake Codex command, never the real installation or provider.

After the fix, all **12 installer/document/boundary tests passed**. Public metadata
and syntax checks passed. Real isolated stdio discovery/invocation validated all
seven schemas, status/errors and text fallback without API calls.

Only affected tests are claimed. The complete historical runtime matrix is not
rerun for this document-installation revision. Frozen build/self-test, package
hashes and actual host installation are separate evidence recorded in release notes
and the private installation receipt; this source record does not substitute for them.

## Version, recovery and acceptance

Keep the original v0.1.1 release and its artifacts for rollback. Install docs.1
through the supported installer; its content-derived Codex suffix identifies the
new installed payload while the runtime version remains 0.1.1. Existing tasks may
retain the old loaded plugin until normal new-task/reload pickup. Do not edit
internal caches or close a shared host to force that transition.

Configuration, credential storage, budget reservations, private source snapshots
and job receipts stay outside the install payload. Live provider/model access,
full coding workflows, fresh-device/removal, OS events and other hosts remain
unverified independently of document/package installation.
