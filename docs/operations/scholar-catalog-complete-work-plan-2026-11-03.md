# Scholar / RSTV4 Catalog: complete work plan and priority review

Updated: 2026-11-03, Asia/Kuala_Lumpur.

**Latest evidence review, 2026-11-05** — Read the [independent W01–W34 audit](scholar-catalog-w01-w34-independent-audit-20261105.md) for current item verdicts, reproduced errors, retained evidence and correction sequence. Earlier baseline counts remain historical.

**Status reconciliation, 2026-11-04:** Another agent team has completed additional work. The historical baseline below must not be used as the current runtime state. See [Teamworks reconciliation and updated W01–W34 positions](scholar-catalog-teamwork-reconciliation-2026-11-04.md). The combined Reading release is now selected and the original native Skeleton is persisted, while its whole-paper view and deep purpose output remain incomplete in the directly inspected canonical owner. Preserve the original plan and reuse completed work.

Status: user review draft. Implementation Goal remains **PAUSED**. The user requested a detailed inventory, completion criteria, solution approach and ordering. This document does not resume implementation or authorize a separately held model retry. Existing scheduled work has not been cancelled.

## 1. Scope and how to use this plan

This is the work breakdown for this thread's Scholar FieldKG availability and global Catalog workflow: verified full-text acquisition, automatic initial reading, open multi-Theme understanding, optional research mappings, semantic search and aggregation, value-driven PaperSkeleton deep reading, source/version reuse and final delivery. It is not a new project-wide redesign of all UuMA specialists.

Each item below states its current evidence, proposed priority, method, dependencies and observable completion condition. **Implemented** does not imply **deployed**, and **deployed** does not imply **accepted using actual papers**. An item with existing implementation should first reuse it and close the evidence gap; it should not be rebuilt from scratch.

Priority definitions:

- **P0 / first usable delivery:** stable full-PDF initial reading and an informative Catalog. Address the high-value shared recovery cases, then prove useful runtime behavior. Processing the entire library is not a prerequisite for this first delivery.
- **P1 / next delivery:** complete the agreed semantic discovery workflow and actual full PaperSkeleton workflow. These remain part of the original final scope.
- **P2 / final delivery:** portable full evidence, actual import/adoption and final operational acceptance. A dependency needed earlier moves forward without pulling the whole group forward.
- **DEFER:** a later task, not cancelled or silently counted as completed.

Proposed order is for discussion; the user has not yet approved this new sequence.

## 2. Confirmed decisions: keep these fixed

1. A verified readable full-text PDF is required before initial or deep reading. A title, abstract or provider page does not qualify.
2. Every new import receives an automatic initial-reading intent, independent of a Field, Topic, Collection or View. Source acquisition must finish before reading.
3. All automatic reading and eligible backfill run at **00:00–08:00 Asia/Kuala_Lumpur**. Explicit manual requests have priority at a safe work boundary.
4. Initial understanding can be the final chosen depth for the current purpose. A recommendation is separate from consent to execute deep reading or citation expansion.
5. Each paper can have many Themes. The vocabulary is open, including subjects not represented in current research Fields or Topics.
6. Candidate Themes are immediately visible, searchable and aggregatable, with evidence and review status.
7. Direct Theme research mappings target **Field or Topic**. Track/RQ/Collection relationships are separate workflow links.
8. The existing **PaperSkeleton L1–L4** is the deep-analysis framework. Initial dimensions preview that framework; they do not create a second analysis system or 22 new sequential layers.
9. Theme counts overlap. Unique-paper totals use paper IDs; counts across Themes must not be added as a unique-paper total.
10. New scientific interpretations, semantic relations and mappings remain candidates until reviewed. Preserve quotations, qualifications, versions and correction/reversal history.
11. Authored Scholar research content and project artifacts use English; the existing interface language is preserved.
12. Night reading continues under the user's existing decision concerning NAS rescue. Implementation work must preserve that rescue and existing source data.

## 3. Current baseline and limits of the evidence

The latest directly inspected queue observation, on 2026-11-03 around 21:28–21:31 Malaysia, was:

| Initial-reading job state | Count |
| --- | ---: |
| SUCCEEDED | 3 |
| READY | 116 |
| NEEDS_HUMAN | 21 |

These are counts of these reading jobs, not all papers and not a whole-project completion percentage.

