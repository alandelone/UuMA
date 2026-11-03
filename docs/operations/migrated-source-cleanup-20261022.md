# Migrated workstation source cleanup: 2026-10-22

The user explicitly confirmed deleting verified C-drive copies after migration to
NAS Z and alandelone-server-001. The old C Hardware-Lab-Workspace and its Git directory
are deleted. NAS retains the complete Git history, including the original committed
baseline, and passed another full integrity/ancestry check.

Removed2,090 verified entries (1,270,973,665 logical bytes): the old Wisdom, Lab, Honc,
Yonc database copies; Brainstormer state; migrated domain files; manifest-listed files
in five archived Agent profiles; and corresponding local final migration snapshots.
All selected files had verified original server snapshots. SQLite row contents were
compared where backup headers differed. The remote rollback snapshots remain intact.

Five server Telegram receivers remained connected. Workstation serves only
Orchestrator/default and Scholar. Server databases passed quick_check, NAS Git passed
fsck, and the remote final archive checksum was unchanged after deletion.

Development repositories/model environments, workstation browser/Notion login data,
independent untransferred legacy backups and old caches are retained. Archived profile
directories can remain: only their verified migrated files were removed. Remote-owner
markers and small manifests/receipts remain. No execution policy was changed.

Earlier local rollback-copy notes are superseded. Restore from server/NAS evidence,
reconciling newer production writes first. Local audit receipts are under
.uuma-local/migrated-source-cleanup-20261022/.
