# Testing and Recovery Contract

## Deterministic tests

- Tests must use `tmp_path`, in-memory substitutes, or versioned files under `test-fixtures/`.
- Never point tests at `%LOCALAPPDATA%\UuMA`, Hermes `state.db`, live credentials, or network services.
- Assertions should express an approved contract, including provenance, permissions, and event order.

## Failure triage

Physical database byte comparisons require a quiescent fixture. After a successful asynchronous
discussion, drain that fixture's writer before freezing a baseline for rejected-request/read-only
checks. Keep byte equality and model-call-count assertions intact; terminal receipt reads alone
are not a blanket guarantee that every writer sharing the fixture has stopped.

When an Agent repeats a failed approach, stop code edits and read `repomemory/findings.md`. Classify
the failure as one of:

1. **Missing context/dependency:** record the requirement and exact diagnostic in `findings.md`, then
   add the durable instruction to the narrowest relevant file under `rules/`.
2. **Incorrect assertion/contract:** compare the assertion with approved requirements and design.
   Correct `stage-gates/03-execution-brief.md` before changing the test. Never weaken a valid safety
   or behavior assertion for a green run.

After the context fix, preserve the current diff, rerun the narrowest test, then the full suite. A
Git restart is allowed only from a named, verified commit after unrelated work is preserved. This
repository currently has no committed baseline, so `git reset --hard` and `git clean` are forbidden.

## Bundled skill validator context

`skill-creator/scripts/quick_validate.py` requires PyYAML (`import yaml`). Repository and bundled
Python environments do not necessarily include it. If that dependency is missing, use a dedicated
ignored validation environment such as `.uuma-local/skill-validation-venv` with PyYAML installed.
Run the unchanged bundled validator there, with UTF-8 enabled on Windows. Do not change product
dependencies, weaken the validator, or treat an import failure as a completed validation.


2026-10-09 confirmed WAL baseline execution context: diagnostic-v4 preserves actual
current before/after raw DB and WAL, all table records and observed MainThread-only state.
Before rollback test freeze, WAL contained135992 bytes of earlier committed fixture work;
after abort it was0 and mainDB differed4832bytes, while every actual table record remained
exact. Privately frozen before-edit source kept its WAL pending and mainDB unchanged.
The absent free pages disprove the earlier freelist hypothesis. Explicit successful
wal_checkpoint(TRUNCATE) BEFORE freezing the current-source byte baseline gave(0,0,0),
every record unchanged, and original unchanged post-write-fault/full-byte assertion PASS.
No transaction, runtime or physical guard weakened. Primary behavior source:
https://www.sqlite.org/wal.html (checkpoint moves earlier committed WAL into main file;
last-connection close can checkpoint). Optional dbstat probe failure remains preserved.

For a quiescent isolated rollback fixture in WAL mode, require completed pre-freeze
checkpoint with busy0/all frames copied/truncated, verify every table record unchanged,
and explicitly close the checkpoint connection. THEN freeze all raw DB bytes. Retain the
exact post-fault byte and data/history assertions. Never manually delete WAL/SHM, checkpoint
after freezing to make an assertion pass, touch live production databases, or omit earlier
failed logs. This completes missing fixture execution context, not a weaker assertion.


2026-10-09 correspondence generation execution contract correction BEFORE read-view repair:
generation-v1 retained19passes/two failures. Actual generation+real artifact compiler succeeded,
but immutable generated read compared populated referenced author Intents against raw empty
template slots and rejected the original input. The reader must derive the same deterministic
realization projection from the EXACT frozen author revision, preserving canonical author bank,
fixed target source, original group/full contexts and relation conditions. Retain all original
validated-call/hash/output/mapping guards; add exact original bank/context/formula/asset guards
for mapped output. Tampering with frozen source/context/projection must remain rejected.
The other new check incorrectly assumed a block_ids API field: comment_changes exposes actual
before/after documents. Verify stable IDs by the existing changed-block calculation on those
exact documents, plus unchanged association events through Undo/Redo/archive/restore. No guard
or assertion scope is reduced. No real model, scientific acceptance or native download claim.


2026-10-09 generation-v2 retained41passes/two fixture inspection failures. The actual
generated read succeeded, including the unchanged validated-output guard. Physical schema
PRAGMA proves studio_model_calls has started_at/completed_at, not created_at. list_comments
returns studio_changes raw before_json/after_json, not before/after or block_ids. Prepare
the added checks from these observed current fields, parse exact JSON and calculate stable
changed endpoints. Preserve both failed logs, all original assertions and all118/all11 scope.


