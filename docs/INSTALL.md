# Install and use

## Windows preview

Download the Windows x64 ZIP from the project's GitHub prerelease, verify its SHA-256 checksum, extract it and double-click **code-relay.exe**. The bundled runtime includes Python and the settings window. No Git checkout or separate Python installation is required for this package.

In local settings, add an API model profile, select the exact project folder, set request limits, and enable calls when you authorize sending selected source to those endpoints. Enter the key in the masked local field. Windows stores it with user-scoped DPAPI, independently of host accounts. Blank key fields preserve an existing credential.

Use **Install / reconnect in Codex** in the settings window. Installation uses Codex's public plugin command and preserves other plugins. Start a new Codex task after installation to load the tools and skill.

One profile identifies one model. To use several ELM models, duplicate the connection with a new profile ID and exact model ID; retain the same endpoint and key reference. Capabilities and priorities can differ. Use the endpoint and model identifiers supplied to your ELM account, not guessed brand names.

Ask Codex: “Use Code Relay to delegate independent test and documentation tasks to my configured models, then review, integrate and test the results.” Code Relay opens settings if the project or credentials are missing.

## Source and other hosts

Developers can run `python -m code_relay setup` or `python -m code_relay serve` with Python 3.11+. The core has no external runtime dependencies. Other MCP stdio hosts can launch that command from this repository or the installed package. Their connection UI and model acceptance are unverified. ChatGPT Chat and cloud Work connectivity are not included in this local preview.

Use an environment-variable key reference on Linux/macOS; this preview does not persist plaintext keys. Headless cloud checks use synthetic data and do not need a key or university login.

## Update, recovery and removal

Install the new release through the same settings window. Configuration, credentials, unrelated plugins and old versioned runtimes are preserved. Installation metadata backups are saved under the user's `.code-relay-install-backups` directory. Reinstall a previous release to roll back, then start a new Codex task.

Remove Code Relay through Codex's plugin UI or `codex plugin remove code-relay@personal` (substitute the actual personal marketplace name). Local settings and job receipts remain available; remove them deliberately only when no run is active. There is no automatic uninstaller for retained data in this preview.

Settings live in the platform's CodeRelay local data folder. Job records contain selected source and candidates. Archive or remove old receipts there when the configured storage limit is reached; never publish that directory.

A claimed plan cannot be rerun automatically after an interruption. Inspect its receipt before making a new plan. When the owning process has definitely exited, a new run safely recovers admission and marks the old receipt interrupted without resending it. Unknown or live process ownership fails closed. If a short-lived `budget.lock` remains after every Code Relay process has stopped, preserve receipts and remove only that stale lock. This never resets call reservations. A graphical recovery wizard and automatic updates are not yet implemented.

## Connection limits

OpenAI-compatible services differ. Select the supported output-token parameter, supply exact model IDs and verify a small task first. The transport uses direct TLS connections and does not inherit environment HTTP proxy settings; explicit proxy support is a known gap. HTTP is allowed only for explicitly opted-in loopback testing. Redirects, generated tools and automatic retries are disabled.