- The observed live Reading release is `catalog-12c4571ce546`.
- Combined repair candidate `catalog-48cece41023e` is prepared, not activated. Sixteen focused candidate tests passed. Its prepared night coordinators and activation guards have additional bounded fixture evidence; these are not real recovery results.
- One exact digest admission is scheduled as `UuMA Scholar Digest Recovery v653` for **2026-11-04 00:05:05 Malaysia**. The latest observation found it Ready and not yet executed. The future task outcome must be inspected, not assumed.
- Two exact Theme failures and four exact dimension-state failures have prepared night admission helpers; they are not scheduled or resolved.
- The original full deep sample retains substantial partial output, but complete content/purpose publication and a full final archive/import have not been demonstrated.
- Original PDF/parser bytes are retained. A local detached-database test accepts the relocated real PDF with the unchanged source guard and rejects tampering. Production location mapping and server-side adoption are not proved by that test.
- Global semantic retrieval, candidate-index and API/MCP implementations have prior software evidence. Their current complete library indexing, integration and actual scientific usefulness require verification. An older document's historical MISSING label must not be treated as proof that the feature still needs to be written from scratch.
- FieldKG server migration is recorded as completed. Final health and client consumption still need a final probe; do not migrate it again as routine follow-up.

### The 21 currently held initial-reading jobs

| Error class | Count | Present recovery position | Proposed treatment |
| --- | ---: | --- | --- |
| Invalid dimension support state | 4 | Exact cases pinned; repair and night admissions prepared | P0, task W03 |
| Digest omits/reorders supplied inputs | 3 | Repair implemented; only one exact admission currently scheduled | P0, task W05 |
| Theme-role cites an unsupplied quotation ID | 2 | Exact cases and night admissions prepared | P0, task W04 |
| Malformed JSON/non-object output across reading/recovery/digest tasks | 5 | Mixed cases, including already-used recovery paths | Triage under W06; do not blanket-reset |
| Deep-read rationale or supported-dimension binding | 3 | Scientific meaning needs source-specific inspection | Triage under W06 |
| Source block/quotation/foreign-selector mismatch | 2 | Requires exact original evidence verification | Triage under W06 |
| Synthesis dimension lacks source-backed observation | 1 | Separate synthesis contract failure | Triage under W06 |
| Preview patch did not establish the original signal | 1 | Prior correction is insufficient | Triage under W06 |

The first three classes total 9 jobs. Prepared recovery is not a guarantee that those 9 will succeed. The other 12 should have clear visible held states; they need not all be repaired before first delivery, but cannot silently disappear from final scope.

## 4. Detailed work items

### A. Runtime and the current held jobs

#### W01 — Reconcile the already-scheduled digest recovery

- **Status / priority:** scheduled, actual outcome pending; P0, first operational action after its window.
- **Method:** inspect the task execution result, per-case receipt, durable owner request and exact job/model events. If admitted, follow that same job and model operation; do not submit it again because a local receipt or observation is missing. If it failed, classify the actual failure before another action.
- **Done when:** the scheduled attempt has an evidenced outcome; any successful admission is bound to the original source/job/call and is either completed or visibly held with a specific next action.
- **Evidence / dependency:** task result plus owner request/event history; no dependency on a new deep retry. W02 must preserve this task's pinned release until its admission is reconciled.

#### W02 — Activate the tested combined Reading repair release

- **Status / priority:** fixed candidate and guarded activation prepared; P0.
- **Method:** reuse the existing candidate and manifests. Recheck current pointers, source hashes, exact task/process ownership and a transactional idle boundary. Switch once to the combined release; verify the actual loaded package and healthy unique worker. Retain the previous release and a scoped rollback receipt. Preserve active/manual work and the Web component.
- **Done when:** the owned Reading worker is demonstrably running the intended candidate, existing data/history are preserved, and the current rollback path is concrete. Merely writing a release file is insufficient.
- **Evidence / dependency:** activation receipt, fixed manifest and actual runtime identity. Depends on W01 reconciliation and an idle boundary. Do not execute both Theme-only and combined activation paths.

#### W03 — Recover four invalid initial dimension states

- **Status / priority:** source-bound repair, four pinned cases and night coordinator prepared; P0.
- **Method:** use each original quick-read payload and evidence. Ask the scoped repair task to decide only affected states and rationales using the supported profile; UNKNOWN remains valid. Reuse all unaffected output and retain both original and repair receipts. Verify the physical PDF during the allowed window before admission.
- **Done when:** each admitted case passes the unchanged evidence/coverage validator and continues through its actual initial workflow, or returns a clearly recorded unresolved cause. Do not silently map PARTIAL to SUPPORTED or reset retry history.
- **Evidence / dependency:** per-case durable admissions and actual worker outcomes; depends on W02 and W07 source eligibility. A helper's test success is not a recovered paper.

#### W04 — Recover two Theme-role evidence-reference failures

