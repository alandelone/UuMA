# Librarian refined acceptance report review — 2026-11-05

## Latest recheck — 2026-11-05, report timestamp 11:00 UTC+8

**The four findings below are resolved in the rechecked report revision.** They remain
below as historical findings, not current unresolved failures for this revision.
The report can serve as a scoped progress/acceptance record; the overall deployment
still has nine explicitly PARTIAL requirements and is not fully accepted.

Independent recheck evidence:

- Report SHA-256: `06aba1218a00fdf7d744d8919cb3af7b6e3bc214f494cf7aa6007beb4c0d904b`.
- Machine receipt JSON SHA-256: `49d36b912c169d3de3dafc01db3240bda87cc95af177c7bb6bb123d49dc8b9d9`.
- Parsed all fourteen unique batches from `actual_execution_receipts_14.json`.
  Reported capsule/plaintext hashes, sizes and table counts agree with that JSON.
  Each receipt records COMPLETE coverage, one restored entry, matching expected
  plaintext hash, `integrity_check = ok`, and a table-list length matching its count.
- Independently fetched each corresponding immutable server manifest: all **14/14**
  capsule hashes, capsule sizes and snapshot hashes match, and all referenced
  intake object sizes match. Thus the former thirteen digest discrepancies are
  resolved. This round did not independently download, decrypt or rehash all real
  capsule/plaintext objects; actual recovery evidence comes from the supplied
  machine execution receipts, corroborated against live source manifests.
- Independently reran the revised synthetic suite: **5/5 passed**, including
  rejection of a wholly UNAVAILABLE batch with `NO_CAPTURED_ENTRIES`. The former
  successful `EMPTY_SOURCE` branch is removed; SQLite failures still reject.
- Summary and twenty-row matrix both count **11 PASS / 9 PARTIAL**.
- Recovery is now described as temporary-directory isolation using the host's
  recovery key and SSH retrieval. Physical offline key custody stays PARTIAL;
  “Air-Gapped” appears only in the explanation of why that claim is not made.

The nine partial items remain **3, 4, 5, 6, 9, 10, 15, 16, 18**. This review does
not independently re-approve every other requirement, perform full-scope recovery,
approve the mission gate or change any production service.

Recheck record:
`.uuma-local/librarian-implementation-20261029/audit-final-receipts-20261105.json`.

## Historical review of the earlier 10:17 revision

Review target: [librarian-acceptance-report-2026-11-04.md](librarian-acceptance-report-2026-11-04.md), refined version dated 2026-11-05 10:17 UTC+8.

**Conclusion: do not accept this revision as verified acceptance evidence.** Several scope statements are improved and the original swallowed-integrity defect is repaired, but the restore receipt values do not reconcile with their named immutable source batches. This review made no production changes, performed no new real decryption, and did not modify the target report or verifier.

## Findings

### F1 — P1: thirteen of fourteen reported plaintext digests do not match the named server manifests

The fourteen entries in report section 4 were parsed and compared by exact batch identity against the latest server `manifest_revisions` record. All fourteen named batches exist, are COMPLETE, and have one captured entry. Only Phoenix matches the report's snapshot SHA-256 and capsule size. The other thirteen reported snapshot digests do not match their source entries, and none of those reported digests appears as a snapshot digest in any revision of the currently retained intake ledger. Several reported capsule sizes also differ.

Examples:

| Batch | Report value | Manifest value |
| --- | --- | --- |
| `workstation:chatgpt-bridge-state:2026-11-04` snapshot SHA-256 | `e875f317b12da36ad94a5e3b6e86fb7e2b6946059d0a7905c317ff0a2cf75f32` | `e875f317b12da36a43bf6416d44dfbd55adb25563e584652620e746335d8b8b7` |
| `workstation:codex-state:2026-11-03` snapshot SHA-256 | `a0e78550186c8fef3e53ba59aee002ec7e58e3ce6f31698288fbaf85055272a8` | `d031339479df082abd41cf6deb083917bdf01cdd5cdde005468a867ca888b8e9` |
| `server:yonc-graph:2026-11-04` capsule bytes | 3,441,360 | 2,380,496 |
| `server:brainstormer-native:2026-11-04` capsule bytes | 123,600 | 2,081,488 |
| `server:forge-lab:2026-11-04` capsule bytes | 4,047,568 | 2,806,480 |