2026-10-09 generation-v3:25PASS/one message-contract mismatch. Altering formula caption changes the rendered immutable Markdown, so the pre-existing immutable-version guard correctly rejects it before the new correspondence-context guard. Require the exact original immutable-version diagnostic for formula, and exact original-author-context diagnostic for other corruption variants. Retain exception/type and all content integrity assertions; no production change.


2026-10-09 static-v2: all correspondence/type/lint/history/structure checks passed; existing
response-review unit stopped at missing require('@/lib/studio-downloads'), before any behavior
assertion. Actual current component imports only studioFileUrl from that module. Execute the
unchanged shipped helper in the controlled unit loader, retaining every response/async/association
assertion. This is an import dependency fix; do not trigger browser downloads, add download
permissions, mock successful delivery, or run the paused native download test. Old test saved
before repair. Full regression remains required after the narrow response-review check.


2026-10-09 native independent audit context: audit-v1 stopped at studio_change_link_state.
Physical diagnostic proves77prior rows plus11new rows, keyed by change_id, not manuscript_id;
each newly saved operation records initial comment-link state even with no comment selected.
Before altering the verifier require ALL77previous rows exact, each new row tied to an actual
owned new change, no initial comment association, recorded_at_save origin and initial revision.
Keep comparison of all109tables and every other manuscript, immutable payload/inverse and original
source intact. Earlier diagnostic command used nonexistent studio_jobs.kind; real job_kind
observed. Failed quote-escaped read command did not run; use saved helpers for multiline SQL.
These are verifier execution-context fixes, not product edits or weakened acceptance.


2026-10-09 after1041PASS native exact audit, final completion audit adds the original
L2-condition corruption case. l2-before-v1 proves a real gap: mapped model-call input condition
altered with a recomputed request hash still passed immutable generated read. Existing bank,
context, formulas/assets and output guards all remain. Reader must recompute complete original
argument_context from the fixed raw author revision plus same deterministic target projection,
and require exact model input edges/endpoints/content/condition. Record before changing code,
retain new failing test and run narrow then full final source. Native current valid result must
remain readable; no rewrite of historical source, database schema or actual worker/approval.


2026-10-09 runtime refresh diagnostics before continuation: workspace has no jobs field; actual
studio_jobs.job_kind/status table was read instead. Verified own8879ancestry/commands before
stopping; original child+root now both authoritative-terminal and port absent. Stopping the
already-exited launch wrapper raised nonzero before relaunch; old3004/3005 remained untouched.
Restore only the expected absent owned service, not on timeout. Prior quiescent snapshot
comparison stopped relaunch: actual difference is10new ownMS/r19sample-candidate rows from
post-audit generated heading/citation UI reads; ALLother109-table records exact, no removed
cache rows, no new operation/model/job. Preserve original audit+screenshots in-v1, clone-v2,
rerun complete independent109table/native-history/generation audit with final reader source,
then require all current records EXACT before/after the service refresh. Keep each failed
attempt; the original immutable snapshots and byte/record guards are never relaxed.


2026-10-09 actual material focused-v1 generation fails because XeTeX image IO cannot find
280-character original fixture path. Independent short-path probe kept every staged input byte
and original artifact untouched, same XeTeX args/no-shell-escape,120-character paths compile0.
This proves runtime path context, not invalid images or missing dependency. BEFORE compiler
repair: when Windows complete input paths exceed240characters, compile in a newly owned short
temporary directory with exact same input files; preserve compiler log/PDF and all five fixed
output registrations at original immutable job location. No Windows security/path-policy
change, fixture/assertion reduction, deletion/reset of user work, or substitution of content.
Same original long-path test must pass, then full affected and complete suites and native QA.


2026-10-09 materials focused-v3:56PASS/one stage CAS fixture mismatch. Actual manuscript revision0/stageWHOLE_PAPER_REVIEW and author document revision1 are distinct authority axes. Generated materials, complete tables, frozen-byte corruption/live-source isolation all preceding assertions passed. Before fixture correction require set_stage CAS against actual manuscript revision, keep original author input_revision1 for GENERATE/PACKAGE. Do not merge axes or weaken conflict/stage guards. Preserve failed log; narrow then affected/full suite.


