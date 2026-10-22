# Production cutover checkpoint: 2026-10-22

| Component | Actual owner | Status |
| --- | --- | --- |
| UuMA control | alandelone-server-001 | Single authoritative control API |
| Brainstormer | Server | Connected; admission open |
| Yonc and project Graph | Server | Connected; admission open; 691 nodes, version65 |
| Honc and life ledger | Server | Connected; admission open; original reminder resumed |
| Wisdom | Server | Connected; canonical knowledge/CPU KAG; governed Orbit runner |
| Forge | Server | Connected; Lab/eSchematic/journal server; workspace and Git on NAS |
| Orchestrator and Scholar | Workstation | Retained; Scholar research remains PAUSED46/126 |

Honc retained all23 domain tables, 44 profile files and its existing delivery binding.
The same reminder job3381ec71b9d2 resumed from repeat.completed5696, with all delivery
and uncertain receipts preserved. The migrated source profiles are archived outside
the workstation gateway's served profiles. No new model verification call or research
queue retry was performed. Honc's Linux contract suite passed261 tests with2 existing
skips; no assertions were weakened.

Workstation navigation and Yonc UI retain ports8772 and8766 through authenticated
proxy/SSH forwarding. Browser, voice transcription and desktop connectors remain on
the workstation. Its startup helper resumes owned connectors; code updates remain
manual. Source Graph startup and watchdog recovery respect the server owner marker.

The server gateway now explicitly includes the full pinned Hermes source in PYTHONPATH;
an older editable dependency mapping otherwise omitted tui_gateway and failed a
background worker. The full import probe passed before the zero-active gateway restart.
No shared domain database or OpenSPG configuration was reset during that repair.

Private production receipts and rollback snapshots are retained under .uuma-local and
on the server. The mission verification gate remains pending_review. This checkpoint
does not by itself certify all A2A/release architecture acceptance work.

## Wisdom and Forge final cutover

All five specialist Telegram receivers are connected on alandelone-server-001 and
admission is open. Workstation gateway serves default/Orchestrator and Scholar only.
The two newly moved source profiles are archived outside served profiles; retained
workstation Wisdom/Lab databases carry remote owner markers that reject new local
store initialization. Final original table counts matched before server writers started.

Wisdom owns production/wisdom-oldman/wisdom.db and its content-addressed source tree.
Knowledge MCP uses authenticated identity forwarding; Orchestrator/user alone may
apply/reject/reverse canonical knowledge patches. The read-only topic view keeps
localhost8767 through SSH. CPU ONNX bridge8891 uses the same original model/tokenizer
hashes and OpenSPG project1. No reindex or automatic projection drain was invoked.
Stopped, failed and budget-exhausted Orbits retain their status and history.

Forge owns production/forge-lab-bot/lab.db, eSchematic data/output, commerce archives
and its journal runner. eSchematic has an isolated dependency lock under deploy/forge.
Its one existing queued journal job completed after restoration;12 jobs nowSYNCED,
with the original cancelled job retained. No manual retry was issued. Notion credentials
remain workstation; a Forge-only semantic relay uses durable request receipts and
stable perjob mutation identifiers. Uncertain results require reconciliation. Procurement
runs the browser on the workstation and writes/evaluates against the server-owned Lab.

NAS workspace remains Z:/Hardware-Lab-Workspace on Windows and
/mnt/nas/Hardware-Lab-Workspace on server; Forge pool workers may use this workspace.
The original C copy is rollback-only. No second bot/legacy bridge was started.
Eleven owned production user services are enabled for boot, with user linger enabled.
Code releases are manual. The fixed running content snapshot is
8d751df2ca0f2dfee43853ba5bc279009b6760343c0d251f4dd4f9a3a33cd9d0;
review commits, content versions and unchanged component versions remain distinct.

Verification: Windows237 tests passed; Linux73 focused migration contracts passed.
Both final domains and900 transferred files were verified against the final manifest.
Final archive SHA256:73ffeb536b370902bb03c8a8a940b29a6ae858ac582e261eef61343b2cf5f269.
Private receipts: .uuma-local/wisdom-forge-production-cutover-receipt.json and
.uuma-local/wisdom-forge-cutover-20261022/. Rollback must reconcile any new server
writes before switching back. Do not overwrite new data using retained source copies.

These two Agent cutovers are complete. Remaining original architecture acceptance
includes broader A2A interruption/cancellation/consultation coverage, release OS hooks,
and Observatory remote adapter/version views. The mission review gate remains pending.
Scholar's research queue remains PAUSED46/126; no model verification was replayed.