- **Status / priority:** exact cases and combined-release admission wrapper prepared; P0.
- **Method:** retain the original whole-paper candidate and supplied quotations. Use the distinct source-bound correction to select only valid evidence IDs, then rerun normal role/evidence validation. Preserve previously successful synthesis and roles.
- **Done when:** corrected role decisions cite supplied original quotations and the original jobs proceed without duplicate successful calls. Unresolved cases remain explicit.
- **Evidence / dependency:** exact original/repair receipts, retained quotation identity and worker events; depends on W02 and W07.

#### W05 — Resolve the three digest coverage cases

- **Status / priority:** repair code exists; one scheduled case and two additional cases needing exact review; P0.
- **Method:** reconcile W01 first. Review the other two original failed calls against their actual source and complete supplied-input sequence, then use eligible scoped admissions. Check that summaries account for every supplied part in the required order while preserving saved source results.
- **Done when:** no omitted/reordered supplied parts are accepted; each of the three cases has a demonstrated resolution or a specifically recorded remaining blocker. General repair implementation alone does not close all three.
- **Evidence / dependency:** complete input coverage, actual digest receipts and job outcome; W02 where required, plus source verification.

#### W06 — Triage and gradually resolve the other twelve held jobs

- **Status / priority:** error groups identified; triage P0, broad automatic recovery DEFER/P1.
- **Method:** inspect one original failed payload and saved response per error class before designing another path. Separate syntax failures from missing scientific support and invalid evidence. Reuse existing compatible recovery contracts. Record a clear reason and next action for jobs that remain held; propose a new contract only for a real recurring need.
- **Done when:** all twelve have an accountable state and plan; repairs actually satisfy their source contracts. First delivery may retain visible holds. Final disposition must be resolved or explicitly accepted by the user as deferred, rather than falsely marked complete.
- **Evidence / dependency:** per-job diagnosis/outcome inventory. Do not let one held paper block unrelated READY jobs, and do not treat a failed repair as permission for unlimited new calls.

### B. Stable initial reading and resource behavior

#### W07 — Prove the full-text readiness gate on the actual workflow

- **Status / priority:** guards implemented and software-tested; actual final workflow acceptance remains; P0.
- **Method:** reuse canonical paper/PDF identity and current parse checks. Confirm missing, unreadable, changed or quarantined PDFs remain in acquisition/source review. Only eligible readable full text enters initial or deep reading.
- **Done when:** a genuine eligible paper proceeds, and representative ineligible cases expose the missing source stage without publishing abstract-only content analysis. Existing source evidence is reused.
- **Evidence / dependency:** source/parse identity and actual stage/readback; prerequisite for reading and semantic source consumption.

#### W08 — Complete automatic import and historical backfill behavior

- **Status / priority:** import intents and staged source/reading queues exist; backlog incomplete; P0.
- **Method:** verify every imported canonical paper has the appropriate initial intent, independently of a View or Field. Mark historical missing work by stage and let bounded night batches advance it. Deduplicate paper/source/version work across Views.
- **Done when:** new imports enter the right stage once, historical missing stages are visible and progress over successive permitted batches. The eventual inventory accounts for each eligible record as processed, pending or explicitly held; queue creation is not reading completion.
- **Evidence / dependency:** canonical import/intent/job history and visible inventory; W07 and W09. Full backlog drainage is later operational work, not a first-delivery gate.

#### W09 — Verify night policy, manual priority and fair resource sharing

- **Status / priority:** policy implemented; parse/reading fairness adjustment deployed with final night observation pending; P0.
- **Method:** observe an actual 00:00–08:00 Malaysia window, including safe handling of the end boundary. Confirm explicit manual requests take the next safe priority, while automatic parsing, initial reading and indexing do not starve each other. Pause/quarantine and resource limits must remain effective.
- **Done when:** actual events show eligible automatic work advances without daytime automatic admission, manual work receives priority at a safe boundary, and the old parse backlog no longer indefinitely postpones READY initial reads.
- **Evidence / dependency:** timestamps and claim/checkpoint events, not a simulated clock alone; W08 and existing worker ownership.

#### W10 — Verify resumability and reuse of saved successful results

- **Status / priority:** durable operations, receipts and fencing exist; full actual continuation still incomplete; P0.
- **Method:** resume the same operation after a wait/restart; reuse successful parse, initial, synthesis and deep parts. Confirm a pending model by its actual handle before making a restart decision. Preserve input/source/profile identity and distinguish uncertain observation from terminal failure.
- **Done when:** a real continuation advances with original result history intact and no duplicate dispatch of completed work; stale source/profile inputs are rejected or explicitly versioned.
- **Evidence / dependency:** operation/request IDs, fencing and returned-event lineage; relevant to W01–W09 and the original deep task.

