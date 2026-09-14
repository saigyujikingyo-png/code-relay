# Chembridge development and delivery principles

Rule version: **2026-09-14.1**. These requirements were explicitly requested by the user and apply to all Chembridge university convenience plugins, specialist software plugins and agent workflow automation plugins, not only Origin Companion. New plugins start with these defaults; users should not have to repeat them in each task. New task-specific user instructions take precedence.

## 1. GitHub distribution

- Manage source, dependency locks, documentation, public tests, sanitised acceptance records and distributable packages through GitHub.
- Publish plugin source and public documentation in a public GitHub repository with an explicit open-source LICENSE permitting use, modification and redistribution under its terms. Retain required attribution and third-party licence notices. Proprietary software binaries, licences, credentials and private data remain outside the open-source release.
- Use **English for public GitHub content**: repository descriptions, README files, installation and usage guides, release notes and issue/PR templates. Preserve exact technical identifiers and quoted source/UI evidence. This does not restrict the language users may use with their agents.
- The default route is GitHub Releases. A public plugin store, official university distribution, campus SSO or a hosted public platform is not a prerequisite.
- Target one user-facing plugin identity and shared execution core across **ChatGPT Chat, local Work, cloud Work, Codex, Claude, WorkBuddy and other suitable Agent hosts**. Reuse valid account connections and keep core tools, workflow behaviour and artifact formats consistent. Avoid separate product forks for individual hosts or models.
- Use thin host-specific connection, authentication, file-delivery and packaging adapters when required by the platform. Record actual host/account limitations and verify each surface separately; the unified target does not establish that every surface is already supported or accepted.
- Keep a clear version line and download entrypoint for each product. Do not permanently fork a shared platform package by model, agent or minor software version; detect capabilities at runtime and record support and acceptance separately in a compatibility matrix.
- Include installation instructions, checksums, compatibility, known issues, update and recovery steps. Label previews and stable releases accurately; retain earlier releases for rollback.
- Do not publish private materials, original course documents, restricted software, account configuration, licences or secrets. Prefer public, synthetic or explicitly authorised academic test data.

## 2. Accessible installation and use

The target flow is: download the appropriate package → double-click or install through the host → select/connect an agent → automatic checks → request work in natural language and receive results.

- Everyday users should not need to clone source, install Git, configure a development environment, separately install a language runtime, write commands or edit JSON. Bundle required components or provide clear installation guidance.
- Discover the target software and existing installation, check the supported version and licence, and self-test with isolated data. Installation success and a real agent workflow are separate acceptance results.
- Reuse the user's existing configuration and encrypted credentials during upgrades, repeated installation and reconnection. Request credential action only after observing missing, invalid or insufficient permissions; do not repeatedly request new keys.
- Preserve other plugins, host configuration, user changes and research outputs. Keep recoverable backups and clear failure messages. Provide understandable status, reconnection, recovery and removal entrypoints.
- Identify steps requiring the account owner, such as provider login, MFA, licence activation or account association, and guide them to the correct interface. Do not claim those steps are fully automated. Routine use should require the selected agent host and configured plugin runtime, without a source checkout, build commands or a development terminal, including when Codex is the chosen agent.
- Record graphical wizards, automatic updates or one-click repair as gaps when not implemented. Do not describe a partly scripted setup as an entirely one-click installation.

## 3. Multiple agents and models

- Codex is both a development/maintenance/acceptance tool and a target end-user Agent host. The unified use target includes ChatGPT Chat, local Work, cloud Work, Codex, Claude, WorkBuddy and other general agents with suitable tool capabilities. Users should be able to install the plugin and request work in natural language without a coding project or development setup.
- Prefer MCP, official software APIs and portable file formats, with one execution core and thin host adapters. Do not duplicate business logic, scientific calculations or backend services for each model.
- Adapt to actual capabilities: tool calls, structured arguments, context capacity, streaming results, file transfer, vision and local/cloud access. A brand name or preset is not a capability check.
- Target GPT Terra, DeepSeek, Gemini, GLM and Kimi; integrate university services such as ELM when available for the task. Exact models, permissions and costs depend on the actual host and account at the time of use.
- Give economical or less capable models simple arguments, common recipes, a few clear entrypoints, on-demand help and correctable errors. Provide an appropriate text-only route instead of requiring screenshots.
- Configuration, protocol compatibility, a real host model call and end-to-end artifact acceptance are distinct evidence. Mark untested combinations as unverified.