Correction to the preceding materials-v3 context note: the actual observed manuscript revision was2 (not the mistakenly written0), workflowWHOLE_PAPER_REVIEW; author document revision1. The requirement to read the separate actual manuscript CAS basis is unchanged. Original full assertions now8PASS in focused-v4, including independently recompiling the delivered package. No production stage/CAS guard altered.


2026-10-09 materials visual QA-v1 inspected all3actual rendered pages. No missing image/table data, but a ten-row CSV table split with one final row isolated on next page. Before layout correction retain originalrendered3pages/hash; keep smallcomplete tables together with original title and use continuation title for genuinely multipage tables. Do not truncate, reorder, duplicate values or change original source. Rerender after change; narrow/affected/full tests remain required.


2026-10-09 native materials independent audit-v1 stops before PDF/ZIP audit because verifier
assumed Studio call status DONE. Exact owned call studio_model_call_5cae693a7b614e4c80c61637f4cafe01
is VALIDATED, paragraph_realization, no error, actual completed timestamp and declared
TEST_FIXTURE_MATERIALS_NATIVE. DONE is an unrelated scientific acquisition worker status;
do not merge status axes. Before verifier correction require exactly VALIDATED plus actual
contract/task/input/output/mapping provenance, one fixture call and zero remote models.
Retain audit-v1 source/failure and all109table/byte/author/ZIP/fullcells guards. No product
change, schema or scientific approval; real native GENERATE/PACKAGE both SUCCEEDED.


2026-10-09 native downloaded PDF visual QA-v2: inspected all3real pages, SHA
c5c4aa8679b430aa3bab7b61e71da71704e1aefacf679502e9b36f15af04b060.
All30original table rows/secondSheet/3images are present, but compact table title lacks
trailing paragraph break: title shares the table baseline, pushing table to the right;
third-page Markdown extends beyond physical page edge. Fixed .9linewidth widths also
omit cell padding/rule budget. Preserve this immutable v1/native25file ZIP and all3renders.
BEFORE repair require original title above table, columns budget actual linewidth minus
padding/rules, original complete ordered cells unchanged. Add independent Poppler word
geometry to real-PDF integration test (all words within page margins and each table title
above first row). Do not bless visible clipping from a text-only PASS, rewrite old version,
truncate/reorder cells or weaken prior source/byte/schema/permission guards. Run narrow,
full regression and native new immutable generation/download/independent compile/visual QA.


2026-10-13 isolated preview restart receipt context BEFORE recovery-v2:
Build receipt `before` fingerprints the ORIGINAL source workspace, including
its original dist, to prove that isolated building did not mutate user work.
It is NOT the isolated compiled output fingerprint. `dist_files` is the complete
ACTUAL isolated output hash map. Require every original before hash unchanged,
every copied non-dist source hash exact, every actual dist_files hash exact AND
actual dist membership exact, plus current acceptance source vector before start.
Do not omit either authority or reuse original BUILD_ID paths for the new dist.
Preserve original failed helper/diagnostics. On confirmed absent owned runtime,
start only the verified existing isolated preview and serve-only backend; no
seeding/reset, old scientific/model rerun, remote fallback or broad process kill.
Retain every raw database-byte/all-table/job/ownership assertion after recovery.
Run narrow recovery then full affected deterministic suite after this context fix.


## 2026-10-13 G09 native live Evidence source-reader gap

Native current Studio evidence cards expose only excerpt/external URLs and display original
unavailable despite exact skeleton_id/unit_id/digests/page/section/sequence and exact original
PDF/parse records. Frozen generated-reference reader remains working. Keep the native failing
DOM/screenshots in .tmp/scholar-g09-native-v2/proof/live-citation-reader-original-unavailable.*.
Implement an on-demand manuscript-scoped Evidence original-source reader using the SAME strict
freeze_source identity/excerpt/location/file guards. Return exact units, adjacent/full parsed
text and versions; never guess the latest Paper/Skeleton/file or synthesize missing provenance.
PDF opening must bind the reader's context digest, recheck original bytes and scope, and reject
changed/foreign sources. No author/citation decisions, Gen, stage/schema/scientific approvals
are implied by source reading. Preserve all old109 tables/20artifacts and new206comments/4link
events. Source files backed up in .tmp/scholar-g09-source-reader-repair-v1/before.

Windows search execution context: PowerShell does not expand glob path arguments to rg.
Use an existing directory plus rg -g 'test_studio*' (or an exact known file), never pass
research* or test_track_first*.py as a literal path. Prior failed searches were read-only.
The actual read module is studio_read_views.py, not studio_read.py; use imported source names.