#### W11 — Confirm supervised worker operation and actionable errors

- **Status / priority:** scheduled worker/runtime mechanisms present; final integrated acceptance remains; P0.
- **Method:** verify a single owned worker, real task/process identity, durable state and actual exit/health reporting. Surface queue, running, partial, held and source-review states with actionable reasons. Reconcile a stopped owner before restarting it; preserve unrelated services.
- **Done when:** the user can tell whether work is queued, progressing, stopped or requires action, and recovery follows the original jobs without duplicate workers.
- **Evidence / dependency:** task/process observations and UI/API status; W09–W10. A registered task alone is not runtime success.

### C. Initial understanding, Catalog columns and research mappings

#### W12 — Verify the reusable initial-reading content card

- **Status / priority:** existing initial publication and UI evidence; current final acceptance remains; P0.
- **Method:** reuse the current question/problem, claims/contribution, method, material/data, results and limitations card. Retain source spans, confidence/uncertainty and actual source coverage. Keep journal/provider metadata separate from inferred content.
- **Done when:** a real completed initial read has a useful card linked to the correct PDF/parse, and missing information is explicit rather than invented. It is accessible from the canonical Catalog record.
- **Evidence / dependency:** real published card and located quotations; W07 and actual initial completion.

#### W13 — Verify shared PaperSkeleton dimension binding at initial depth

- **Status / priority:** shared 22-dimension profile and initial views have implementation/example evidence; P0 acceptance.
- **Method:** check that initial observations reference the shared versioned profile, real source spans and intended L1–L4 responsibilities. Preserve SUPPORTED/UNKNOWN/unassessed distinctions; do not invent completed Skeleton unit IDs before deep reading.
- **Done when:** all assessed dimensions expose their evidence and limits, and the same definitions can be followed into deep outputs. Dimension count alone is not coverage proof.
- **Evidence / dependency:** profile/version/evidence readback; W03 and W12 where relevant. New dimensions are deferred until an actual need is agreed.

#### W14 — Verify reading disposition and understandable deep-read reasons

- **Status / priority:** disposition/reason logic exists; real final examples and deep purpose are incomplete; P0 for initial use.
- **Method:** distinguish initial understanding sufficient, deeper reading recommended and more information required. Each recommendation should explain source evidence, observed feature, purpose/value, unresolved detail and expected Skeleton output. Keep the system recommendation separate from a user execution decision.
- **Done when:** the researcher can understand why to deep-read or stop, a missing reason is visible, and a recommendation alone creates no unauthorized deep task. One useful concrete example is included in the UI/help.
- **Evidence / dependency:** actual card/reason/job history; W12–W13. Addresses the three held rationale/binding cases through W06 rather than weakening their validators.

#### W15 — Verify open multi-Theme display, search and coverage roles

- **Status / priority:** prior real candidate/UI evidence; current integrated acceptance remains; P0.
- **Method:** show all applicable Themes per paper, including unmapped subjects. Retain CENTRAL, SUBSTANTIAL and PASSING_MENTION where supported, candidate/reviewed state and initial/deep evidence provenance. A review paper can span many domains.
- **Done when:** a real paper has multiple visible/searchable labels; unmapped labels participate without creating an artificial Field. Scope/role evidence is inspectable and brief mention is not automatically presented as the paper's main topic.
- **Evidence / dependency:** genuine source-backed labels and Catalog queries; W04 and actual initial results. Previously demonstrated behavior is checked, not rewritten.

#### W16 — Verify Field/Topic mappings and controlled vocabulary review

- **Status / priority:** mapping/review mechanisms have software and limited example evidence; P0 for basic mapping visibility, P1 for complete review lifecycle.
- **Method:** retain optional direct Theme-to-Field/Topic proposals and visible unmapped states. Keep Track/RQ/Collection use separate. Use explicit review for mappings, aliases and merges, with history and compensating reversal; candidate similarity alone cannot apply a merge.
- **Done when:** a label can remain unmapped, a reviewed mapping is distinct from a proposal, and rejection/reversal survives reload without altering original evidence.
- **Evidence / dependency:** actual proposal/review/readback and scoped lifecycle check; W15. No new Field should be created merely to enable global content discovery.

#### W17 — Verify Catalog columns, detail panels and saved preferences