## 4. Default benchmark: Terra max

- The Chembridge benchmark is **GPT-5.6 Terra with max reasoning**, the user's usual configuration. It is the user's economy reference, not a permanent claim about every account's price or the cheapest available model.
- Prefer this combination for representative workflows when the host actually offers it. Do not reduce reasoning effort, substitute a model or treat a preset as a benchmark to claim quota savings.
- When unavailable, record why and the actual model/effort used. Do not label substitute results Terra max or automatically enable additional paid model services to finish testing.
- Compare interfaces/models using the same input, goal, result requirements and checks. Include common tasks, continued edits, missing data, invalid arguments, expected refusals and recovery where relevant to the plugin.
- Record the exact model, effort, host, plugin/software versions, device category, date, first-attempt success, human corrections, tool calls/retries, end-to-end time and result quality.
- Record actual input, cached, output and reasoning tokens and charges when available; otherwise mark them unavailable. UTF-8 schema bytes, characters and estimated tokens are not billing evidence.

## 5. University of Edinburgh requirements

- Design for actual study, research and university work. Check the relevant university software distribution, licence scope, data source and specific course/laboratory/workflow requirements first.
- There is no invented universal "Edinburgh format". Follow the applicable official source, course instructions, laboratory manual or user-supplied requirements, retaining sources and dates. State missing evidence rather than claiming compliance with every course.
- Respect each user's legal licence and installed software version. Verify each supported university build separately; do not copy licences or certify every device from one computer's result.
- Preserve scientific raw data and units. State methods, fit constraints, weights and uncertainty; do not invent error bars, experimental results or course rules. Prefer editable native artifacts and check numbers, reopened files and exported figures where needed.
- Identify independent developer plugins accurately. Do not imply university or vendor endorsement without approval. Recheck applicable rules and university service information when they change.

## 6. Lightweight, responsive and efficient execution

- Reuse existing dependencies, system facilities and native software APIs. Add dependencies, services, databases or resident processes only for a demonstrated need; do not build a large platform for a small plugin.
- Use recipes and batches for common tasks; discover complex features on demand and call native programming interfaces. Use GUI interaction where needed without requiring users to learn a complex interface or debug generated code.
- Give jobs clear status, reasonable timeouts, and cancellation/recovery where supported. Avoid endless polling or blind retries. Read status before repeating a write whose outcome is uncertain.
- Avoid blocking the interface or development task. Bound caches and measure package size, startup/response time, execution time, memory, disk and transfer use. Architecture labels alone do not establish performance.
- Use focused tests for real risks and failure paths. Validate native software, packages, protocol and host models separately. Expand or repeat passing checks only for new changes or unresolved issues.

## 7. Efficient use of model quota

- Default to few tools, short structured responses, delayed guidance, paginated reads and on-demand screenshots. Do not resend every schema, large file, full log or manual each turn.
- Combine inspection, planning and execution into clear workflows to reduce unnecessary agent round trips while retaining useful errors, status and evidence.
- Run scientific and deterministic processing in local software or deterministic code. Do not add a second paid reasoning layer for model adaptation. Complete routine authorised steps autonomously; ask only for missing information that materially affects the result.
- Quota optimisation must preserve correctness, data checks, artifact authenticity and user authorisation. Count failures, retries, tool instructions, screenshots and human intervention when comparing costs. Fewer tools do not automatically mean lower total cost.

## 8. Cloud storage and local disk