2026-10-13 G09 source runtime refresh-v1: all six prior PID/creation/command/parent rows
were verified before stopping. Stopping owned frontend listener41060 successfully exited
its three npm/cmd launchers too. Next per-process check correctly found40796 missing and
stopped the helper before backend stop/restart; no new server started. Fresh diagnostic
proves all four frontend PIDs absent and both backend PIDs exact. Preserve v1 helper and
all-table snapshot. A followup nested PowerShell port read lost $_ expansion and failed;
process output before that read is valid. Use saved Python subprocess arguments for ports.
V2 must require exact original DB/all109 rows, allfour frontend PIDs absent and port3008
absent, both backend identities and8881 listener exact, all new original/copied source and
dist hashes exact. Stop only these preverified backend processes, skipping only an already
authoritatively absent known child after its verified parent's stop. Recheck absent old
chain and ports before starting new owned processes. Never substitute a reused PID or
restart on timeout. No source/data assertion, model guard or original scope relaxed.


2026-10-13 G09 readable reply-diff contract BEFORE repair: current native review dialog
renders raw [@evidence_ID] markers. Keep authoritative raw baseline_to_target_diff, actual
change rows, evidence IDs, PDF locations and all assertion validation unchanged. Add a
separate numeric display diff from EACH verified version's own references, plus separate
baseline/target citation source labels (exact original source page/unit/version). Identical
numeric printed text can still have changed citation identity: explicitly retain raw diff
and show both fixed source lists, never report no changes merely because display diff is
empty. Evidence display text may be numbered separately but must not change raw evidence
digest or accepted assertion identities. Missing citation titles use local candidate ordinals
instead of internal IDs, without guessing bibliographic identity or editing author records.
Preserve old reports and failed raw display proofs. Full reply/current-generation workflow
and original118/all11 scope still required; formatting is not completion evidence.


2026-10-13 current-generation input auditor v1 failed on manuscripts before model/readiness
execution. Exact RO diagnostic proves ONLY original A updated_at advanced during native
author saves; manuscript revision5, stageWHOLE_PAPER_REVIEW, writingINTERNAL_REVIEW, original
track/title/scope/science/blocker fields and all other manuscripts exact. Authorrevision is
separate axis. V2 permits only that timestamp for actualA; retain every other manuscript
field exact, all other109 table guards and source/author/old artifact invariants. Preserve
v1 helper/exclusive directory. No native action replay or product guard change.


2026-10-13 v5 generation auditor v1 reached manuscript identity check after exact11calls,
newversion/5artifacts/fullbyte checks. Fresh RO diagnostic: actual successful generation
publication advances A manuscript revision5->6 and updated_at; WHOLE_PAPER_REVIEW,
INTERNAL_REVIEW and all otherfields/othermanuscript exact. V2 requires exactly+1 for
the single independently SUCCEEDED generation, distinct authorrevision remains62.
Do not hold the manuscript CAS axis fixed through actual publication or merge axes;
retain all originalcalls/history/version/artifact/baseline guards. Preserve failedhelper.


2026-10-13 G10 isolated existing semantic data copy: original104-table snapshot and rawDB
matched prior completed readback. Initial prep wrongly assumed this data had the same109
tables as citation fixture, failed AFTER only declared additive initialization. ROdiagnostic
proves105tables: ONLY new empty skeleton_source_outlines, catalog12->13 metadata; every
original104table row exact, no seed/newmodel/approval. Fixture table counts depend on the
components previously initialized;109 is not a universal schema count. V2 reuses the single
alreadycreated owned copy, requires exact105/newemptytable and every originalrow, known
version12->13 only, originalDB digest unchanged. Preserve failedhelper/copy and diagnostic;
never createanothercopy or alter rows/assertions to make it pass. An inlinequotedSQL probe
failed before execution; use saved multiline helpers for SQL. Run narrowprep then affected
full deterministic suite. Actual native G10 and original118/all11 still required.


2026-10-13 G10 native explicit-unknown source label BEFORE repair: old semantic source
records have null parse_run_id/file_version_id/PDF digest. Backend correctly returns
precise Paper/Skeleton/unit plus no PDF; StudioSourceContext unconditionally displayed
解析版本已固定. Keep native original proof and source raw backup; render解析版本未记录
when exact parse identity absent. Full-text summary must distinguish known parse from
preserved original units. Do not invent versions/PDF, rewrite source records, infer
scientific approval or reduce completeness requirements. Known G09 parsed-source labels
remain the same. Native unknown/known checks and all frontend unit/type/lint/build required.