- **Status / priority:** columns/UI already developed with prior rendered evidence; final exact current behavior and default choices require review; P0.
- **Method:** verify Themes, Understanding, Reading disposition, optional Field/Topic mappings and Next action against true source/job/result state. Preserve existing technical columns and saved layouts. Keep detailed reasons/evidence expandable. Journal/Publication Venue is distinct from import Source; inferred paper type remains a candidate.
- **Done when:** the real record shows the correct reading stage and next action, partial deep work is not labelled complete, saved preferences persist and the interface remains usable with broad-label papers. Missing venue/type data stay missing.
- **Evidence / dependency:** current UI readback and save/reload behavior; W11–W16. User choice: default visibility of optional Field/Topic, Paper type and Venue columns; no schema expansion is required merely to choose a layout.

#### W18 — Verify counts, filters and semantic group statistics

- **Status / priority:** distinct-paper ANY/ALL/grouping mechanisms implemented; final real behavior needs acceptance; P0.
- **Method:** count unique paper IDs within each Theme and across unions/intersections. Show that per-Theme counts overlap. Preserve candidate/review/role filters and reviewed alias/merge semantics. Distinguish an aggregation group from an exclusive classification.
- **Done when:** a paper belonging to several Themes appears correctly in each set and once in the overall union; ANY/ALL yields the expected genuine records with clear filter scope.
- **Evidence / dependency:** representative real overlapping examples and deterministic count checks; W15–W16. No new universal paper-quality score.

### D. Global full-text search and semantic aggregation

#### W19 — Complete actual full-text semantic retrieval and index coverage

- **Status / priority:** real embedding adapter, source-fenced core, index and integration code have software evidence; current library-wide runtime acceptance incomplete; P1, after basic initial workflow.
- **Method:** first inspect the existing deployed components and index progress. Reuse existing BGE-M3 service and source-bound rebuildable index; fill only missing integration. Index original passages and eligible candidate labels, including unmapped domains, through the approved bounded night/resource policy. Preserve model generation, source version and current coverage.
- **Done when:** a bounded real natural-language query returns relevant located quotations from eligible papers, including an example beyond label substring matching. Results distinguish semantic/lexical basis and indexed, pending, stale or unavailable source coverage. An empty index is not represented as complete semantic search.
- **Evidence / dependency:** actual index status, model/source identity and bounded real query; W07, W09 and actual parsed sources. Neither whole-corpus indexing nor a new provider is assumed for a first bounded acceptance.

#### W20 — Complete evidence-backed semantic relation proposals

- **Status / priority:** bounded candidate-neighbor cache and proposal paths have software evidence; real integrated use remains to be checked; P1.
- **Method:** reuse the existing bounded incremental aggregation, not an unbounded pairwise operation on each query. Display candidate relation/similarity with evidence from both sides, distinct paper counts and partial-index scope. Route reviewed alias/merge/mapping actions through W16.
- **Done when:** actual candidates can be inspected with their supporting sources and processing status; no candidate result automatically becomes an accepted equivalence, applied merge or scientific claim.
- **Evidence / dependency:** real bounded candidate readback and review behavior; W16 and W19. All original labels remain available even when suggestion pages are bounded.

#### W21 — Verify Scholar tool and user-entry integration

- **Status / priority:** historical Catalog tools and new semantic API/MCP code exist; current end-to-end access needs final confirmation; P1.
- **Method:** verify the existing Scholar profile uses the intended Catalog owner and exposes the relevant search/read/stage/evidence tools. Confirm ordinary Catalog and semantic operations reach the same canonical records and maintain English authored research output. Refresh only the scoped agent/tool metadata if required by actual evidence.
- **Done when:** the intended Scholar entry point can retrieve a real paper's current stage, Themes and located evidence, and semantic search when indexed. No stale or different database is accidentally used.
- **Evidence / dependency:** native tool metadata and actual bounded tool readback; W17 and W19. No unsolicited Telegram/email/third-party messages; a user-originated chat test can be used when appropriate. Do not restart the shared gateway or unrelated agents merely for this check.

### E. Complete real PaperSkeleton and purpose evaluation

#### W22 — Resolve the distinct held deep-role approval

- **Status / priority:** original v419 case is still separately unapproved; P1, user-dependent.
- **Method:** retain the concrete original proposal, full source payload, failed call and exact additional one-call scope. The earlier v329 one-off authorization was consumed and cannot authorize this different failure. Obtain a distinct direct user decision before any such extra submission.
- **Done when:** the user approves or declines this exact action and the decision is durably bound to the proposed scope. Goal resumption and elapsed time are not approval.
- **Evidence / dependency:** authentic user decision, original proposal and scope identity. No request is made by this planning document. Independent work may continue while implementation is later active.

