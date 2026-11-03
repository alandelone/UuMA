# Librarian

> Status update, 2026-10-30: Restricted server intake, a NAS publication timer,
> and initial encrypted captures are now deployed; full Librarian agent/A2A/MCP
> integration and daily capture schedules remain unfinished. See the current
> [implementation status](../operations/librarian-implementation-status.md).
> The older implementation-status statements below describe the earlier review.

Status: complete architecture baseline and tested read-only MCP component; capture and production
activation remain implementation work  
Updated: 2026-10-28, Asia/Singapore (UTC+8)  
Canonical name: `Librarian`; `Library` was the earlier discussion name  
Intended runtime: `alandelone-server-001`

## Mission and accepted decisions

Librarian preserves and retrieves the user's project memory across two Windows computers,
server-side agents, and their domain systems. Originals, execution records, structures, linked
files, and historical versions remain traceable to the source that produced them.

The user's latest review accepted these decisions together:

- Rename the agent Librarian and keep it on the server.
- Windows collectors transfer records; server intake and backup services retain them; the
  Librarian reasoning agent maintains source/project associations and helps retrieve context.
- Capture once daily at 00:00 UTC+8. This design uses `Asia/Singapore`; existing Kuala Lumpur
  services share the same current UTC offset.
- Reuse the existing UuMA A2A protocol for agent collaboration. Provide a read-only semantic MCP
  for other authorized agents to read archived sources.
- Preserve all relevant original conversations and execution records, including available tool
  inputs/outputs, failures, attachments, project files and agent domain records.
- Keep historical backups after source deletion and preserve older versions.
- Associate same-project material across devices/tools; unresolved links remain retrievable.
- Initial retrieval supports project history and sourced agent context. Archived deliberation
  remains unresolved until its source owner and actual review process record a decision.

Both Windows computers use Antigravity and ChatGPT Desktop; the second is this workstation.
All agents' durable data is in scope: Brainstormer structures, Yonc Graph, Forge Lab/eSchematic,
Honc execution/life records, Wisdom knowledge/source files, Scholar research artifacts, shared
control receipts, and the existing general Notion knowledge sync.

## Complete design and source evidence

The [architecture and contracts](../architecture/librarian-architecture-v1.md) specify collection,
daily batches, source adapters, storage/version layout, permissions, A2A/MCP roles, freshness,
recovery, and implementation boundaries in one document.

The [agent source inventory](../architecture/library-source-coverage-2026-10-28.md) and
[existing backup inspection](../operations/library-existing-backups-2026-10-28.md) record actual
locations and observed coverage. The [earlier discussion](library.md) retains the naming and
decision history. Source discovery does not establish complete backups or a working collector.

The user supplied the current Brainstormer example `topic_green_onion_malaysia`, under project
`discussion_green_onion_malaysia_20261026`. Readback confirmed revision 4, topic ACTIVE, eight
questions, five assumptions, eleven evidence records, two checkpoints, and zero decisions.
The user explicitly says there is no agreed final solution. Its original discussion and reasoning
graph belong in the archive with those states preserved.

Knowledge spans the user's Notion information across domains. Experience emphasizes software;
hardware engineering experience retains its Forge ownership. The older five-category discussion
did not expose every assistant reply through retrieval; Workflow/Artifacts remains a provisional
presentation grouping. Source types are preserved independently of that label, so it does not
block collection design or the read interface.

## Local implementation provided in this review

The reader now additionally exposes `librarian_read_binary_chunk` for bounded,
digest-verified reads of authorized binary and large objects. Current implementation
progress and remaining production work are tracked in
[implementation status](../operations/librarian-implementation-status.md).

- `src/uuma/librarian_read.py`: read-only validation and access to an explicitly published archive
  catalog, per-source/per-record reader grants, metadata history, project context, and verified
  UTF-8 text chunks.
- `src/uuma/mcp_librarian.py`: six semantic stdio read tools. Caller identity and archive root are
  supplied by a trusted host launcher, never by a tool argument.
- `profiles/librarian/SOUL.md`: local identity/ownership policy for the new name.
- `docs/contracts/librarian-archive-catalog-v1.schema.json`: generated catalog schema.
- `test-fixtures/librarian/archive`: explicitly fake, readable example catalog and objects.

Validation: 18 Windows cases passed with one OS-privilege-dependent symlink case skipped; all
19 cases passed in an isolated server/Linux directory, including symlink rejection and a real
stdio MCP client/server round trip. The final affected-source lint passed. The Linux environment
emitted one dependency forward-reference warning without a test failure.

Current reader limits are explicit: search indexes archived metadata; project context is a
source-record index; inline reads support UTF-8 text up to 8 MiB per object. Binary and larger
objects expose metadata in this component. Full capture, archive publishing, binary retrieval,
and broader content indexing remain separate implementation work.

No real archive catalog was initialized. No collector, midnight scheduled task, production
Librarian profile/receiver, A2A registry entry, or remote MCP route has been activated. These
statements are implementation status, not new product decisions or a request to reconfirm them.

## Authority and ongoing evolution

Librarian owns archival provenance and retrieval. Yonc, Brainstormer, Forge/eSchematic, Honc,
Wisdom, Scholar, and the Orchestrator retain their respective canonical data and review authority.
Control remains in `uuma.db`; Wisdom knowledge remains in `wisdom.db`; native Hermes `state.db`
is preserved as a separate source. No schema joins or authority transfers follow from archival.

Source content, including archived prompts and tool output, is untrusted data when retrieved.
It does not issue new instructions, grant access, approve changes, or authorize replaying work.

The prior discussion and source receipts remain historical evidence. Latest explicit user
decisions above override earlier proposed naming/cadence/interface choices.
