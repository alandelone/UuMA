# Librarian: agent data coverage

> Status update, 2026-10-30: This is a historical inventory. The user has since
> authorized implementation and deployment; initial captures and server intake
> are operational. See [implementation status](../operations/librarian-implementation-status.md)
> for current evidence and remaining gaps.

Status: accepted scope expansion; initial read-only source inventory, not backup activation  
Updated: 2026-10-28, Asia/Kuala_Lumpur; inventory receipt at 16:56 MYT  
Canonical design: [Librarian](../agents/librarian.md)  
Prior inspection: [existing NAS, Notion, and Brainstormer backups](../operations/library-existing-backups-2026-10-28.md)

Latest combined review renamed the agent Librarian, kept it server-side, fixed capture at
00:00 UTC+8 once daily, and selected existing A2A collaboration plus a read-only MCP. The
[complete architecture](librarian-architecture-v1.md) records those decisions and implementation
status. This inventory retains the earlier inspected source locations and historical evidence.

## 1. Scope clarified by the user

Library must preserve agents' durable working information as well as the previously confirmed
two-Windows conversation, execution, and project-file history. The user explicitly named all
Brainstormer structure, Yonc Project Graph, and Forge Lab data such as items and event history,
and asked to identify the other agents' persistent records too.

This is additive scope. It includes original discussions, unresolved reasoning, domain records,
relations, history, proposals, reviews, receipts, and related source/artifact files. Domain owners
retain their authority. A Library backup does not accept a project change, scientific conclusion,
knowledge patch, inventory movement, or task completion.

The user has not requested implementation or deployment. The inspection used directory metadata,
read-only database schema queries, and selected nonsecret runtime paths. No backup/restore worker,
database initializer, model call, service restart, or NAS Git operation was executed.

## 2. Persistent source inventory

Server paths below are on `alandelone-server-001`. File existence and indicated schema families
were read directly; they are not evidence that complete backups currently exist.

| Owner | Durable records to cover | Observed primary storage and evidence |
| --- | --- | --- |
| Brainstormer | Every project/topic, question, assumption, evidence record, reasoning relation, checkpoint, proposal/review, decision when one exists, and history | `/home/alandelone/.local/share/uuma/production/brainstormer/brainstormer/projects` and `proposals`; `/home/alandelone/.local/share/uuma/production/brainstormer/navigation.db`; previously verified current topic/source state. |
| Yonc | Project nodes/edges, goals/actions, resource references, proposals and versions, operations/status history, assignments, deliveries, user reviews, execution receipts, split discussions, and saved views | `/home/alandelone/.local/share/uuma/production/yonc/project_graph.sqlite3`; effective `YONC_GRAPH_DB` from the active Graph process matches this path. Twenty-five user tables observed. |
| Forge Lab_Bot | Physical inventory references, locations, purchase/order history, lots, inventory events, builds, commissioning/failures, engineering lessons, worklogs, journal jobs/events/notifications and receipts | `/home/alandelone/.local/share/uuma/production/forge-lab-bot/lab.db`; twenty user tables observed, including `component_refs`, `purchase_lots`, `inventory_events`, `builds`, `failure_records`, `engineering_lessons`, and journal/worklog tables. Active journal `LAB_DATABASE_PATH` matches. |
| eSchematic, with distinct design ownership | Component definitions/aliases/pins and other authoritative design records; related designs and generated outputs where present | `/home/alandelone/.local/share/uuma/production/forge-lab-bot/eschematic/data/catalog.db` and `catalog.json` exist; DB has `components`, `component_aliases`, and `component_pins`. Active configuration also names an `eschematic/output` directory, which was absent at inspection. Other design artifacts can reside in the NAS workspace below. |
| Honc | Work rounds/segments, execution facts, completion assessments, task snapshots and graph receipts; habits, life objects/revisions/sources, reminders, occurrence/delivery history and pending operations | `/home/alandelone/.local/share/uuma/production/honc/honc.db`; twenty-three user tables observed, including both execution and life-history families. These remain distinct from Brainstormer deliberation. |
| Wisdom-Oldman | Sources/documents, evidence, claims and conditions, relations/conflicts, candidate patches and review/reversal events, topic versions, questions/gaps, research runs/traces, and Orbit cycles/frontier/history | `/home/alandelone/.local/share/uuma/production/wisdom-oldman/wisdom.db` plus `wisdom-content`; thirty-six user tables observed, including search/index tables. Active Wisdom data configuration matches this root. Related artifacts and existing operation state also need source inventory. |
| Scholar / RSTV4 | Research catalog and provenance, source PDFs, extraction/understanding artifacts, Field/Topic/Track records, annotation/review history, experiments, writing workspaces, manuscript versions and outputs | Workstation `C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db`, `data/artifacts`, and `data/writing-studio` exist. Actual referenced PDF/resource roots and server FieldKG graph dependencies require a separate source manifest. Live Scholar schema/rows/jobs were not inspected or altered in this inventory. |
| Orchestrator / UuMA control | Agent task/run contracts, events, operations, artifacts and their references, verification records and cross-agent receipts | `/home/alandelone/.local/share/uuma/data/uuma.db`; ten user tables observed. Active control `UUMA_DATA_DIR` matches. Referenced artifact files must accompany record-level provenance; local orchestration/desktop receipts require their own verified source mapping. |
| General Notion knowledge store | Synced page content and source identities, revisions preserved by Library, sync runs/events and dated recovery snapshots | `/home/alandelone/services/notion-sync/notion_sync.db`; NAS `/mnt/nas/backups/notion-sync`. Previously inspected independently from Forge's journal relay. |

