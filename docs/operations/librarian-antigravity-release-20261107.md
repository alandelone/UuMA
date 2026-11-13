# Antigravity live-directory capture repair

Date 2026-11-07, UTC+8.

## Request and change

The user authorized formal deployment of the Antigravity capture repair. The source
is on the current Windows workstation, so the production Windows scheduled action
must select the repaired collector. Server intake and NAS publication retain their
existing roles. The shared server collector also received the reviewed scan repair.

The previous Windows task selected a fixed source snapshot from November 3. Its
paginated discovery rejects a directory cursor after the source changes. The actual
source scan reproduced `Discovery directory changed; restart its inventory`, and
the November 7 daily run reported core capture failure.

The repaired `_tree` uses the existing bounded complete walk when a page cursor
becomes invalid. Every fallback inventory issue remains fatal. This includes file
count limits, deadlines, unreadable directories and unsupported links. Per-file
capture failures remain explicit manifest entries. Existing SQLite online snapshot
selection and WAL/SHM handling are retained.

## Fixed production sources

Windows selected release is
`antigravity-tree-dfe26b74ab93ace2a9aac9f6`, with module SHA-256
`dfe26b74ab93ace2a9aac9f6fc493dc2fe721a9a4634b75e47b5cf00493edf8c`.
It is under the workstation Librarian device's `runtime` directory. The release
copies the verified scheduled baseline and replaces only `_tree`. Its source and
dependency manifests were verified before selecting its launch action. The existing
task principal, triggers, settings, interpreter, queue and source configuration are
retained. The previous task XML and hashes are in the private release receipts.

Server selected release is `server-tree-478ec542ba2b7d7a723298a9`, module SHA-256
`478ec542ba2b7d7a723298a90cf586bf540b166eb2092c3cc6cd4d842fc6438a`.
The server capture service's idle admission, baseline files, configuration and
interpreter were verified before publication. A scoped service override selects the
new launch path. The capture timer remains active. The server launcher returned
`LIBRARIAN_SERVER_RUNTIME_VERIFIED`.

The selected server service was then started through its normal systemd entry
point at 10:45:48 UTC+8 and completed with Result=success and ExecMainStatus=0.
Observed repository HEAD was `3c9bc5b1a4bfff113bcc0ec8fb874400608a5b56`.
The reviewed source/test corrections in this release were uncommitted working
changes. Fixed runtime content is identified by the manifests and hashes above.

## Verification

Focused server/workstation/discovery tests passed 26 tests with one Windows symlink
privilege skip. Ruff passed. Regression cases verify successful recovery from a
changed directory and rejection of all incomplete fallback inventories. An existing
Windows timestamp-sensitive discovery fixture initially failed because its directory
change shared a filesystem clock tick. The fixture now explicitly advances the
directory timestamp and retains the same rejection assertion.

A native scheduled task runs a source-scoped production capture using the repaired
Windows launcher and the existing queue, recovery key enrollment and transport.
The first diagnostic invocation failed because its new status directory had not
been created. The directory was created and the production capture was retried.
The repaired daily action was already selected before this diagnostic retry.

Read-only stack inspection confirmed that the subsequent long-running phase was
header inspection of approximately 59,307 source files. It was progressing through
actual Antigravity conversation/transcript paths. The scan remains at the collector's
existing lowered process priority.

## Production follow-up on November 12

The November 7 source-scoped retry captured 58,590 entries and reported one
unavailable entry with PermissionError. The server received revision 1 and NAS
publication completed at 12:48:28 UTC+8. The missing November 6 batch remains
visible in the capture history.

Every daily batch from November 8 through November 12 reached NAS. The November 8
through 11 batches each captured 59,014 entries with one unavailable entry. The
November 12 batch completed capture at 01:52:30 and NAS publication at 03:08:42
UTC+8, with 59,198 captured entries and zero unavailable entries. The intake and
NAS manifest digests match the publication receipts for all six days from
November 7 through November 12. An independent NAS readback matched the length
and SHA-256 of all 58,590 captured November 7 objects and all 59,198 November 12
objects. The combined readback covered 12,731,530,838 encrypted bytes. Private
status and readback receipts are `status-20261112.log` and `readback-20261112.log`
in the release receipt directory.

The server capture timer remains active with the repaired `server-tree` release
selected. The Windows daily task ran at midnight November 12. Its overall exit
code 2 reflects the partial `codex-app-roaming` source, which captured 10,425
entries with 78 unavailable. Eight entries timed out, with none named `History`.
The registered Codex session, archive, attachment and state sources all reported
COMPLETE that day.

## Related clarification

Honc's persisted life module includes 11 diary objects, four body objects and 22
habit objects. These are in `honc.db` and included in its November 7 database backup.
The single `execution_events` row describes an older separate execution operation.

The 18 Codex snapshot timeouts refer to databases inside Codex's embedded browser.
Their basenames comprise three Account Web Data, one DIPS, three History, three
Web Data, three QuotaManager, three declarative performance observer, one Top Sites
and one ukm_db. They are separate from the registered native conversation/session
sources. This Antigravity release does not establish that those timeouts are resolved.

## Rollback

At an idle boundary restore the Windows task's previous action from its retained
XML and remove the scoped server service override after checking current ownership
and source hashes. Preserve all newly captured batches, queue revisions, server
intake and NAS history. Private receipts and diagnostic helpers remain under
`.uuma-local/librarian-antigravity-release-20261107`.