2026-10-13 G10 final native audit context: initial frozen copy had105tables.
First real research annotation initializes the shipped research_discussions SCHEMA,
adding exactly4tables: requests1/annotations1/messages0/jobs0, now109. Failed v1
assumed initial105 after native use; retained raw helper and RO diagnostic. Verify
the exact four names/counts, all old105 data rows, known native append records and
exact sqlite_sequence increments12->13 plus annotation1. This is initializer and
bookkeeping context, not permission to relax data preservation, invent rows or
rerun any successful UI/model/terminal fullsuite. Keep source-original/G09 raw
DB hashes and original SEALED Snapshot fully identical. G10 only its unchanged
original software group scope; original118 and full11/science remain incomplete.


2026-10-13 G10 final native audit context: initial frozen copy had105tables.
First real research annotation initializes the shipped research_discussions SCHEMA,
adding exactly4tables: requests1/annotations1/messages0/jobs0, now109. Failed v1
assumed initial105 after native use; retained raw helper and RO diagnostic. Verify
the exact four names/counts, all old105 data rows, known native append records and
exact sqlite_sequence increments12->13 plus annotation1. V2 then rejected two concurrent shared default-endpoint source changes. RO byte comparison proves ONLY one default endpoint literal changed in each model_gateway.py/skeleton_dspy.py; reversing the literal in memory exactly reconstructs both old hashes. No product file reverted or remote call permitted. V3 requires those exact old/new hashes and all175 other sources unchanged, freezes all177 current bytes and pairs with current-full-tests-v2. This is initializer and
bookkeeping context, not permission to relax data preservation, invent rows or
rerun any successful UI/model/terminal fullsuite. Keep source-original/G09 raw
DB hashes and original SEALED Snapshot fully identical. G10 only its unchanged
original software group scope; original118 and full11/science remain incomplete.


2026-10-13 current-default-endpoint regression: current-full-tests-v2 terminal
1077PASS/1FAIL/20warnings; unknown-or-other-scope parent returned404 but rawDB
bytes differed at change counter byte27 after preceding legitimate discussion.
Earlier full G10 suite1078PASS. Exactly two shared source edits are default URL
literals; all175 remaining backend files exact. No causal claim connects URL to
this rejection failure. Retain full failed log/source context; run the unchanged
single rejection test once with diagnostic exception-state capture. Existing
assertions404/rawbytes/callcount1 remain unchanged. Do not count a narrow pass as
full current-suite completion, ignore the failure, or rerun any native/model job.


2026-10-13 rejection physical-baseline execution contract: unchanged isolated
test passes1/1. Full-suite failure remains retained1077/1. Database connect enables
WAL; discussion shutdown drains threads but does not establish a checkpointed
physical .db baseline while other fixture SQLite connections can remain open.
Before comparing rejected requests against main-file bytes, explicitly checkpoint
the completed legitimate writes and require wal_checkpoint(TRUNCATE)==(0,0,0).
This strengthens setup: no outstanding committed WAL frames may be hidden by the
physical baseline. Preserve every404/rawDB-equality/modelcall-count1 assertion;
no product mutation or fixture removal/rewritten expected response. Exact original
test raw backup retained. Deferred checkpoint is a supported failure mechanism;
the original full failure's specific connection owner remains unproved. Run the
affected source-bound discussion suites, then full current suite under frozen
source AND tests hashes; neither a narrowpass nor new setup erases originalfailure.


2026-10-13 G11 single SCREEN worker context: v1 constructor refused role screen
before any worker execution/model call. Shipped ROLE_QUEUES has network/parser/model;
model owns all four MODEL_* queues. Preserve failed helper, exact frozen request and
before snapshot. V2 uses model and requires ALL four possible model queues contain
only the one newly created owned job. Require exact v1 pre-execution DB snapshot,
READY/attempt0/fencing0 again. No old worker or successful phase replay allowed.


2026-10-13 G10 report seal context: v1 rejected copied vinext manifest before
report directory creation. Build receipt before vector includes untouched original
production dist; copied rebuild intentionally uses different API8886 and its own
dist_files76 vector. V2 requires ALL original source/dist before hashes unchanged,
copied source hashes identical, and ALL76 actual copied outputs equal dist_files.
Do not compare new copied bundle against old untouched production bundle. Preserve
failed sealer and complete receipt. No rebuild/fulltest/DB/native action replay.


