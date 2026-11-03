# Librarian agent discussion — 2026-10-28

Canonical design record: [Librarian](../docs/agents/librarian.md).

## Latest combined review and implementation

The user renamed Library to **Librarian**, confirmed server-side residence and responsibility
split, set capture to **00:00 UTC+8 once daily**, and chose existing A2A plus a read-only MCP for
agents. They requested the complete design together, not another sequence of scope questions.
Timezone recorded as Asia/Singapore under current client context; Kuala Lumpur services have
the same current offset. Offline continuations keep daily batch identity; no extra scheduled
capture or hidden continuous watcher. Notion remains on its existing 03:00 sync, so midnight
archive freshness must disclose the last available source sync.

Complete design: [architecture v1](../docs/architecture/librarian-architecture-v1.md).
Local read component `librarian_read.py` plus `mcp_librarian.py` now provides six stdio semantic
read tools over an explicitly published archive catalog, scoped by trusted host identity and
source/record grants. It creates no archive, queries no live domain DB and installs no schedule.
Binary/large objects are metadata-only in v1; search/context use metadata indexes. Actual source
collectors and publishing are not implemented by this component.

Validation: Windows18 passed/1 symlink-privilege skip; server/Linux19 passed including symlink
rejection and a real MCP stdio round trip. Final lint passed; initial two lint findings were
corrected without changing assertions. Source bytes matched the isolated server fixture. One
Linux dependency warning retained. Evidence under `.uuma-local/librarian-implementation-20261028`.
No production profile/A2A registration/MCP binding/collector/nightly task or NAS archive activated.
The latest request authorizes the read component and consolidated architecture; earlier
discussion-only statements below describe their historical context, not an undone decision.

