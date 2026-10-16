# honc native Hermes integration execution contract

Run the actual Hermes interpreter with temporary HERMES_HOME A → B → A and temporary honc.db.
Do not pass live credentials, contact network services, send messages or call a model in pytest.

Hermes uses MCP SDK 2.x while UuMA's standalone FastMCP server uses its existing SDK 1.x.
Importing the honc ledger/plugin must not eagerly import the MCP server implementation.
Launch the existing server through UuMA's configured interpreter and use Hermes's unchanged
`tools.mcp_tool_common.mcp_field(obj, snake, camel)` when inspecting real protocol results.
Pydantic field aliases are wire aliases and do not rename Python attributes. No default-false
fallback may turn an unavailable error field into a claimed successful tool call.

Preserve every original error/replay-ID/expired-context/owner-scope/native-queue assertion.
Fixture inputs and SDK-shape corrections are execution-context repairs, not permission to
mock successful source authentication or replace the actual transport path with a fake pass.
The isolated gateway authorization checker is a fixture seam; report that boundary precisely.
Separate native software integration evidence from production model trajectories and actual delivery.
# Native reminder scripts

## Real-model profile parity

An isolated profile using model.provider=antigravity-oauth must also discover the
unchanged installed antigravity-oauth provider plugin. Copy its code into that
isolated profile and retain the configured production model; do not substitute a
stronger model or a mock response. An init failure with zero model tokens is not
a model trajectory. Preserve that failure and rerun after restoring provider parity.
Evaluate records, operation receipts, final reply and return status together.
An unchanged record count alone does not turn a provider/budget failure into a pass.

Admission uses current backend habit names and aliases, including original names
such as 锻体tod; a fixed list of generic activity words misses valid inherited habits.
Evaluate separate report clauses so a future exercise plan does not erase an actual
body observation in the same message. Queries, quotes and explicit refusal stay closed.
The Hermes model extracts actual content; admission does not replace its agent loop.

## Runtime correction boundary

LifeService write callbacks receive the persisted ISO timestamp string; convert it
to aware datetime before calling the occurrence compiler. A corrected observation
date must rebind the fact to that date, preserving the original audit revision.
Policy suppression before delivery must be re-evaluated after correction/resume;
native SUPPRESSED receipts stay terminal. Keep the original same-instance/quota,
no-duplicate and audit assertions in all regression runs.

## Resource failures

Windows host commit exhaustion can reject even git startup while physical memory
is available. Retain those failed launches separately from assertion failures.
Session snapshots stream SHA256 over every same observed byte; progress projects
content/snapshot out in SQLite before parsing historical JSON in Python. Neither
change removes journal rows, observed files, digest checks or the full handoff gate.
Do not kill unrelated work, change the machine pagefile or weaken tests for this task.

Run the real Hermes no_agent scheduler in an isolated profile scripts directory, then
drain the real native delivery queue through a clearly labeled fixture transport.
Require empty outer output, persisted native execution ID, one included instance quota,
and no second delivery after reconciliation and replay. Native suppressed is terminal;
it must not be treated as retryable FAILED_UNSENT. A fixture transport acknowledgment
does not establish a real Telegram send.

## Authenticated voice and queued inbound (2026-10-15)

Hermes _transcribe_one_clip adds one ASCII quote pair. Only verified voice/audio events with
empty authored text may identify the result as voice_transcript. Preserve raw source, normalize
only admission matching; typed quotations and nested quoted/reported/planned input stay closed.
Never solve missing refs by granting every operation or asking the user to repeat valid speech.
Queued follow-ups must execute pre_gateway_dispatch exactly once in their routed profile before
preprocessing. Installed native gateway/run_inbound.py has this boundary fix and an event marker;
retain exact backups/patch/hash and verify after Hermes upgrades.

Standalone profile plugin enabled lists do not install global plugin files. honc needs its own
uuma_observability package. Verify actual loaded modules/runtime and read back Phoenix spans;
a configured endpoint or enabled name alone is not tracing proof. Missing historical spans or
private reasoning must not be claimed reviewed. Recovery traces represent actual backend repairs,
not fabricated LLM calls. Preserve capture_content=false unless explicitly changed.