The source schema inventory establishes record families, not a promise that every table already
contains user data. Empty tables and not-yet-created output directories must not cause fabricated
records or claims that data has been lost.

### Forge items and engineering state span related owners

The user's item example maps to more than one physical store. eSchematic's catalog holds component
definitions, aliases, and pins; Lab holds physical stock/lot/event/build and engineering records.
The Lab DB does not have a literal `items` table in the inspected schema. Preserve these stores
and their links together while keeping component definitions distinct from actual inventory and
purchase history. Neither a catalog item nor an order line proves present stock.

The live project workspace is `/mnt/nas/Hardware-Lab-Workspace`, also visible on Windows as
`Z:/Hardware-Lab-Workspace`. It contains project files, shared material, outputs and Git metadata.
Those are the same live directory through two paths, not two independent backups. No Git command
or write was performed there during inspection.

Additional Forge source directories verified:

- `/home/alandelone/.local/share/uuma/production/forge-lab-bot/commerce`
- `/home/alandelone/.local/share/uuma/production/forge-lab-bot/notion/relay-receipts.db`
- `/home/alandelone/.local/share/uuma/production/forge-lab-bot/eschematic/data`

## 3. Native agent history is a separate required source

All five server specialists have a native `state.db` under:
`/home/alandelone/.local/share/uuma/pilot/home/profiles/<agent>/`.
Verified agent directory names: `brainstormer`, `yonc`, `honc`, `wisdom-oldman`, and `forge-lab-bot`.
Each also has `memories`, `logs`, and `cron` directories. Related image/audio/session data and
profile-local project records need source coverage where present. An attachment stored under a
cache-named directory may still be the only retained copy; classify by actual content and source
role before treating it as disposable.

Native dialogue/tool history and a domain database are different records. Preserve both. Honc's
execution ledger is not its entire chat history; Yonc's Graph is not its entire planning dialogue;
Brainstormer's structured checkpoints are not every original message.

The server's shared gateway/runtime state and delivery/idempotency/response stores were identified
as additional recovery dependencies in prior directory inspection. Exact ownership, inclusion,
and consistent collection need a dedicated contract. Workstation Orchestrator/Scholar native
profile roots have not been fully resolved by this inventory and must not be guessed from an
empty or legacy `.hermes` folder.

## 4. Coverage contract to design next

The accepted requirement is preservation of all relevant records with historical backups.
Proposed implementation details:

- Register each source with an owner, verified active location, record families, related files,
  schema/format version, source identifiers, collection method, and coverage/failure status.
- Collect a source-consistent database version together with the files required by its retained
  records. Keep hashes, source locations, version references and collection times. Do not silently
  substitute a running database-file copy for a consistent backup.
- Preserve relationships and review/status history, including unresolved discussions, rejected
  proposals, failed/paused work, compensating reversals, and uncertain receipts. Archiving must
  not resume, retry, approve, or complete those operations.
- Keep per-owner consistency boundaries explicit. Recording several stores in one manifest does
  not create a globally atomic snapshot or justify joining independent schemas.
- Include provenance for graph/search/vector projections and their rebuild inputs. Decide a
  supported export/recovery or rebuild contract for OpenSPG/FieldKG and other derived services;
  do not infer that copying their configuration captures their data.
- Preserve reproducibility metadata and needed profile/configuration versions alongside records.
  Recovery material and caller access need distinct treatment; storing a source does not make
  all its private contents visible to every agent.
- Add newly discovered or newly deployed agents' durable sources to the same coverage inventory,
  so the user need not enumerate individual tables repeatedly.

Domain-specific semantic retrieval/export/restore adapters remain the agent-facing boundary.
Do not expose a new generic SQL/vendor API through Library. Keep `uuma.db`, Wisdom knowledge,
Lab, Graph, Honc and Hermes native stores separate and retain their existing authority rules.

## 5. Remaining design details and evidence

The scope expansion is clear. Source-specific consistency methods, automatic collection intervals,
resource limits, NAS capacity/storage layout, and retrieval/recovery surfaces remain design work.
Historical preservation after source deletion is already accepted and must not be asked again.
Exact current coverage and recovery must eventually be tested per source; this source inventory
does not establish recurring backup health or completed Library integration.

Private metadata receipt:
`.uuma-local/library-agent-discussion-20261028/agent-source-inventory-f4b9fc4267494ee597944350a53043a8.json`.
It contains inspected paths, DB table names, native-profile existence, Yonc's effective DB path,
and bounded workstation file-existence checks. No credentials or raw personal/domain record
contents were copied into this document or receipt.
