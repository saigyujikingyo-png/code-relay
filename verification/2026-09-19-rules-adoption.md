# Shared rules adoption: 2026-09-19.1

Scope: documentation and its version/package references only. Runtime/package version
remains **0.1.1**; output contract remains **1.0**. No release asset, installed runtime,
configuration or runtime behavior is changed.

Approved source: [Chembridge 922d950](https://github.com/saigyujikingyo-png/chembridge/commit/922d95041b3b857f6ba11fbfb2817b18712ef605).
Product checkpoint before adoption: 60e3dcbe35b762be44f2812b64f7035963a50ffb;
runtime implementation: 30ed044c3371732c99772b67a8ec0ed68234f9af.

## Adopted source

Five normative documents are copied byte-for-byte from the pinned hub commit:
DEVELOPMENT_PRINCIPLES.md, CLOUD_STORAGE.md, RUNTIME_LIFECYCLE.md,
governance/OWNERSHIP.md and templates/LIFECYCLE_RECORD.md.

The incident dependency is a link to the governance-owned record. Contributor/version
references and source/Windows archive document allowlists include linked dependencies.
No archive is built here. The [lifecycle record](../docs/LIFECYCLE.md) classifies the
on-demand frontend and tracks CLR-LC-01 through CLR-LC-05 as open, unreproduced and
unfixed. Product Max ownership and Terra max benchmarking remain separate.

## Validation

Local documentation results on 19 September 2026:

- PASS: all five normative copies match the approved hub commit byte-for-byte and by Git blob identity.
- PASS: release metadata, Python syntax and credential-pattern check (scripts/check_release.py).
- PASS: 21 local references in changed Markdown files resolve; Windows archive documentation dependencies form a complete local set.
- PASS: source inventory contains all 15 changed files among 51 selected files; Windows document allowlist contains 17 entries. These are inventory checks, not archive builds.
- PASS: git diff --check and explicit changed-path review. Runtime, protocol/plugin configuration, workflow skill, tests and CI workflow remain unchanged; the two script edits are document lists and the rule-version reference only.
- PASS: changed-file scan excludes private handoff/takeover paths, task/account identifiers and credential patterns. This bounded scan is not a general security audit.

No full runtime test suite, synthetic self-test, package build, paid API call or new
runtime CI acceptance is claimed. Existing whole-matrix CI is intentionally skipped
for this documentation-only commit. Historical results remain in their dated receipts.

## Acceptance boundary

Rule adoption is complete only when the document checks pass. Runtime lifecycle
conformance remains **PARTIAL**; installed/OS-event, real-provider, full host workflow,
fresh-device/removal and delivery gates remain independent. Private handoff, takeover,
account, installation and process evidence is excluded. No cross-product incident
is closed by this source adoption.