#### W23 — Complete safe admission and actual deep-role continuation

- **Status / priority:** private proof/replay work exists; actual second response and complete worker continuation absent; P1.
- **Method:** after W22 approval, inspect and reuse existing scoped helpers. Complete only the missing exact admission, one-call execution, actual result authentication and worker integration. Preserve the old grant, retry limits and all saved outputs. Resolve detached-worker execution-origin context through an explicit scoped contract, not a writable identity bypass.
- **Done when:** at most the approved additional request is submitted; its original run/result is retained and validated; the authentic original job resumes through normal validation with previous successful results intact. An offline synthetic proof alone does not close this item.
- **Evidence / dependency:** approval, durable operation claim, actual provider receipt, original job events and worker result; W22. If declined, final scope/disposition must be discussed rather than fabricating completion.

#### W24 — Complete all original L1–L4 source coverage

- **Status / priority:** substantial original results preserved; actual full source completion unproved; P1.
- **Method:** resume the existing real sample and its source-located plan, reusing completed stages. L1 retains atomic propositions/entities/qualifications/source spans; L2 the actual relations; L3 argumentative intent; L4 macro writing roles. Preserve figures/tables/equations/citations and actual source outline where represented, with explicit coverage limits.
- **Done when:** every required original block/window/stage is accounted for under the original full-paper contract, complete output is persisted and retrievable, and partial coverage is not labelled complete. Do not replace the original acceptance sample with an easier sample as proof of its completion.
- **Evidence / dependency:** current source plan, all required native checkpoints and final version/readback; W23 where the held role blocks it, plus W10 reuse.

#### W25 — Publish whole-paper content and writing-structure views

- **Status / priority:** initial views and saved deep parts exist; whole-paper publication incomplete; P1.
- **Method:** derive shared dimension views from the completed Skeleton. Cover research problem, claims/viewpoints, synthesis, technical and research methods, data, evaluation, findings, limitations/gaps, argument flow and writing architecture, plus the other configured dimensions. Connect source order, L2 relations, L3 intent and L4 roles instead of producing an unrelated narrative.
- **Done when:** observations cite real Skeleton units/relations and source locations; whole-paper Theme roles and writing map reflect actual coverage and distinguish unknown/unassessed content. Existing shared profile definitions are reused.
- **Evidence / dependency:** published content views and source/Skeleton bindings; W13 and W24. Adding further dimensions is a later requirement choice, not a prerequisite to finish the current profile.

#### W26 — Publish separate purpose/value judgments and depth actions

- **Status / priority:** initial disposition support exists; full deep purpose example incomplete; P1.
- **Method:** evaluate the completed content for a declared research purpose without modifying the paper's content authority. Explain why it is useful or not, and what additional work is justified. Support individual/batch depth decisions through existing policy, keeping automatic initial reading separate from optional explicitly enabled automatic deep work.
- **Done when:** a real judgment names its purpose/version and exact content evidence; a changed purpose can reuse compatible understanding; initial-only/defer remains valid; execution is tied to an actual independent request or explicitly enabled policy.
- **Evidence / dependency:** real purpose output, decision and resulting or absent job; W14 and W25. A recommendation is not an execution grant.

### F. Source/version reuse, portability and final evidence transfer

#### W27 — Verify reuse and freshness across Views, purposes and source versions

- **Status / priority:** reuse/version/fencing mechanisms exist; complete real deep reuse remains pending; P0 basic behavior, P1 complete-deep acceptance.
- **Method:** keep one canonical paper/source and compatible analyses across Views. Reuse initial/deep results for new compatible purposes; explicitly invalidate or version derived outputs when PDF, parse, profile or source-review generation changes. Preserve history rather than overwriting old evidence.
- **Done when:** opening another View does not duplicate analysis, a changed source is not silently treated as current, and the researcher can inspect which versions produced each result.
- **Evidence / dependency:** actual source/version/result lineage and bounded reuse check; W10, W12 and later W25–W26.

#### W28 — Implement explicit portable source location handling

- **Status / priority:** real retained bytes and detached-location guard compatibility verified; production mapping/server use incomplete; P2 unless earlier release needs it.
- **Method:** retain the immutable original parse manifest and exact PDF/parser hashes. Add an explicit verified location/provenance mapping for retained or server-accessible files, using the real owner/adoption contract. Verify bytes at the target. Preserve original locations/history and avoid recreating migrated workstation stores.
- **Done when:** the target runtime opens the correct retained source with ordinary full-text checks after original workstation paths are unavailable, while the original manifest/history remain intact. A copied file or a locally altered fixture DB alone does not prove completion.
- **Evidence / dependency:** target-side physical identity and actual reader readback plus mapping history; original source package and W27. Preserve NAS rescue and coordinate any live-workspace writer.