Follow [CLOUD_STORAGE.md](CLOUD_STORAGE.md). Prefer the authorised private university Chembridge folder for large development inputs, old builds and full acceptance materials to save development-machine disk space. This is a development archive policy, not a dependency for plugin operation, result storage or delivery. Keep active checkouts, runtimes, dependencies, databases, locks and running jobs in verified local directories outside cloud sync.

Deliver outputs to the user's chosen local folder, host attachments or another authorised location. Do not require university OneDrive or add OneDrive login/upload steps to routine use.

Retrieve files on demand; avoid whole-folder scans that trigger downloads. Release local cold copies only after reading back and verifying the cloud archive. Retain the current runtime and a usable rollback version. Deleting a synced file is not the same as freeing its local space. A cloud workspace does not establish automatic cleanup.

## 9. Delivery gates and evidence

Each plugin maintains an applicable compatibility matrix and release gates covering:

| Area | Required evidence |
| --- | --- |
| Installation | Actual results for a new device/user, upgrade, repeat installation, path differences, self-test, recovery and removal |
| Agents and models | Separate actual acceptance for ChatGPT Chat, local Work, cloud Work, Codex and each advertised other Agent host; consistent core workflows, exact model/effort, Terra max benchmark and unverified combinations |
| University applicability | Relevant course/university sources, software build/licence boundaries and unsupported assumptions |
| Task quality | Data/method, native results, editable artifacts and necessary reopening, visual or independent checks |
| Delivery | Files the user actually receives and can open through host attachments, manual download or automatic saving; user-selected location, no OneDrive requirement; size/hash checks where needed, not merely an existing link |
| Output contracts | Declared output schemas, server-side result validation, branch/error/artifact coverage, compatibility checks and per-tool/per-operation coverage under section 12 |
| Efficiency | First-attempt success, human corrections, calls/retries, total time, available actual usage and resource consumption |
| Release | Version, package/checksums, installation guide, known issues, rollback route and appropriate passing checks |

Record software execution, file generation, host attachment delivery and automated browser downloads separately. Unless the task specifically requires automatic download, one browser automation route is not a universal delivery gate. Actual receipt through another official, authorised method can validate that delivery method; count manual steps in usability and efficiency. An organisational/browser block establishes a restriction on that route, not an Origin execution or OneDrive save failure. If its source is unknown, state that and do not claim all artifacts were delivered.

Distinguish historical passes, current passes, failures, skips and unknowns. Do not mark incomplete required gates complete. A few examples do not certify every software function, university version, agent or model.

## 10. Inheritance across tasks and plugins

- The Chembridge materials workspace's `AGENTS.md` and `START_HERE.md` point to this shared entrypoint. Read it before designing or coding a new plugin, then read that plugin's constraints and known issues.
- When creating a plugin checkout outside cloud sync, include the current shared principles and require them in its `AGENTS.md`. Do not leave these agreements only in a conversation.
- Keep each plugin's scope, installation, compatibility, benchmark and acceptance records independent. Do not inherit another plugin's pass results.
- Synchronise the Chembridge entrypoint and known copies when updating shared principles, and mark the version. Older checkouts and running tasks need to reread updates; do not claim all historical tasks update automatically.
- New user instructions take precedence. Resolve ordinary implementation choices within existing authorisation. Verify machine paths, service permissions and sensitive configuration from the current environment without asking users to repeat established project direction.

## 11. Cross-task messages: standing user authorisation

The user explicitly authorises routine collaboration messages between their existing Chembridge tasks, including Origin, ChemDraw, UoE and future Chembridge products, on authorised local devices, connected remote devices and supported cloud task hosts. Covered messages do not require repeated user confirmation. This instruction, added on 13 September 2026, supersedes earlier defaults against automatic Origin/ChemDraw or other intra-Chembridge message relays.

