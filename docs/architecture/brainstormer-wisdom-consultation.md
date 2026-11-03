# Direct Brainstormer to Wisdom knowledge consultation

Status: published to the server on 2026-10-26 after explicit user approval. Runtime imports,
MCP tool discovery, scoped access and service health are verified. Live consultation acceptance
is recorded separately in `../operations/brainstormer-wisdom-consultation-20261026.md`.

## Roles and information flow

Brainstormer frames the business/design question, supplies its bounded relevant context and
source references, and integrates the answer. Wisdom owns knowledge retrieval, located evidence,
qualification of the answer, and retention of unresolved questions. A future separate Brainstormer
critic checks how that evidence supports a proposal. A consultation does not implement that critic.

```text
Active Brainstormer discussion/run
  -> brainstormer_ask_wisdom
  -> authenticated control registration of one Wisdom child
  -> existing A2A SendMessage -> Wisdom runtime
  -> cited answer or saved unanswered question/research handle
  -> structured result -> Brainstormer status lookup and synthesis
```

The control plane mediates identity and receipts without requiring the Orchestrator conversational
agent to forward each question. No new general worker coordination capability is granted. The
only direct edge is Brainstormer -> Wisdom; there is no reverse-delegation or recursive agent loop.

## Request and receipt

`KnowledgeConsultationRequest` binds the current parent run and epoch, project/topic, question,
purpose, bounded context, source references, research choice and idempotency key. Brainstormer's
MCP checks that the topic has saved objects. The server requires an enabled requester/responder,
open intake and a current RUNNING Brainstormer parent. A bound parent project must match.

The control broker builds the fixed Wisdom task server-side. One transaction writes existing
TASK_CREATED, TASK_ASSIGNED and RUN_REGISTERED events; no control SQL schema is added. Task and
run source gain the explicit `consultation` value. General worker run registration, task assignment
and Orchestrator-only control endpoints keep their prior permissions. Repeat keys must match all
original input. Existing receipts do not recreate, resume or supersede work.

The bounded request is retained in an `x-uuma-knowledge-consultation` JSON Schema annotation on
the task output schema. This uses existing immutable task contracts, not a new knowledge table or
an extra default TaskContract field that would invalidate old idempotency hashes.

`brainstormer_ask_wisdom` dispatches the registered pending child over the administrator-bound
Wisdom endpoint using Brainstormer's own identity. A2A permits Brainstormer only on Wisdom paths;
dispatch additionally requires the fixed consultation contract and current parent epoch. Generic
dispatch/cancellation and global receipt access remain unavailable to Brainstormer. Existing A2A
dispatch reservation handles ambiguous outcomes without blind runtime resubmission.

`brainstormer_wisdom_status` can read only this class of consultation. The result remains readable
after its parent finishes. Receipt reads do not initiate research or relaunch an execution.

## Answers and unanswered questions

Wisdom submits `partial_state.consultation` with a bounded structured answer:

- ANSWERED requires located citations and no remaining material question.
- PARTIAL includes the usable answer and remaining gaps.
- PENDING_RESEARCH includes a durable question or research reference; a promise is insufficient.
- NEEDS_INPUT and BLOCKED explain the missing input or dependency.

Only ANSWERED can accompany a COMPLETED outcome. Submission still goes through normal result
review and does not accept a claim or a Brainstormer decision. Citation shape validation proves
neither scientific correctness nor source relevance; those remain Wisdom and review duties.

By default `research_if_unknown=false`: preserve the unanswered question and return its reference.
An explicit request to research can set it true and use Wisdom's existing governed research tools.
For incomplete replies, Wisdom's worker `submit_result` now saves a stable per-consultation root
question, bounded child questions and a gap through the configured Wisdom semantic MCP, and reads
each actual record back before submitting. It verifies the current assigned run before any save.
It uses no raw knowledge database API. A failed save/readback blocks result submission; repeated
submissions reuse the same verified records. The original model response is retained separately,
and machine-verified question/gap references replace unverified model-supplied retention references.
This guarantees retained questions in this worker path; it does not validate scientific claims or
make the multi-owner save/submission an atomic transaction. Records can remain when a later result
submission fails, and are safely reused. Direct HTTP result calls do not acquire this MCP guard.
Existing topic approval, paused/stopped Orbit, provider quota, canonical review and reversal rules
remain in force. This implementation provides a consultation reply handle, not automatic Telegram
push or a new background research scheduler. New research can outlive the consultation; its saved
handle/document is the progress reference. A later bounded consultation can ask for updated findings.

## Current Notion access evidence

On 2026-10-26, the actual server Brainstormer `notion_kb` SSE binding initialized as
`notion-knowledge-store` and exposed search_pages, get_page, list_pages and get_sync_status.
The directory contained 1,674 synced pages. A business search returned two hits and a matching
page read returned 641 characters without an MCP error. Latest recorded sync finished at
2026-10-25T19:22:45Z (2026-10-26 03:22 Asia/Kuala_Lumpur), with 63 updates and zero errors.
These are real access checks of the synced store, not proof that every Notion page is shared or
that a fresh upstream API read occurred for each request. No Notion content was changed.

## Manual publication boundary

Follow `../operations/agent-development-and-release.md`. Local changes are not production changes.
Publish the compatible control source, A2A source, worker source and role/skill definitions together;
merge the two tool additions in `deploy/brainstormer/wisdom-consultation-tools.json` with the current
Brainstormer allowlist. Preserve existing tools, provider-pool paths, Wisdom daily-quota component,
databases, user pauses and all unrelated profile changes. Same-named cached MCP processes need a
verified scoped refresh; editing YAML alone does not replace them.

Before applying, record the current actual component source hashes, service environment references,
active tasks, backups, exact new content manifest and rollback. If a gateway restart is necessary,
all five specialists are affected and must be included in the maintenance preview. Do not interrupt
active work or replay historical jobs. Rolling back code after consultation events exist must retain
a reader for the new source value; never restore an older database over later writes.

The compatible production release is
`f68069659e53bca5877dba472d6ac711e2a4728f23ffcd2313df32f75a278753`.
The release was verified with 41 isolated server checks before publication. After publication,
the real Brainstormer MCP dispatched one consultation using its own identity; the actual Wisdom
runtime accepted it. The operation receipt distinguishes dispatch from a returned answer.
Separate actual owner-MCP verification proved three retained records and stale submission rejection.
Two incorrect model retention claims and one stalled additional model run remain in the receipts;
none is used as proof of successful persistence or scientific completion.
