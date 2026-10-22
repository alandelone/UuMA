# Wisdom-Oldman Telegram progress queries

2026-10-20: user requested applying the Brainstormer-style Telegram operation to Wisdom-Oldman,
specifically for checking progress. Scope is read-only queries, without topic switching, new
research, pause/resume, or changing research routes.

- `/wisdom`: command guide.
- `/topics [page]`: saved research topics, eight per page, with detail commands.
- `/progress`: latest 100 research tasks, status counts and recent tasks.
- `/progress <topic name or ID>`: topic status, document version, task states and stop reasons,
  question states, and the saved research document link.

These commands run deterministically without a language model. Native Hermes command authorization
applies. The plugin is registered only for `wisdom-oldman` and reads semantic MCP tools
`knowledge_topic_list`, `knowledge_topic_get`, and `knowledge_orbit_list` on `wisdom-knowledge`.
It never calls intake, research, route-binding, pause/resume, or budget mutation tools. It reads
the existing Wisdom backend, not Brainstormer's discussion-state storage. Data remains in
the existing `wisdom.db`; no schema change or Hermes `state.db` access was introduced.

Names resolve exactly first, then uniquely by substring. Ambiguous names return IDs for selection.
Missing topics remain missing. Errors and truncated receipts are shown as failed reads, not zero
progress. Topic enumeration is bounded to 500; known `topic_` IDs can be queried directly. Queries
do not imply that an ACTIVE topic has a currently running background task: task states are separate.

Cold commands can precede the first model turn. If Hermes reports that the knowledge server is not
connected, the plugin calls Hermes' scoped MCP discovery for **only** `wisdom-knowledge`, then retries
the same read via `ctx.call_mcp` and its existing permission gate. Async command handlers offload
blocking reads to a worker thread so Telegram's event loop is not blocked.

Deployment: `scripts/deploy-wisdom-commands.py` saves raw config/prior plugin backups, installs
`integrations/hermes/uuma_wisdom_commands`, grants that plugin only the knowledge MCP server,
and prioritizes the three commands in Telegram's menu. Model and MCP server configurations
are preserved. `scripts/sync-wisdom-telegram-menu.py` publishes and reads back the menu without
chat messages or getUpdates polling. Evidence and backups are under
`.uuma-local/wisdom-progress-20261020/`.

Verification: seven focused tests passed, covering profile isolation, allowed read tools, ambiguity,
missing names, pagination, error/truncation handling, cold connection setup and raw config backup /
model preservation. Installed handlers were loaded in a fresh Hermes process and successfully
read actual topics and task progress via the real MCP connection. All three Telegram menu scopes
were published and read back; no chat messages or research tasks were created by verification.

Activation limit: the already-running gateway had an active agent; its control pipe did not answer
the safe reload probe. It was not force-stopped. The plugin and menu are installed, but registration
in that existing process is unverified until a normal gateway reload/restart. No claim is made that
a Telegram user-message round trip was tested. Other profiles and their active work were preserved.

## 2026-10-20 output layout revision

The user supplied a screenshot of `/progress` with five historical tasks, repeated English
objectives and long raw errors/Windows paths, and asked for a clearer output style.
The revised view starts with whether research is actually running/queued, then a compact count
line, then separate current / needs-attention / historical sections. Each task has a number,
short title, status and a plain-language reason. Known miscreated progress/error-payload tasks
are explicitly labeled as historical mistakes; no research record is deleted, merged or changed.
Known boilerplate objectives are shortened; unknown titles retain their source wording.

Raw diagnostics are excluded from the overview and remain available through
`/progress detail <number>`. `/progress page <number>` lists additional records beyond the first
eight. Numbers refer to the current fetched list, ordered by status group and then update time;
details include the durable record ID for identification. Detail queries are read-only.
Topic detail queries use the same concise reason summaries. Unknown technical errors are not
invented or translated into an unsupported diagnosis: the user is directed to the original record.

Eleven focused tests passed, including the screenshot's exact five task/error patterns,
preservation of raw records, detail availability, active/history ordering and paging. The actual
installed plugin was exercised against the real backend: the revised overview is 303 characters
for those five tasks, with no raw logs/paths. Raw plugin backup, preview and verification receipt:
`.uuma-local/wisdom-style-20261020/`. Profile configuration is byte-for-byte unchanged.

The updated output was installed before reloading the existing gateway. The reload probe found
zero active agents and received an already-stopping acknowledgement; after shutdown, the existing
`Hermes_Gateway` task was started. Final live connection evidence is saved in that same folder's
`live-gateway.json`. No Telegram test messages were sent.