#### W29 — Produce the complete actual FULL evidence archive

- **Status / priority:** archive/source-retention tooling prepared; current actual guard not ready; P2.
- **Method:** after real completion, capture a fresh consistent complete source/history carrier. Include the original source package, native layers, content/purpose outputs, exact execution/model receipts, source/profile versions and scoped recovery approvals. Reuse existing verifiers; update only context that actually changed.
- **Done when:** the actual finished-record guard accepts the archive against authentic original completion and all required retained files; original raw failures and successful receipts remain represented. An earlier incomplete carrier cannot become complete by relabelling.
- **Evidence / dependency:** complete archive manifest, source snapshot and verifier result; W24–W26 and W28 as required for portability.

#### W30 — Verify actual import/adoption into a nonempty owner

- **Status / priority:** software transaction/reversal cases exist; real original FULL import not achieved; P2.
- **Method:** import/adopt the actual completed archive through the existing scoped controller into the intended nonempty target. Check source identity, existing records, conflict mapping, idempotency and compensating reversal. Back up consistently and avoid blind DB replacement or rollback after unrelated new writes.
- **Done when:** the actual full sample is reusable/readable in the target with correct provenance; existing target records remain intact; duplicate adoption and conflict/reversal behavior are demonstrated at the appropriate scope.
- **Evidence / dependency:** real controller/adoption/readback receipt and preservation checks; W28–W29. Fixture success alone is insufficient.

### G. Lightweight validation, final integration and handover

#### W31 — Perform bounded independent content review

- **Status / priority:** small prior Theme spot-check exists; current full-paper claims and new changes lack final review; P0 initial sample, P1 deep sample.
- **Method:** use program checks for identities, required fields, exact quotations, references and workflow. Use an independent suitable model only for a small declared sample of semantic claims, with the original full-text evidence and relevant Skeleton context. Reuse unchanged prior checks and preserve uncertainty/disagreements.
- **Done when:** the sampled Themes, centrality, claims, methods and deep views have explicit supported/unsupported/uncertain findings; real defects are corrected/versioned. The report states its limited sample and does not approve every paper or create a universal quality score.
- **Evidence / dependency:** exact sampled items, original evidence and review results; W12–W15 first, W25–W26 later. No corpus-wide per-field model validation by default.

#### W32 — Run the actual first-delivery and full-delivery user journeys

- **Status / priority:** component and prior UI evidence exist; current complete journeys incomplete; P0 first journey, P2 final journey.
- **Method:** reuse real results where possible. First journey: import/source readiness, night initial progress, visible card/Themes/reasons/counts and manual priority. Final journey adds reasoned depth decision, complete original Skeleton, semantic discovery and portable final evidence. Test affected software once; repeat only after new changes, failures or unresolved concerns.
- **Done when:** the intended user can complete each declared journey with accurate UI/API/tool states, usable evidence and no hidden owner/version discrepancy. Partial acceptance is labelled as such.
- **Evidence / dependency:** bounded real UI/API/tool readback tied to task IDs; the relevant preceding items. A green test suite alone cannot close the journey.

#### W33 — Final FieldKG and runtime dependency check

- **Status / priority:** FieldKG already server-owned; current final integration probe pending; P2 or earlier only if an active workflow fails.
- **Method:** verify the existing server service/project/schema/storage guard and required 8892/8887 connectivity from the real client. Check the existing embedding/runtime dependencies used by this workflow. Repair only an actual observed issue within authorized scope.
- **Done when:** the intended client reaches the correct existing service and reads the expected project/schema; dependent features report failures honestly and ownership is documented.
- **Evidence / dependency:** bounded final health/client readback and known service identity. Do not remigrate, recreate local graph stores, reindex unrelated graph data or restart shared services as routine verification.

#### W34 — Close the scoped release and handover against this checklist

- **Status / priority:** draft plan and prior release receipts exist; full delivery incomplete; P2.
- **Method:** update these stable IDs with actual status/evidence. Record live versions, schedules, owners, outstanding jobs, rollback references and operational next actions. Preserve unrelated user changes and the managed session handoff. Any deliberate scope reduction or deferred final requirement needs the user's explicit decision.
- **Done when:** every retained requirement has current matching evidence or an explicitly agreed disposition; no required item is merely inferred from software tests, a planned task or an old receipt. Submit the mission review boundary appropriately; ordinary implementation does not approve it.
- **Evidence / dependency:** final requirement-to-evidence checklist, release/handover records and applicable review; all retained scope. Do not mark the Goal complete while required runtime/scientific/transfer work is unproved.

