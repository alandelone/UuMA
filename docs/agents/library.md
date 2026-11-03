# Library — historical discussion baseline

The user renamed this agent **Librarian** on 2026-10-28. The current canonical record is
[Librarian](librarian.md), with the complete
[architecture and read-only MCP contract](../architecture/librarian-architecture-v1.md).
This file preserves the earlier discussion and evidence; latest explicit naming, daily-midnight
cadence, and A2A/read-MCP decisions are recorded in those current documents.

Status: discussion baseline; implementation and deployment remain future work  
Last updated: 2026-10-28, Asia/Kuala_Lumpur  
Intended runtime: server side; service and storage layout remain proposed  
Primary role: preserve and retrieve project memory across Windows computers and agent domain systems  
Sources: [Agent memory discussion](https://chatgpt.com/c/6ae14601-5608-83ec-ae5a-b6a5af1fee39)
and the user's Library clarification in this UuMA chat on 2026-10-28.

## 1. Mission and confirmed requirements

Library is the proposed keeper of the user's project memory. It preserves original records,
connects them to projects, and helps the user and authorized agents recover relevant context
across computers and tools. Preservation proceeds before optional interpretation or knowledge
extraction.

The user's long-term aspiration is to back up everything relevant. The user explicitly confirmed
the first-stage scope: **agent conversations, development history, and project files from both
Windows computers**. This scope does not imply a complete operating-system image.

The user subsequently expanded the scope to **all agents' durable data**, explicitly including
the entire Brainstormer structure, Yonc Project Graph, and Forge Lab item/event information.
The Windows history scope remains included. See the
[agent source coverage inventory](../architecture/library-source-coverage-2026-10-28.md).

| Requirement | Confirmed user intent |
| --- | --- |
| Name | Use `Library` as the working agent name; the earlier librarian description explains its role. |
| Runtime | Deploy on the server in a later implementation phase. |
| Organization | Project-centric; investigate the existing Project Graph as an identity anchor. |
| History | Preserve conversations and development processes from both Windows computers and different coding agents. |
| Content completeness | Confirmed: preserve all relevant records, including all execution records, original conversations, tool records, and related artifacts available from their sources. Record unavailable content explicitly rather than replacing originals with summaries. |
| Agent domain coverage | Confirmed: include all agents' durable structures and records, with databases, relationships, source/artifact files, history, proposals/reviews, and receipts. Brainstormer, Yonc and Forge are explicit examples; inspect other agents too. |
| Historical retention | Confirmed: keep historical backups when a source tool deletes records; preserve old versions rather than only a current mirror. |
| Project association | Accepted: associate same-project records across computers/tools and keep uncertain associations in a retrievable inbox. |
| Initial retrieval | Accepted: sourced project-history search, earlier development context/failures, and relevant context for other authorized agents. |
| Responsiveness | Backup must not hold up normal work; preservation and later organization need separate paths. |
| Collection direction | Accepted on 2026-10-28: a lightweight background collector on each Windows computer sends supported records to server-side Library, with initial backfill and resumed transfer after disconnection. Implementation details remain open. |
| Existing systems | Build on existing NAS backup arrangements and Notion synchronization where compatible. Complete coverage has not been audited here. |
| Knowledge | Include information already organized in Notion, across domains rather than software alone. |
| Experience | Emphasize reusable software-development experience; hardware engineering memory already has a separate home. |
| Decision process | Preserve ongoing deliberation as well as eventual decisions. The user identified the current Brainstormer green-onion topic as the example and explicitly said no final solution has been agreed. Broader future Life context remains to design. |
| Collaboration | Let other agents retrieve relevant memory; a semantic tool interface was discussed previously. |
| Current phase | Discuss and maintain the existing design document library as decisions become clear. |

These are product requirements. Mechanisms below are proposals unless explicitly marked confirmed.
This document creates no profile, service, collector, production registration, or deployment.
The repository mission gate remains governed by `mission_status.json`.

## 2. Memory categories and source limits

The referenced conversation explicitly discusses five categories. Retrieved user turns establish
Knowledge, Experience, Decision, and History, and also mention workflow/artifact-like material.
The retrieved older assistant replies contain content-reference placeholders rather than readable
bodies. The remaining category's exact historical name therefore cannot be verified from this
retrieval. This table is a working proposal, not a verbatim recovery of the earlier five-item list.

| Working category | Content and scope | Preservation boundary |
| --- | --- | --- |
| Knowledge | Curated concepts, references, and notes, including Notion information across domains | Keep source pages, revisions, and provenance; coordinate with Wisdom for accepted knowledge. |
| Experience | Software debugging lessons, failed approaches, environmental conditions, and solutions | Extract candidates from original history with applicability and evidence. Hardware lessons stay with Forge. |
| Decision | Questions, alternatives, assumptions, evidence, deliberation, checkpoints, and any eventual reviewed choice, conditions, or reversal | Preserve distinct source types and unresolved status. A discussion can be archived before any decision exists. |
| Workflow / Artifacts — provisional label | Reusable procedures plus code, specifications, reports, patches, tests, and other outputs | Keep procedure and artifact record types distinct even if presented together. Confirm this category's name and grouping later. |
| History | Original conversations, development events, run records, handoffs, and file versions | Preserve originals and known order; derived summaries and lessons link back to them. |

One conversation can support a decision, an experience, and an artifact. Keep those relationships
explicit rather than flattening different record types into undifferentiated memory.

### Current Brainstormer example: an ongoing decision process

The user's screenshot identifies `topic_green_onion_malaysia`, titled in the source
“马来西亚青葱种植计划：每月至少赚 RM10,000”, under project
`discussion_green_onion_malaysia_20261026`. A fresh server read on 2026-10-28 confirmed the
topic and active navigation binding. Project revision 4 contains eight questions, five
assumptions, eleven evidence records, two checkpoints, and **zero decision records**; the topic
status is `ACTIVE`.

The user explicitly clarified that there is no agreed final solution. The income objective in
the title, saved discussion state, and checkpoints do not establish an approved farming plan.
Library should preserve this continuing reasoning process with its original unresolved status.

The user may later build on Brainstormer's architecture. Library's archive may therefore follow
its project/topic/question/assumption/evidence/checkpoint/decision relationships and source
versions. This is a direction to explore, not an approved new schema or completed integration.
Brainstormer retains reasoning and review ownership; Library preserves and retrieves the records.
Backing up a checkpoint does not create, approve, or complete a decision.

Verified structured record:
`/home/alandelone/.local/share/uuma/production/brainstormer/brainstormer/projects/discussion_green_onion_malaysia_20261026/state.json`.
Native conversations and tool records remain a separate source in the Brainstormer profile's
`state.db`; preserve both. See [the inspection update](../operations/library-existing-backups-2026-10-28.md).

## 3. Project identity and navigation

Proposed approach: reference stable project identities exposed by the existing Yonc Project
Graph. Library owns its catalog and source associations; the Yonc backend keeps ownership of
accepted project structure and state.

- A project may span repositories, directories, tools, and computers. A local folder path alone
  is insufficient as a global identity.
- Records can belong to several projects. Personal/Life or unresolved material can remain in an
  explicit inbox until a justified association is available.
- Preserve original host, path, tool, session, timestamps, and source revision separately from
  Library's project association. Association changes retain history.
- Project renaming, merging, archiving, or removal must not rewrite or discard original records.
- Audit actual Graph identifiers and read interfaces before implementation. This discussion
  accepts no Graph schema change or automatic creation of projects.

Example: conversations in two coding tools on different computers can both reference UuMA.
Library shows their histories together while retaining each original tool and computer identity.

## 4. Preservation without delaying work

Accepted collection direction, with storage and operational details still to design:

```text
Windows A -- local capture / durable pending records --+
                                                      +--> server intake and receipts
Windows B -- local capture / durable pending records --+            |
                                                         retained originals
                                                                   |
                                                       NAS versioned backup / recovery
                                                                   |
                                             background cataloging and project retrieval

Existing Notion material -- scoped sync adapter --> catalog with source provenance
```

Exact transport and storage topology remain open. Normal development should not wait for
network delivery, NAS availability, Notion, an LLM, or indexing. Local capture still has measurable
overhead; acceptable latency, CPU, disk, and bandwidth budgets need definition and measurement.

Proposed behavior:

1. Capture originals with minimal metadata into durable local pending work. Classification and
   summarization are not prerequisites for preservation.
2. Transfer incrementally in the background and resume from acknowledged progress after restart
   or disconnection. Repeated delivery does not invent another source event.
3. Distinguish locally captured, server received, backup verified, and indexed states. Upload
   receipt alone proves neither verified backup nor successful recovery.
4. Throttle bulk scans and large transfers separately from small conversation increments. Expose
   pending counts, oldest pending age, failed sources, and incomplete coverage.
5. When capture fails or local storage fills, surface degraded coverage. Never silently drop
   pending records or claim complete preservation.

The user accepted the per-computer background collection and server intake direction after
reviewing the transfer explanation. Detailed queue, acknowledgment, and storage contracts remain
to design. No numeric backup lag target or zero-loss guarantee has been agreed.

## 5. Two-computer history, files, and continuity

Inventory each computer's agent tools, supported exports or local history stores, workspace
locations, and inclusion rules. Distinguish accessible content from metadata-only or unavailable
sources. A cloud conversation URL is not a transcript backup; actual source content is required.

### Initial source inventory — user clarification, 2026-10-28

| Item | What is known | Still to verify |
| --- | --- | --- |
| Windows computer 1 | The other Windows computer; uses both Antigravity and ChatGPT Desktop. | Its identity, project roots, source accessibility, and connection to the existing backup. |
| Windows computer 2 | The current workstation where this discussion is taking place. | Its project roots and existing backup coverage. |
| Antigravity | The user confirmed use on both Windows computers. | Where actual conversations, runs, and artifacts can be obtained on each computer. |
| ChatGPT Desktop | The user confirmed use on both Windows computers; it is also the current desktop application named by the user. | Which history is available from local data or supported account/export interfaces. |

The user's later clarification resolves per-computer tool usage: both computers use both tools.
Do not assume either tool's data location, automatic export capability, or that the two tools
share a session store. For any Codex work surfaced through ChatGPT Desktop, inventory
its actual source separately from ordinary ChatGPT conversations when applicable. Associate
available originals from both tools with the same project while retaining source identity.
Coverage and automatic ingestion must be verified per source before being claimed. The first
read-only source/backup inspection is recorded in
[the existing-backup inspection](../operations/library-existing-backups-2026-10-28.md).

Proposed record identity combines stable source/computer identity, tool identity, original
session or record ID, revision, and content digest. Identical content can share stored bytes while
retaining every source occurrence. Shared NAS mounts need one explicit shared-source identity;
two paths to the same live directory are not two independent backups.

Keep source and ingestion timestamps separately, preserve known per-source order and causal
links, and avoid inventing precise global order from different computer clocks. Conflicting file
versions remain recoverable variants rather than overwriting one another by upload order.

Project-file preservation should include working changes and untracked material under the
eventual inclusion policy, not only Git commits. Dependencies, build outputs, caches, large
binaries, credentials, and private configuration need explicit handling rules. Live databases
require source-owner-consistent snapshots rather than arbitrary copies omitting journal data.
Exact paths, adapters, retention, encryption/access policy, and resource budgets remain open.

Two outcomes need separate validation:

- **Recovery:** restore selected original conversations and project files with verified contents.
- **Continuity:** from either computer, retrieve project context, previous failures, decisions,
  current handoff, and original records.

Neither requires merging live application sessions or synchronizing tools' internal databases.
An agent can receive a sourced context package without sharing every other agent's runtime chat.

### Connecting the other Windows computer — accepted direction and proposed setup

The user does not yet know how the other computer would send records to Library. Treat this as
a setup and collection design problem; the user need not identify every internal data directory
to continue discussing the product.

Accepted responsibility split: Library runs on the server and receives, preserves, and catalogs
records; a small background collector on each Windows computer discovers and transfers supported
local sources. Routine copying and transfer do not require another reasoning agent or an LLM.
Server deployment alone cannot capture local-only files on an unconnected or powered-off computer.

1. Prepare a repeatable connection package after the server intake and source adapters exist.
   On each computer, run a one-time setup that pairs its distinct device identity with Library.
2. Inspect the named tools and project locations on that computer. Present discovered sources
   and coverage for selection; identify unsupported history or export requirements explicitly.
   No specific Antigravity or ChatGPT Desktop extraction capability has been verified yet.
3. Preserve existing accessible history in a throttled initial backfill. Give newly captured
   changes their own processing capacity so a large old archive does not delay current records.
4. Let each computer send its queued increments directly to the server. The second computer
   does not have to stay on for the first computer to upload, and vice versa. Whether remote
   access requires an existing private connection is a later network configuration decision.
5. If a computer is offline, retain durable pending work locally; resume when it reconnects.
   Library reports each computer's last contact, received progress, verified backup progress,
   and gaps. A powered-off computer is not presented as providing fresh coverage.
6. Retain local pending originals until their transfer is acknowledged. Local queue cleanup
   and source retention remain separate from NAS backup verification and recovery policy.

Actual source files remain under their applications' ownership. This direction does not make
both computers open or write a shared live application database. Existing NAS backup transport
may be reused if its scope and guarantees match; no collector or connection has been installed
by this discussion.

## 6. Existing facilities and ownership

### Complete agent structures and domain data

Library's source inventory extends beyond coding-assistant exports. Read-only inspection located
Yonc's active `project_graph.sqlite3`, Forge's `lab.db` and separate eSchematic catalog, Honc's
`honc.db`, Wisdom's `wisdom.db` plus source content, UuMA's server control database, and the
workstation Scholar catalog/artifact/writing directories. All five server specialists also have
separate native profile history.

Preserve every relevant source type and link: complete Brainstormer reasoning graphs; Graph
nodes/edges and assignment/review history; Lab inventory/order/build/engineering events; life
and execution ledgers; knowledge/evidence/patch history; research artifacts; and cross-agent
execution receipts. Preserve related files alongside databases and keep domain ownership distinct.
Exact verified paths, schema families, supporting stores, and remaining coverage gaps are in the
[agent source coverage inventory](../architecture/library-source-coverage-2026-10-28.md).

The user's Forge item example spans eSchematic component definitions and Lab physical records;
it does not authorize merging their schemas or treating purchase history as stock. Current
source discovery is not proof that these sources already have complete backups.

### Existing integration evidence

| Facility | Repository evidence | Library consequence |
| --- | --- | --- |
| Agent document library | `docs/agents/README.md` consolidates design conversations and specifications | Add this discussion to that archive and its index. |
| Yonc Project Graph | Yonc's backend owns canonical project structure | Reference identities through semantic interfaces and preserve ownership. |
| NAS workspace | Forge's Windows `Z:/Hardware-Lab-Workspace` and server `/mnt/nas/Hardware-Lab-Workspace` are the same live directory | Shared storage alone does not establish independent backup versions, retention, or recoverability. |
| Assistant history backups | Read-only inspection found `Z:/backups/ai-assistants-history`, existing backup scripts and original Codex/Antigravity records. Main status is dated 2026-10-23; `devices` is empty. | Reuse this real layout and mappings; independent device coverage, complete project files, consistent snapshots, and historical versions need further design. |
| General Notion knowledge sync | A separate `/home/alandelone/services/notion-sync` service syncs integration-visible pages nightly; 1,674 pages and seven dated NAS DB backups were observed. | Integrate this existing knowledge source. Its current-value page cache and rolling backups do not themselves provide complete historical versions. |
| Forge Notion relay | Forge also has its own restricted server relay and journal consumer. | Preserve that separate identity/scope; do not confuse it with the user's general Notion knowledge sync. |
| Brainstormer decision-process context | The user's screenshot identifies the existing green-onion topic, now matched to the active server record. No final solution has been agreed; zero decision records are present. | Preserve deliberation and structured reasoning alongside raw history. Future broader Life organization remains open; no separate Life database is inferred. |

Library owns proposed archival intake, catalog, provenance, recovery status, and context retrieval.
Brainstormer retains discussion/convergence; Wisdom retains knowledge formation and review;
Forge retains hardware memory; Yonc retains project management; existing decision owners and
the user retain decision authority. Preservation does not turn a record into accepted knowledge.

Control stays in `uuma.db`, Wisdom knowledge in `wisdom.db`, and Hermes `state.db` is not
repurposed. Future Library storage requires a distinct ownership design; do not merge or join
these schemas. Preserve corrections through supersession or compensating history.

## 7. Retrieval and restoration

Proposed semantic capabilities: find project history, retrieve an original record, assemble
sourced project context, inspect backup coverage, and prepare a recovery preview. These are
concepts, not installed tool names. Retrieval reports sources and freshness, distinguishes
originals from summaries and accepted decisions from suggestions, and enforces caller scope.
Archiving a record does not grant every agent access to it. Extracted software lessons remain
candidates until the applicable review process accepts them.

A recovery preview identifies source versions, destination, conflicts, and expected changes.
Actual restoration uses a separately authorized execution path that preserves later writes.
This discussion authorizes no restoration or modification of source applications.

## 8. Next discussion and future acceptance

The first scope question is resolved: conversations, development history, and project files
from both Windows computers. The second computer is this workstation, and both computers use
Antigravity and ChatGPT Desktop. The user's current concern is how the other computer sends
records to Library; the accepted collection direction above addresses that setup path. Next audit
supported source access, project roots, server connectivity, and existing backup transport.
Then refine:

1. The original fifth category's name and the relationship between workflows and artifacts.
2. Future Life/decision organization beyond the identified Brainstormer example, Notion collections,
   and synchronization direction.
3. Stable project associations, unresolved records, and read access to Project Graph.
4. Acceptable overhead and backup lag, retention, storage, and access boundaries.
5. Context/recovery surfaces and exact server topology.

### Remaining product choices and implementation evidence

On 2026-10-28 the user accepted the collection direction and subsequently settled content scope,
historical retention, project association, and initial retrieval. The core role and scope are
clear enough to develop the next design. Status after those decisions:

| Area | Recommended starting point | Still to decide or verify |
| --- | --- | --- |
| Preserved content | Accepted: all relevant original records and execution history, including available attachments, tool records, failures, handoffs, and project-file versions. | Verify source access, actual completeness and file roots; preserve access boundaries around retained material. Tool inspection is not selective summary retention. |
| Project association | Accepted: link same-project records and keep unresolved/cross-project material retrievable. | Exact Graph identifiers and review mechanics; the still-provisional fifth category name. |
| Retention and deletion | Accepted: keep historical backups after source deletion and retain previous versions. | Storage/version format, capacity policy, and explicit Library deletion/recovery procedure. Rolling-current copies do not satisfy the accepted history requirement. |
| Retrieval and reuse | Accepted: sourced project-history search and relevant context retrieval by authorized agents, with originals preserved beneath summaries. | User surface and later automatic software-lesson extraction. |
| Sync and source ownership | General Notion sync and Brainstormer storage are located; the screenshot's topic is matched. Keep ingestion separate from publishing or accepting decisions. | How Library versions existing Notion and Brainstormer sources, and any later broader Life organization. |
| Backup confidence | Show each computer's coverage, backup lag, failures, and verified recovery evidence. | Measure acceptable impact/lag; inspect existing NAS transport and demonstrate a selected restore. |

Source adapters, actual available records, NAS coverage, and network connectivity are engineering
investigations; the user need not supply internal paths or exact service settings now. The user
requested and received a read-only initial inspection of the existing NAS assistant backups,
general Notion sync, and Brainstormer stores; see
[the inspection findings](../operations/library-existing-backups-2026-10-28.md).
Version/storage details, explicit Library deletion, user surface, and automatic curation remain
to discuss. No installation or server publication is authorized in this discussion phase.

Future acceptance should demonstrate actual content from both computers, disconnected capture
and restart recovery, duplicate-safe delivery, recoverable conflicting versions, retained
originals beneath summaries, measured impact during development, and a selected restore with
verified bytes. Expose gaps rather than inferring coverage from a healthy process or empty queue.
These are future goals, not test results or deployment evidence.

Implementation planning and server publishing follow the
[agent development and release runbook](../operations/agent-development-and-release.md)
once discussion reaches that phase.

## 9. Sources and change history

- [Agent memory discussion](https://chatgpt.com/c/6ae14601-5608-83ec-ae5a-b6a5af1fee39),
  retrieved using the app's conversation reader: five user turns readable; older assistant
  replies were reference placeholders. Unavailable assistant content is not asserted here.
- User discussion and explicit first-stage scope answer in this UuMA chat, 2026-10-28.
- [Agent Design Archive](README.md), [Yonc](yonc.md), and [Honc](honc.md).
- [NAS workspace](../operations/forge-nas-workspace.md),
  [Forge Notion server sync](../operations/forge-notion-server-20261023.md), and
  [agent publishing](../operations/agent-development-and-release.md).
- 2026-10-28: initial baseline added and first-stage coverage confirmed. Taxonomy, integration
  owners, adapters, storage, and deployment details remain open as marked above.
- 2026-10-28: user clarified both computers use Windows, the second is the current workstation,
  and named Antigravity and ChatGPT Desktop as tools; per-computer use was initially unresolved.
- 2026-10-28: user confirmed both tools are used on both computers and raised how the other
  computer sends records. Added a proposed one-time pairing and per-computer background collection
  workflow. Actual source access and network setup remain unverified; this is not deployment.
- 2026-10-28: user accepted the per-computer collector/server intake direction and asked about
  remaining gaps. Recorded acceptance and a proposed product/evidence checklist, without treating
  retention, deletion, automatic curation, adapters, or deployment as approved.
- 2026-10-28: user confirmed all relevant records/execution records, required historical backups,
  and accepted project association and initial retrieval. They directed inspection of existing
  NAS Backups, assistant-history batch scripts, general Notion sync, and Brainstormer-owned Life/Live
  records. Linked actual read-only findings; previously open product choices above now reflect
  these decisions. General Notion sync is distinct from Forge's relay; exact Life/Live identity
  remains unresolved. No backup or service was changed.
- 2026-10-28: the user supplied a screenshot identifying the latest green-onion Brainstormer
  discussion and explicitly stated there is no agreed final solution. Fresh server read matched
  its topic/project and ACTIVE binding, revision 4, with zero decision records. This resolves
  the current discussion reference without inventing a separate Life system. Decision memory
  includes ongoing reasoning before a choice exists; future use of Brainstormer's architecture
  remains a design direction. No production record was edited.
- 2026-10-28: user expanded coverage to all agents' durable data, explicitly complete Brainstormer
  structure, Yonc Project Graph, and Forge Lab item/event records, and requested inspection of
  other agents. Added a source coverage inventory based on read-only server/schema and bounded
  workstation inspection. Windows history remains included; no backup activation or data
  ownership change occurred.
