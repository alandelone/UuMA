# Librarian agent coverage audit

Observed 2026-11-07 at 10:02:54 UTC+8, with subsequent read-only decision checks.

## Current backup receipts

The configured server operations reader returned 63 source identities, 304 batches,
306 manifest revisions, 306 matching NAS publication receipts and zero pending
revisions. Four sources remained PARTIAL. Receipt matches were read from the current
ledgers. This audit did not rehash archived payloads or perform restoration.

| Agent or data source | Latest registered batch | Observed scope |
| --- | --- | --- |
| Brainstormer | 2026-11-07 | Native state.db, structured project state/proposals, audit, memories, logs, cron and navigation |
| Yonc | 2026-11-07 | Project Graph database, native state.db, memories, logs and cron |
| Honc | 2026-11-07 | honc.db, native state.db, memories, logs and cron |
| Forge | 2026-11-07 | Lab/design data, hardware workspace, commerce, relay, native state.db, memories, logs and cron |
| Wisdom | 2026-11-07 | wisdom.db, content, native state.db, memories, logs and cron |
| Librarian | 2026-11-07 | Native state.db, configuration, role, logs and cron |
| Scholar | 2026-11-07 | Workstation RSTV4 catalog.db. Its native Hermes profile history was not found among received paths |
| Shared UuMA control | 2026-11-07 | Server data/uuma.db, including control events |
| Workstation Codex | 2026-11-07 | Session/archive/state/attachments captured. App roaming source PARTIAL with 95 unavailable entries |
| Antigravity core | 2026-11-05 | 49,396 captured entries, four unavailable, PARTIAL and now old |
| Antigravity logs/User | 2026-11-07 | Registered sources COMPLETE. The separate Backups source contains an initialization marker |
| Phoenix and ChatGPT bridge state | 2026-11-07 | Their registered databases COMPLETE |
| Workstation Hermes main history | No received path found | Local AppData/Local/hermes/state.db exists with 4,984 sessions and 64,458 messages at inspection |
| hermes_xgp | Unconfirmed | No matching registration/source path found under either underscore or hyphen spelling |

The other two PARTIAL sources are historical project-chatgpt-watchdog (2026-10-31,
one unavailable entry) and project-watchdog-inventory-p00001 (2026-11-02, one
unavailable entry). Their publication receipts exist. Their old snapshot dates remain
visible. COMPLETE is the registered manifest's entry coverage, not an assertion that
every persistent file of the named agent has been enrolled.

The current server capture timer last triggered November 7 at 00:00:48 UTC+8 and
remained active. The publisher timer remained active. Both the multiplex gateway
and separate Hermes serve unit were active. These checks do not certify every
application's own state or all restore requirements.

## Project-centric retrieval

The readable catalog remains snapshot librarian-index-20261103033751, published
November 3 at 11:37:51 UTC+8. It has 59 structural-index records, comprising one
Brainstormer topic index and 58 Yonc project indexes. Every index carries explicit
project_ids, source identity, original status, version and original provenance.
The project-context reader filters authorized latest record versions by project ID.

The Brainstormer index uses discussion_green_onion_malaysia_20261026. Yonc indexes
use yonc_proj_<graph-project-id> identities. This snapshot does not establish a
complete cross-agent mapping between those identities, local project trees and
server artifacts. Encrypted intake registration alone does not create project
associations or readable content projections. Most current recovery sources remain
outside the content catalog.

## Decision records

Native Hermes conversations preserve discussion text in each profile's state.db.
Server specialist native databases have received November 7 backups. The local
main Hermes history and local Scholar native profile were not found in received
manifest paths, so their conversation decisions cannot be claimed covered here.

Brainstormer's structured owner store is
`/home/alandelone/.local/share/uuma/production/brainstormer/brainstormer/`.
Project objects are in `projects/<project_id>/state.json`; proposals are in
`proposals/`; append-only audit evidence is separately captured. The inspected
project is revision 6, last updated October 28 at 09:07:48Z. It contains five
assumptions, two checkpoints, one project, 12 evidence objects, eight questions and
one topic. It contains zero decision objects. Proposal files have five APPROVED
and one PROPOSED status. These are distinct observations. An approved state
transaction does not establish a decision object or an accepted solution.

Honc stores structured life/execution data in production/honc/honc.db. The inspected
execution_events table currently has one row, an October 16 outcome about improving
agent quality. This is only the older execution subsystem. A follow-up inspection
found 46 life objects across the separate life module, including 11 diary, four body,
22 habit, eight habit-definition and one settings object. The latest diary and habit
records were saved November 5 at 22:11:35 UTC+8. The latest body record was saved
October 28 at 11:50:30 UTC+8. Reporting the one-row execution table alone gave an
incomplete picture of persisted life records. Control results are retained
in the shared control event store, while agent domain records retain their owners.
This audit found no completed universal decision index spanning every agent.
Librarian's 59-record structural catalog is not such an index.

## Evidence and scope

Private receipts are .uuma-local/librarian-audit-20261107.log and
.uuma-local/librarian-decision-audit-20261107.log. Read-only checks used the profile's
configured operations source, received manifests, published catalog, existing native
databases and selected domain state metadata. No model inference, production writes,
new captures, restores or service restarts were performed. No private conversation
content or credentials were included in this report.

## Follow-up findings on November 7

The November 7 Codex roaming manifest has 77 PermissionError entries and 18
TimeoutError entries, totaling 95 unavailable files. They include application web
cache, lock files, Cookies, browser History, Account Web Data and related SQLite
stores. These are per-file capture failures. The same manifest has 12,093 captured
entries. Codex state, native session/archive sources and attachments are separate
registered sources with November 7 receipts.

The workstation daily task ran November 7 at midnight and returned exit code 2.
Its status stream records antigravity-core FAILED with ValueError. The task's
selected fixed source is workstation-sessions-7ade91d0a0d9474e9c14a809326c99ad.
Its old paginated _tree scan is still selected, while the development source has a
subsequent scan change. A read-only invocation of the actual pinned scan reproduced
`Discovery directory changed; restart its inventory`. The changing Antigravity tree
invalidates its inventory cursor and prevents creation of a new core batch. Existing
November 5 core backup remains PARTIAL with two PermissionError lock-file entries
and two ValueError entries. Logs and User sources have separate successful runs.
No collector repair or runtime publication was performed in this explanatory audit.

The actual server control events table contains 601 events, including 88
RUN_REGISTERED, 63 RUN_RESULT_SUBMITTED and five ROUTE_DECIDED events. Honc accounts
for 27 registered runs and 19 submitted results. Latest control event was Honc's
result submission on November 5 at 22:11:49 UTC+8. A literal reference check found
six of 37 committed Honc life operation IDs mentioned in control event payloads.
This check does not establish complete life-to-control indexing. Full diary/body
facts, source messages and revisions reside in honc.db. Control task/run evidence
and domain records have distinct scopes.
