# Architecture and acceptance contract

The host model decomposes the user's request, retains architecture, security, complex implementation and final review, and supplies small tasks with explicit risk, complexity, acceptance criteria, context files and writable files. Deterministic policy selects an enabled model profile by capability, input limit and priority. There is no additional paid planner.

One profile describes one model. Profiles can share an API endpoint and key reference. ELM is an OpenAI-compatible connection configured with the user's actual endpoint and exact model identifiers, not a bundled list of claimed entitlements.

## Workflow

1. Local setup grants exact workspace roots and configures independent API credentials and call limits.
2. Planning makes no network request. It freezes selected UTF-8 bytes and hashes, destinations, task scope and configuration. Sensitive paths/content, ambiguous tasks and dependencies remain with the host.
3. Run verifies that files and configuration still match, atomically claims the plan and reserves the call budget. A repeated run returns the existing receipt.
4. Independent tasks run with bounded concurrency. Each receives one request, no tools and no automatic retry. Queue cancellation and uncertain dispatched outcomes are distinct.
5. Strictly validated replacement text becomes a local candidate and unified diff. The workspace is never modified by the core.
6. The host reads the candidate as untrusted data, reviews it, applies suitable changes with its own authorised editing tools, runs appropriate checks and reports actual results. Dependencies are replanned after reviewed changes land.

## Required invariants

- No account-cookie extraction or host subscription forwarding.
- Secrets are referenced by environment variable or Windows user-scoped DPAPI storage, never in public configuration or output.
- Explicit relative file names only; reject traversal, reparse points, aliases, sensitive paths, binary and oversized files.
- Freeze bytes once; do not read fresh code into a dispatched request after plan approval.
- Configuration/endpoint changes invalidate plans. In-flight requests may already be billed.
- Durable run claims prohibit automatic resend after restart or uncertain failure.
- Reject cross-task write/write and read/write conflicts. Dependency graphs stay with the host in this preview.
- Record actual provider usage when supplied; prices, savings and unavailable token fields remain unknown.
- No worker shell, workspace write, automatic test execution, git mutation, deployment or publication.
- Local receipts contain private source and must stay outside public source and releases.

## Runtime lifetime

The stdio frontend is an on-demand local companion. Normal EOF requests cancellation of the current in-process batch; persisted submission claims prevent automatic resend but do not supervise execution across host exit or reboot. Exceptional disconnect and ownership recovery have open, unreproduced risks. See the [lifecycle record and backlog](LIFECYCLE.md) for declared owners, readiness, OS events and separate acceptance gates.

## Evidence

Portable tests, loopback protocol tests, an executable package, installed host tool discovery, live provider calls, model quality and a Terra max benchmark are separate acceptance layers. A synthetic result cannot establish a real model's suitability or a university entitlement.