This invalidates the report's claim that those listed exact digests matched the named manifests. It does not establish that the stored backups themselves are damaged. The successful four-case synthetic suite also cannot establish any real batch's plaintext digest or table count.

Required follow-up: retain the current report as historical review input; rerun or recover the actual execution receipts with fixed batch/revision/manifest digests and tool version hashes. Generate the report directly from those receipts. Verify the correct object and plaintext digest before declaring a sample restored. Do not merely replace the displayed hashes with expected manifest values and call that evidence of actual decryption.

Read-only reconciliation log: `.uuma-local/librarian-implementation-20261029/review-refined-report-20261105.log`. It contains report/manifest comparisons for all fourteen entries. The audit did not fetch or decrypt the capsules and therefore independently confirms metadata mismatches, not real plaintext recovery.

### F2 — P1: an entirely unavailable batch is still reported as successful EMPTY_SOURCE

Location: `.uuma-local/librarian-implementation-20261029/verify_isolated_restore.py:52`.

The helper filters to CAPTURED entries and returns `(True, "EMPTY_SOURCE")` when that list is empty. A valid nonempty PARTIAL manifest whose only SQLite entry is UNAVAILABLE therefore counts as successful restoration despite restoring no data. The main runner includes that true value in `all_ok` and can report overall PASS.

A fresh synthetic fixture with one UNAVAILABLE entry reproduced `(True, "EMPTY_SOURCE")`. No network call or real key was used. The supplied four negative/positive cases do not cover this branch.

Required follow-up: distinguish an explicitly empty source from a failed/nonempty source. UNAVAILABLE entries and partial coverage must remain PARTIAL/FAIL; a successful sample must report exactly what was restored. Add this regression case while preserving the newly repaired SQLite error rejection and connection closure.

Reproducer: `.uuma-local/librarian-implementation-20261029/probe-unavailable-restore-20261105.py`.

### F3 — P2: summary totals do not equal the acceptance matrix

Report summary says **12 PASS / 8 PARTIAL**. Parsing all twenty matrix rows yields **11 PASS / 9 PARTIAL**. Partial items are **3, 4, 5, 6, 9, 10, 15, 16, 18**.

Required follow-up: derive summary counts from the matrix after reconciling the substantive evidence. These arithmetic counts describe the author's status assignments; this review does not independently approve the eleven PASS rows.

### F4 — P2: “Air-Gapped” is not established by this verifier

The executive summary labels the fourteen restores “Air-Gapped Sandbox”. The verifier loads the original workstation's DPAPI-protected key material at module initialization and fetches manifests/capsules via SSH. A temporary output directory is filesystem isolation, not evidence of a network-disconnected environment or independent key custody.

The updated item 18 correctly leaves physical key custody PARTIAL; keep that correction and describe these as isolated-directory/sample restores unless a separate offline execution receipt exists. No new air-gap receipt was demonstrated in this review.

## Confirmed improvements

- Former `except Exception: pass` around SQLite verification was removed. A non-ok `integrity_check` now returns false; SQLite exceptions return false; connections close in `finally`.
- Independently reran the supplied four-case synthetic suite: **4/4 passed**, covering simulated non-ok integrity, plaintext hash mismatch, capsule hash mismatch, and the mocked positive path. This is unit-level evidence, not fourteen real restore executions.
- Items 4, 6, 9, 10, 15, 16 and 18 now expose partial coverage rather than overclaiming completion.
- NAS terminology is corrected to **153 revisions / 152 batches**, and the report explicitly separates private recovery intake from the two-source/59-record semantic catalog.
- Current scope preserves the second Windows PC deferral and acknowledges missing project-tree capture and offline key custody.

## Review boundary

No real key export, production restore, NAS publication, service restart, source-code fix, target-report correction, commit or push was performed. The report remains a draft pending reconciliation. Mission gate remains verification/pending_review. The original 2026-11-04 review remains historical; this document records the current refinement's new and resolved findings.