## 5. Proposed execution order and delivery boundaries

| Delivery | Proposed order | Exit condition | What can wait |
| --- | --- | --- | --- |
| 1. Usable initial-reading Catalog | W01 → W02 → W03/W04/W05; verify W07–W18, W27 basic, W31 initial and W32 first journey; triage W06 | Eligible full-PDF jobs actually advance under policy; real multi-Theme cards, dispositions, evidence, counts and truthful stages are usable | Clearing the whole backlog; general recovery for every rare error; full original deep completion; server source transfer |
| 2. Semantic discovery | W19 → W20/W21, using W16 review | Actual full-text semantic query and candidate inspection work with honest coverage and located evidence | Exhaustive indexing and every possible semantic relation before first bounded acceptance |
| 3. Complete original deep workflow | W22 → W23 → W24 → W25 → W26; finish W27 and W31 deep | The genuine original full sample and its separate purpose judgment are published, source/Skeleton-bound and usable | New optional dimensions or extra deep samples beyond needed acceptance |
| 4. Portable final delivery | W28 → W29 → W30, then W32 final/W33/W34 | Real portable archive/adoption and final integrated acceptance are proved | Unrelated specialist changes and unrequested feature expansion |

The independent parts of Deliveries 2 and 3 can be reordered after the user selects the next value target. Deliveries above are sequencing proposals, not a narrower definition of final completion.

## 6. Recommended deferrals and cost controls

1. Do not redesign the agreed two-depth framework or create another dimension taxonomy while finishing current behavior.
2. Do not require all 21 holds or the whole library to finish before a useful first delivery. Keep per-paper failures visible and independent.
3. Reuse existing tested repair, search, UI and history implementations. Check actual deployment/evidence gaps before authoring another wrapper or private version.
4. Use affected deterministic checks after relevant edits. Broaden/repeat only when a change, failure or unresolved risk justifies it.
5. Keep independent semantic review bounded to a declared sample. Do not call a strong model for mechanically checkable fields.
6. Record one durable plan with stable W01–W34 IDs. Update outcomes and next actions here rather than repeatedly generating new progress frameworks.
7. Report actual delivered milestones, resolved jobs and remaining dependencies. The earlier 60–70% estimate is not a measured acceptance score and must not substitute for this checklist.

## 7. User decisions still relevant

| Decision | Recommendation | Blocks |
| --- | --- | --- |
| Accept or change this delivery sequence | Initial-reading Catalog first; semantic discovery next; original deep workflow; portable final delivery | Resuming implementation in the newly discussed order. Goal is currently paused. |
| Optional default column visibility | Keep Themes/Understanding/Disposition/Next action readily visible; mappings in research-oriented views; Paper type/Venue optional until useful | Only the final default layout, not source processing or open-label support |
| Distinct original v419 extra deep-role request | Review the existing exact one-call proposal when Delivery 3 is selected | W22–W24 where this case blocks the original sample; it does not block the first delivery |
| Any permanent scope removal or accepted unresolved hold | Make an explicit decision against the named item/job | Final closure only; temporary sequencing does not delete original requirements |

Previously confirmed full-text, night/manual, open-Theme and PaperSkeleton-binding decisions are not reopened here. No additional implementation, deployment or model call was performed to create this plan.

## 8. Source records

- [PaperSkeleton-bound workflow](../../../RSTV4/docs/catalog-paperskeleton-bound-workflow.md)
- [Catalog columns and decisions](../../../RSTV4/docs/catalog-columns-and-decisions.md)
- [Themes and semantic aggregation](../../../RSTV4/docs/catalog-themes-and-semantic-aggregation.md)
- [Reading value and reason examples](../../../RSTV4/docs/catalog-reading-value-and-reason-examples.md)
- [Confirmed Theme policy](../../repomemory/scholar-catalog-theme-policy.md)
- [Requirement audit and historical gaps](scholar-catalog-requirement-audit-2026-10-29.md)
- [Semantic retrieval implementation history](scholar-catalog-semantic-retrieval-2026-10-29.md)
- Private current evidence: `.uuma-local/scholar-catalog-implementation-20261023/progress-note-v661.md` through `progress-note-v665.md`, `remaining-work-priority-review-v668.md`, `inspect_held_groups_v668.py`, prepared release/admission receipts, and live Reading pointer observed on 2026-11-03.

The source records contain historical states. Use current authoritative runtime/receipt evidence before a later action; do not infer that an older NOT_IMPLEMENTED or RUNNING observation remains current.