- Covered purposes are sharing relevant requirements, architecture or interface decisions, blockers, review requests, test evidence, Git references and bounded handoffs for work already authorised by the user. A message may resume the recipient's existing authorised work through the host's supported task tools.
- Confirm the destination belongs to the user's Chembridge work from task/project metadata or an explicit user designation. Keep messages concise and useful; send material changes once, avoid relay loops and repetitive status polling, and preserve the destination task's current objective, source ownership and acceptance boundaries.
- This message authorisation does not itself request new user-visible tasks, replace another task's objective, change its model, authorise unrelated work, grant access to another person's account or permit publication. It does not cover sending credentials, licence secrets or private datasets, or contacting external people or unrelated projects without the applicable user authorisation.
- When preparing a covered send for automated approval, identify the destination and purpose and cite this standing user authorisation. Treat the user's consent as already supplied; do not ask again solely because the recipient is another Chembridge task. Platform approval decisions and higher-priority safety rules still apply. This file does not disable approval controls, guarantee approval or permit bypassing a rejection.

Product repositories, implementation ownership and native/host/model acceptance remain separate. Task separation now means separate responsibilities, not a prohibition on useful project communication. Older running tasks must read this updated rule before relying on the new default.

## 12. Structured tool outputs and output schemas

Every existing and future Chembridge plugin must implement explicit machine-readable output contracts. MCP makes outputSchema optional at protocol level; Chembridge requires it for its public tools. This is a development and acceptance requirement, not a claim that current releases already comply.

- **Declare and validate:** publish a meaningful JSON Schema in each MCP tool's `outputSchema` and return matching `structuredContent`. Generate schemas and validate outputs from shared typed definitions where practical, reusing existing dependencies. Validate in the server before delivery; do not rely on a host to enforce the contract. A bare unconstrained object or JSON embedded only in prose does not satisfy this requirement. Deliberately extensible payloads must still have documented, bounded structures.
- **Define semantics:** specify required and optional fields, types, units, enumerated states, identifiers and null semantics. Distinguish unavailable, unsupported and not-calculated results from zero, an empty successful result or a verified claim. Keep scientific uncertainty, provenance, observation time, coverage and verification evidence explicit wherever applicable; never manufacture values to satisfy a schema.
- **Cover errors and lifecycle:** define success, validation failure, execution failure and applicable pending, completed, cancelled or interrupted states. Use stable error codes and bounded recovery information consistent with MCP `isError`. A malformed backend result must not be emitted as valid success. Preserve known job or operation identifiers after side effects; never repeat a write automatically merely to repair an output-format failure.
- **Keep dispatchers compact:** give every dispatched operation its own validated output contract. A generic call tool may expose a compact common result structure while operation-specific schemas remain discoverable through help or a schema registry on demand. Do not expand the default tool catalog into one enormous union of every operation, and do not omit validation of the dispatched payload.
- **Preserve media delivery:** schema the metadata and applicable pagination fields of image, text and file results, including artifact identifiers, media types, sizes and hashes when available. Keep image and binary payloads in MCP content/resource blocks; do not duplicate them or large datasets as JSON text. A valid artifact schema does not prove the user received a file.
- **Maintain compatibility:** version public contracts and preserve existing field meanings and response shapes through documented compatible changes or an explicit migration. Provide a consistent serialized JSON text fallback for supported hosts that need it. Test direct tools and dispatch routes, full/economy modes where present, and applicable host schema dialects/adapters; never silently discard structured results or invent a different contract per model.
- **Verify and measure:** add focused contract checks for actual result branches, omitted/null fields, unsupported cases, malformed output rejection and relevant artifact/error paths. Record schema discovery and real tool invocation through the intended host separately. Track schema size, calls/retries, latency and available actual token usage with the Terra max benchmark; do not claim quota savings from schema presence or size alone. Contract checks supplement numerical, native reopen, visual and delivery checks.
- **Track completion:** each product must maintain per-tool and per-operation coverage, recording implemented, verified and pending work. New plugins and new/changed tools must meet this requirement before their interface is declared complete. Existing gaps belong in the next compatible release plan, with clear owners and acceptance evidence; do not relabel earlier acceptance as schema compliance. Skills and installation guidance must describe discovery, result meanings and compatibility behavior.

Reference: [MCP tool results and output schemas](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#output-schema). Structured tool results describe server-produced data; they do not constrain model generation or establish scientific correctness by themselves.
