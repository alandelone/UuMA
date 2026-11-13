# Scholar Catalog Reader Startup Repair — 20261111

The user asked to fix the remaining operational bugs so the system can be used without managing this project manually. This change targets the workstation Catalog Reading supervisor and its fixed-release selection.

**Applied and verified on November 11 at 11:31 Malaysia time.** The Reading task is Running with one logical reader (a parent/child Python pair) on the new fixed engine. Daily midnight startup is installed; the next scheduled start is November 12 at 00:00. Daytime model-event count remains 3,110, all initial queue counts and the exact expired source lease remain unchanged, and the Web process pair and manifest are unchanged. No database restore or new model call occurred during the repair.

Validation passed: 50 focused provenance/recovery/policy tests, 27 native release/launcher/task checks, and exact replay of all 209 retained contracts plus purpose scope. The initial failed activation, its consistent backup, later lease diagnosis, and successful guarded activation all remain as separate receipts.

## Concrete repair scope

- Reproduced the launcher's actual refusal: `The fixed release source differs from its verified digest.` Two previously repaired provenance modules had been changed inside `catalog-48cece41023e` while its manifest retained the earlier hashes.
- The task had only a logon trigger. Once stopped during the earlier repair, it had no daily night trigger to restart it without another login.
- Prepared `catalog-reading-repair-20261111-ebfc1965c357` as a separate 454-file release. It preserves the two existing provenance fixes and adds only the already implemented Theme recovery canonical-order fix missing from the selected engine. All other pinned source/parser files come from the selected baseline.
- Updated `scripts/install-scholar-catalog-reading.ps1` to register both delayed logon and daily midnight triggers. The existing worker continues to enforce 00:00–08:00 Malaysia automatic admission, safe manual priority, source eligibility, durable reuse, and a single reader slot.

| Identity | Value |
| --- | --- |
| Component / node | Catalog Reading only, workstation |
| Existing data owner | `C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db` |
| Existing Reading manifest SHA-256 | `8d24e015531725aa8c526a89933f190dc25543697eacce565dc41e023f2fffb1` |
| Candidate manifest SHA-256 | `e524d2f421c322c658d17aa72a26d1583cf79648901ce808713231e650ee6ea3` |
| Candidate runtime package SHA-256 | `ebfc1965c357cf512395501d79834a8bc7ff776a9bf94ef56f527778f4e46ad5` |
| Retained source archive SHA-256 | `7fa13ce627f6ca6ec536774ed44b938bd7b2e6044b8b207bf96e6dc8dd33d57e` |
| Runtime | Reuses the existing pinned Python, base interpreter and dependency identities; full launcher admission verifies them |
| Schema / recovery changes | No schema change, job reset, retry-limit change, or new recovery authorization |

## Validation and application boundary

The original strict probe, with only its manifest input changed to the candidate, reproduces the exact saved content and all 209 contracts on the real owner. The 19 native release-admission cases, four foreground-launcher cases and four installer cases pass against isolated fixtures. Focused provenance, role recovery, Theme evidence and reading-policy checks run against the candidate package before selection.

Application requires unchanged Reading and Web selection bytes, all 454 candidate source/parser hashes, no current Reading process, no live or unknown source/reading lease, and no queued manual request that a daytime restart would execute. A consistent SQLite backup and the original task XML are retained. The application atomically changes only `reading-release.json`, adds the daily trigger while retaining the existing action/principal/settings/logon trigger, and starts the existing dedicated task.

The first guarded activation stopped before any change because one source job was labelled RUNNING. Read-only reconciliation established that its lease expired on November 6 at 05:42 Malaysia, with no surviving Reading or parser process. The existing claim contract explicitly admits expired leases under normal policy and fencing. This exact diagnosed source lease is retained without modification for normal night reclaim; an unexpired, missing or newly changed lease still blocks activation. The failed attempt and its backup remain preserved.

Verification must show one logical reader using the new engine, task state Running, a nonempty next midnight start, unchanged daytime model-event and queue counts, and the same Web process identities/selection. Retain the real receipt before claiming the repair is active.

## Recovery and remaining evidence

The receipt directory contains the previous Reading manifest, unchanged Web manifest, original task XML and consistent database backup. Configuration rollback uses those retained selections/task definition after verifying an idle reader boundary. The prior configuration represents the stopped pre-repair state and has the documented source drift; it is not a healthy fallback release. Do not overwrite the live database with its backup or alter historical events. An active new job must reach its safe checkpoint before any stop or configuration reversal.

Six recovered initial jobs remain queued for their actual permitted night execution. Successful startup must not be reported as six successful paper readings. Their existing grants and saved outputs are reused; the user need not manually start the night supervisor. Historical deletion disclosure remains an accurately recorded exception; this repair does not rewrite that history or approve the mission gate.

All six original admissions were also independently checked against the selected candidate's unchanged authorization validators: each remains READY with its expected fence and exactly one matching, source-bound recorded grant. [Retained authorization check](../../.uuma-local/scholar-catalog-implementation-20261023/reader-repair-20261111/recovery-grants-verified.json).

Private preparation, check and eventual activation receipts: `.uuma-local/scholar-catalog-implementation-20261023/reader-repair-20261111/`.

- [Successful activation and before/after runtime evidence](../../.uuma-local/scholar-catalog-implementation-20261023/reader-repair-20261111/activation-expired-lease-reconciled.json).
- [Candidate preparation/source identities](../../.uuma-local/scholar-catalog-implementation-20261023/reader-repair-20261111/preparation.json).
- [Original-content/209-contract replay](../../.uuma-local/scholar-catalog-implementation-20261023/reader-repair-20261111/candidate-strict-replay.json).
- [Focused test result](../../.uuma-local/scholar-catalog-implementation-20261023/reader-repair-20261111/focused-tests.log) and [native startup/task checks](../../.uuma-local/scholar-catalog-implementation-20261023/reader-repair-20261111/native-tests.log).