The user requested discussion and incremental documentation of a new server-side agent named
Library, based on [Agent memory categories](https://chatgpt.com/c/6ae14601-5608-83ec-ae5a-b6a5af1fee39).
This request is a design discussion, not an implementation or publication request.

## Confirmed

- Project-centric memory, with existing Project Graph as a possible identity anchor.
- First-stage scope explicitly confirmed: agent conversations, development history, and project
  files from both Windows computers.
- Both computers are Windows; the second is the current workstation. The user subsequently
  confirmed BOTH Antigravity and ChatGPT Desktop are used on BOTH computers. Actual source
  locations/access methods remain to be verified; do not assume one common history store.
- The user is unsure how the other computer would send records to Library. Solve setup and
  collection without requiring the user to know internal data paths before discussion continues.
- After reviewing the explanation, the user accepted the per-computer lightweight background
  collector and server-side Library intake direction. This is design acceptance, not installation
  or publication authorization. They then asked what else needs to be added.
- Preserve broadly without delaying normal work. Separate preservation from later indexing,
  classification, summarization, and knowledge extraction.
- Use existing NAS backup arrangements and Notion synchronization where appropriate.
- Knowledge spans Notion information across domains; Experience emphasizes software.
  Hardware engineering experience already belongs to a separate system.
- Link decisions to projects and existing Life context; exact Life integration remains open.
- Maintain the existing Agent Design Archive as discussion becomes clear.
- Latest user decisions: preserve all relevant original and execution records; retain historical
  backups after source deletion; accept same-project association with unresolved inbox and
  sourced project-history/context retrieval by authorized agents. These are no longer pending.
- User explicitly requested read-only inspection of NAS Backups/assistant-history scripts,
  existing general Notion synchronization, and Brainstormer-owned Life/Live record locations.
- Latest screenshot clarification: the user means the current green-onion Brainstormer topic,
  `topic_green_onion_malaysia`, and explicitly states no final solution has been agreed.
  Preserve ongoing decision processes before a decision exists. Future reuse of Brainstormer's
  architecture is exploratory; do not turn this into schema acceptance or plan approval.
- Latest scope expansion: include all agents' durable structures/data, explicitly complete
  Brainstormer reasoning structure, Yonc Project Graph and Forge Lab item/event records; inspect
  the other agents too. This adds domain data to the accepted Windows history scope. Preserve
  original domain owners and history, and related files, not only database filenames.

## Agent domain coverage

See [source inventory](../docs/architecture/library-source-coverage-2026-10-28.md).

- Server production roots verified for Brainstormer, Yonc, Forge, Honc and Wisdom. Active Yonc
  `YONC_GRAPH_DB` points to `production/yonc/project_graph.sqlite3`; 25 table families include
  nodes/edges, proposals/versions, operations/status, assignment/delivery/review and receipts.
- Forge `production/forge-lab-bot/lab.db` has 20 user tables for physical/domain/journal history.
  Item definitions also live in separate `eschematic/data/catalog.db` (components/aliases/pins).
  Preserve that owner distinction, commerce files, Notion relay receipts, and the live NAS
  Hardware-Lab-Workspace. No literal Lab `items` table was found; do not invent or merge one.
- Honc has 23 execution/life/history table families in `production/honc/honc.db`.
- Wisdom has 36 table families in `production/wisdom-oldman/wisdom.db` plus `wisdom-content`,
  covering evidence/claims/patch events, source files, topic versions and research/Orbit history.
- Server control DB is `/home/alandelone/.local/share/uuma/data/uuma.db`; its contracts/runs/
  events/receipts and referenced artifacts are distinct from domain knowledge.
- All five specialist native profiles have state.db, memories/logs/cron directories under
  `/home/alandelone/.local/share/uuma/pilot/home/profiles/<agent>`. Preserve original chat/tool
  history and domain stores as separate sources.
- Workstation RSTV4 data/catalog.db, data/artifacts and data/writing-studio exist. Scholar live
  rows/jobs/schema were not queried or changed. Exact PDF/FieldKG dependencies, local native
  profile roots, and shared runtime recovery stores remain source-mapping work.
- Inventory receipt: `.uuma-local/library-agent-discussion-20261028/agent-source-inventory-f4b9fc4267494ee597944350a53043a8.json`.
  This is source discovery, not evidence of complete backups, recovery, installation or publication.

## Existing-source inspection

See [verified findings](../docs/operations/library-existing-backups-2026-10-28.md).

- `Z:/backups/ai-assistants-history` exists with original Codex/Antigravity data and batch/Python
  incremental backup tools. Main status is 2026-10-23 20:59:10 (no offset encoded), devices is
  empty, and this workstation had no matching scheduled task or sync process at inspection.
  This does not prove the other machine never wrote to the shared primary destination.
- Existing copying overwrites changed files, uses size/time comparison, and copies live DB
  sidecars separately; it does not establish immutable history or consistent recovery. Project
  scanning copies agent configurations rather than whole project trees. Preserve the existing
  NAS contents; the user asked to inspect and discuss, not run or repair the scripts.
- Correct earlier limited context: the user DOES have a general Notion knowledge sync, separate
  from Forge's journal relay. Server source/DB: `/home/alandelone/services/notion-sync`; daily
  03:00 MYT timer; latest observed run 2026-10-28 checked 1,674 pages, 63 updated, 0 errors.
  Seven dated backups under `/mnt/nas/backups/notion-sync`; latest passed read-only quick_check
  with 1,674 pages. Current-value upserts and rolling seven snapshots are not full revision history.
- Brainstormer native records: `/home/alandelone/.local/share/uuma/pilot/home/profiles/brainstormer/state.db`;
  structured state: `/home/alandelone/.local/share/uuma/production/brainstormer/brainstormer/projects`;
  also preserve proposals, navigation.db, memories and logs as separate record types. Native DB
  had 17 sessions/159 messages; profile sessions directory was empty. No independently named
  Life/Live project was identified in the initial search. The later screenshot resolves the
  current reference to the existing green-onion discussion, not a separate Life system.
- Neither inspected Windows history script nor current server daily_backup.sh covers those
  Brainstormer paths. No recurring current backup was verified; historical/manual snapshots
  and disaster-recovery archive were not exhaustively checked.
- Fresh screenshot-bound server read at 2026-10-28 16:44 MYT matched project
  `discussion_green_onion_malaysia_20261026`, topic ACTIVE and active navigation binding,
  project revision 4: eight questions, five assumptions, eleven evidence records, two checkpoints,
  zero decision records. Path is the structured projects root above plus
  `discussion_green_onion_malaysia_20261026/state.json`. Source hash
  `413957aa107a65e4ef577bdc8e3801e0f0eb1ecc8c2966b98636588d2a3cddc9`.
  Receipt: `.uuma-local/library-agent-discussion-20261028/brainstormer-topic-verification-11ebf13df29548388b3952ee02a47196.json`.
  No state or approval was changed. Checkpoints/objectives do not imply a settled solution.

## Evidence limits and proposals

Five user turns were readable; older assistant replies were content-reference placeholders.
Knowledge, Experience, Decision, and History are supported by user statements. Workflow /
Artifacts is provisional; the original fifth label has not been verified. Do not present a
reconstructed five-item list as a source quotation.

Durable local capture, incremental background upload, versioned NAS retention, a server catalog,
and semantic retrieval are proposed mechanisms. Paths, adapters, latency, retention, access
policy, project IDs, and server topology are not accepted implementation contracts.

Accepted transfer direction, with setup details still proposed: a small background collector
on each Windows computer, one-time pairing with the server, discovered-source selection,
throttled initial history backfill,
incremental direct upload, durable offline pending work, and per-computer progress/coverage.
Transfers do not require an LLM or the other Windows computer to be on. A powered-off or
unconnected computer cannot provide fresh local-only records. Keep upload acknowledgments,
verified NAS backups, and actual recoverability distinct. No collector has been installed.

Earlier repository-only context established Forge NAS and a Forge-only Notion relay. The latest
user-directed inspection additionally verified the separate general Notion knowledge sync above.
Neither proves complete two-computer coverage or an implemented Library connection. Do not borrow
Forge identity or equate Life/Live with Honc. Preserve all existing domain ownership.

## Continue

Next inspect supported source access, project roots, connectivity, and existing backup transport.
Both-computer/both-tool use is confirmed and must not be asked again. Then refine open
taxonomy and integrations in the canonical document. Separate confirmed intent from mechanisms.
Content completeness, historical retention, same-project association and initial history/context
retrieval are accepted. Next discuss reuse of the actual existing backup/Notion layout, independent
device provenance, consistent version retention and Brainstormer coverage. The current topic is
identified; broader future Life organization, version format, retrieval surface and later curation
remain open. Source access and NAS coverage
are technical investigations, not details the user must know now.
Coverage now includes all-agent durable data. Continue from the new inventory rather than asking
the user to list every table. Frequency/resource/storage/recovery details and remaining source
locations need design; retain accepted historical preservation and all domain review boundaries.
No runtime, profile, service, schedule, database, source history, Notion page, production
registration, or mission gate was changed by this record.