2026-10-13 G11 actual MinerU attempt2 ended RETRY_WAIT with CUDNN allocation
failure in Paddle OCR. User explicitly requested GPU before any CPU retry ran.
Torch actual CUDA matrix computation and Paddle GPU availability verified on
RTX 4070 Ti; approximately 11GB free before retry. The original magic-pdf.json
remains byte-identical. An owned configuration selects device-mode cuda through
the child environment only; the bridge's CPU compatibility branch is not used.
Attempt3 may execute only this same native-retried owned job at READY attempt2 /
fence2, retaining the same original PDF, incomplete candidate, reference6 correction,
all previous failure evidence and history. No inherited model/parser jobs replayed.
Fresh actual GPU publication must satisfy all original six-reference quality checks.


2026-10-13 G11 attempt3 genuinely selected CUDA and initialized every original
model, then ended RETRY_WAIT on a 22.1MiB host image allocation before inference.
Windows committed memory afterwards was 40.53GB of 44.54GB, with about 10.8GB
physical available. No publication occurred; all original records/correction retained.
Attempt4 will retain CUDA, every formula/table/OCR/layout model and every PDF page.
Installed MinerU explicitly supports VIRTUAL_VRAM_SIZE=7 to select sequential
all-page inference instead of batch_ratio4. Child-only CUDA_MODULE_LOADING=LAZY
and Paddle auto_growth are documented vendor memory-allocation strategies, not
package, model, machine/pagefile or global configuration changes. No process killed.
Exact same native-retried owned READY attempt3/fence3 target and six-reference
quality requirements remain mandatory; no failure fixture can substitute success.


2026-10-13 G11 attempt4 selected CUDA with sequential-all-page/LAZY/auto_growth,
then terminal access violation in torch loading original MFD weights. Retained
failure/candidate/correction/all history, no publication. Isolated ZIP CRC and
actual ordinary vs mapped vs GPU-transfer loading verified every595 state tensor
equal and exact349867002B original weight SHA41029d5a...5808fc unchanged. New
bridge opt-in uses supported torch mmap for existing ZIP checkpoint paths, retaining
explicit mmap arguments and all original model flags. Actual bridge diagnostic,
syntax/ruff and exact byte-restoration source guard PASS. This does not prove the
crash cause or complete G11; attempt5 must parse the exact same original PDF using
all original models and six-reference quality checks. Only current owned native
READY attempt4/fence4 target is allowed. LLM/history/science rows remain protected.


2026-10-14 G11 next GPU context: attempt5 is terminal RETRY_WAIT/fence5/no lease.
The 02:17Z NVML error was retained. Current actual NVIDIA query and pinned Torch
CUDA matrix compute both pass, GPU free >10GiB and measured Windows commit
headroom >5.5GiB (prior attempt3 approximately4GiB). These are fresh conditions,
not a successful parser claim. Permit exactly one native-retried original job
attempt6 under the same CUDA/sequential/LAZY/auto_growth/mmap settings and all
original models; no CPU fallback, remote language models, original data replay,
weaker six-reference quality assertions, global configuration or driver changes.
Preserve failed attempts1-5, corrected reference6 action/candidate, old versions,
and source/science/model history. A failed/timed-out observation never authorizes
another execution; inspect the same live handle and terminal receipt instead.


2026-10-14 GPU attempt6 succeeded once; do not rerun it. Independent audit v1/v2
stopped on auditor contract mistakes, not parser failure. Current acquisition
publication intentionally stores parsed_path=manifest.structured_path (optional,
here null), and parsed_digest is canonical digest(manifest,blocks,references), not
a file SHA. The bridge's intermediate rstv4-parse-result is pre-normalization:
normalize_mineru_result re-reads authoritative content_list, splits DOI/body and
reference sections, and converts page_idx to physical one-based pages. The audit
must independently re-normalize those retained actual artifacts, preserve the
explicit correction action list, and verify canonical digest, normalized body
texts, all six references and every protected row. Never weaken assertions or
substitute raw pre-normalization blocks, replay GPU/model work or alter data.
Current gate remains verification/pending_review; v3 restarts this read-only audit
using the corrected execution/storage contract. All failed audit helpers retained.
