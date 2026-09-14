# Privacy and trust boundaries

Code Relay runs locally and reads only the exact project roots and relative files selected in a task. It sends frozen source bytes, task instructions and acceptance criteria to the configured API endpoint when the host runs an authorized plan. Provider terms and university eligibility remain specific to that connection.

Configuration contains key references, never plaintext keys. Windows DPAPI uses the current user's scope. Environment keys are read only by their configured names. Profiles sharing the same protocol, endpoint and key reference can reuse one stored key. Changing the endpoint does not reuse a DPAPI credential.

The plugin does not inspect browser cookies, ChatGPT sessions, Codex authentication files, university sessions or account quotas. It has no telemetry, hosted account system, central service or OneDrive dependency. It does not follow redirects with credentials.

Local job receipts contain private source snapshots, candidate code, destinations and actual reported usage. They are stored outside the checkout in the user's local data directory. Do not commit or upload them. The source scanner blocks known sensitive paths and common secret formats, but cannot prove arbitrary source is secret-free; explicit file selection and host review remain necessary.

API workers cannot access a shell, edit project files or approve output. Candidate text, comments and summaries are untrusted. The host reviews before applying and running checks. Cancellation stops queued work; an already dispatched request can consume quota even if its result is ignored.

State admission is serialized across processes sharing the same state directory. The configured per-run/day limits count conservative request reservations, including queued work later cancelled. These are call-count safeguards, not monetary limits. One request per task is attempted without automated retry or provider failover.

Official references checked on 14 September 2026: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create), [MCP stdio](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), and [ELM's OpenAI-compatible example](https://information-services.ed.ac.uk/computing/elm/elm-competence-centre/examples-of-how-to-use-elm-with-python-and-elm-api-key/interacting-with-elm-using-python-and-the-elm-api).
