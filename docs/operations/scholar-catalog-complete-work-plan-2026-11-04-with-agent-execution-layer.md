# Scholar / RSTV4 Catalog: complete work plan and priority review

Updated: 2026-11-03, Asia/Kuala_Lumpur.

Status: user review draft. Implementation Goal remains **PAUSED**. The user requested a detailed inventory, completion criteria, solution approach and ordering. This document does not resume implementation or authorize a separately held model retry. Existing scheduled work has not been cancelled.

The additional **Agent Execution Layer** in §9 is a proposed parallel-work and validation contract. It does not change the historical status, existing decisions, or authorize implementation.

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

---

## 9. Agent Execution Layer — parallel delivery and evidence contracts

**Added for orchestration review: 2026-11-04, Asia/Kuala_Lumpur.** This section is an **execution-layer proposal** added to the 2026-11-03 plan, not a report that implementation resumed. Sections 1–8 and the original W01–W34 requirements remain authoritative. The historical baseline in §3 is **not** a live 2026-11-04 measurement.

**Authorization boundary:** The implementation Goal remains **PAUSED**. Preparing or reviewing this layer does **not** authorize code changes in the managed project, production activation, queue admissions, new provider/model calls, the separate v419 deep-role retry, data migration, or final scientific approvals. Before implementation, obtain an explicit user decision to resume the specified scope. Any additionally restricted action still requires its own approval. Do not interpret this document, task assignment, an elapsed schedule, or another agent's message as consent.

### 9.1 Purpose and governing rules

Use **one orchestrator and seven specialist work packages** to reduce idle time without creating multiple writers to the same runtime. The original four delivery milestones remain unchanged: (1) usable initial-reading Catalog, (2) semantic discovery, (3) original full PaperSkeleton workflow, (4) portable final delivery. Their **independent preparation and verification may overlap**; only actual prerequisites and approvals are sequential.

1. **Read before rebuilding.** An agent first identifies the currently deployed component, its repository implementation, actual service/database identity, existing evidence, and the remaining acceptance gap. Existing implementations are reused. A previous `MISSING`, `RUNNING`, or `SUCCEEDED` note is historical until rechecked against its authoritative owner.
2. **Real evidence over green tests.** Keep distinct `IMPLEMENTED`, `TESTED`, `DEPLOYED`, `RUNTIME_VERIFIED`, and `ACCEPTED` evidence. A passed fixture or helper is not a recovered reading job; a prepared release is not a deployed release; a draft full archive is not an adopted FULL sample.
3. **One accountable task owner.** Every W01–W34 has exactly one work-package owner. Collaborators provide evidence and interface contracts but cannot independently mark that W item accepted.
4. **No competing production writers.** Production Reading activation, real admissions and worker recovery require a single designated operator, current-owner reconciliation, safe boundaries, and appropriate authorization. Other agents use read-only inspections or isolated test fixtures.
5. **Keep scientific authority bounded.** All proposed Themes, semantic links, scientific claims and mappings stay candidates until reviewed. Never bypass source/quotation validators or silently rewrite original evidence to make a test pass.
6. **Preserve existing decisions.** Full readable PDF before reading; automatic import intent; 00:00–08:00 **Asia/Kuala_Lumpur** automatic reading/backfill; manual priority; open multi-Themes; Theme counts overlap; PaperSkeleton L1–L4; English authored research content; existing interface language; NAS rescue/source retention.
7. **Separate workflow gates from implementation work.** Approval, production execution, scientific acceptance, and final scope disposition are not delegated implicitly to coding agents.

### 9.2 Assignment and ownership matrix

| Work package / agent | Sole-accountable W items | Mission | Can start in isolated/read-only mode | Must wait for before production acceptance |
| --- | --- | --- | --- | --- |
| **WP-A — Runtime & Recovery** | **W01–W05** | Reconcile scheduled digest; activate the combined Reading release safely; resolve pinned 4+2+3 source-bound holds | Inspect receipts, pinned cases, release manifests, guards and prior tests | Authorization to resume; W01 real receipt; verified idle/owner boundary for W02; W07 source gate and allowed night admission for W03–W05 |
| **WP-B — Pipeline & Scheduling** | **W06–W11** | Triage the remaining twelve holds; validate source gate, automatic/backfill intents, night/manual fairness, resumability, worker state | Inspect failures, queue/policy code, fixtures and observability; prepare deterministic tests | Authorized live observation and actual window events; coordinated worker owner; W07/W09/W10 integration proof |
| **WP-C — Catalog & Research UI** | **W12–W18** | Validate initial card, shared dimensions, disposition, open Themes, mapping review, columns and distinct-paper counts | UI/API inspection, fixture checks, read-only real-card review | Real source-backed initial results, current owner/API state, approved default column choice for final layout |
| **WP-D — Semantic Discovery** | **W19–W21** | Validate existing BGE-M3/index implementation, bounded semantic retrieval, evidence-based relations and Scholar tools | Source/index discovery, isolated queries and read-only metadata review | W07 eligible source and W09 resource policy; actual bounded index/query and canonical Scholar readback |
| **WP-E — Deep Reading & Reuse** | **W22–W27** | Track separate v419 decision; finish the **original** full L1–L4 sample; publish content/purpose; validate cross-view/version reuse | Inspect preserved outputs, coverage map, existing replay helpers, tests and reuse contracts | **W22 explicit decision** before any extra v419 call; W23 authentic result; W24 completeness before W25–W26; W27 deep proof depends on real outputs |
| **WP-F — Portability & Transfer** | **W28–W30** | Validate original source mapping, complete FULL archive and safe nonempty-target adoption | Build/check isolated location-mapping and import-verifier fixtures; read-only audit | Authoritative target access and permission; W24–W26 real full completion, W28 physical target identity, W29 complete archive |
| **WP-G — Independent QA & Handover** | **W31–W34** | Independently review bounded science, first/final journeys, existing FieldKG probe, requirement-to-evidence closure | Create acceptance harness/matrix, read-only proof checks and test design from day one | Real initial/deep outputs for W31; integrated workflows for W32; current client health for W33; all retained scope for W34 |

The **Orchestrator** coordinates WP-A–WP-G, owns the integrated plan/merge queue and reports to the user; it is **not** an eighth implementer and may not approve its own restricted operations. Shared requirements have supporting contributors: WP-C supplies W27 initial/view evidence to WP-E; WP-B supplies W07/W09 runtime facts to WP-A and WP-D; WP-G independently challenges the evidence from each owner.

### 9.3 Parallel dependency graph and critical paths

The four deliveries are acceptance milestones, **not global stop-the-world phase locks**. Work can start when its own inputs and safe execution mode are available.

```text
Permission gate: Goal PAUSED -> user separately authorizes implementation scope

Initial Catalog critical path:
  WP-A: W01 -> W02 -> (W03 || W04 || W05)
                  ^ W07 from WP-B; night admission policy from W09
  WP-B: W06 triage || W07 -> W08 -> W09 -> W10 -> W11 [verification may overlap]
  WP-C: W12 -> W13/W14/W15 -> W16/W17/W18
  WP-G: W31(initial) -> W32(first journey) -> Delivery 1 ACCEPTED

Semantic path, may progress alongside the initial path:
  WP-D: [W07 eligible parse + W09 bounded-resource policy] -> W19 -> W20/W21
         W20 review actions also depend on W16; W21 canonical retrieval uses W17.
       -> Delivery 2 ACCEPTED

Original deep path, preparation may run before its execution gate:
  WP-E: W22 (distinct user decision) -> W23 -> W24 -> W25 -> W26
         W27(full) follows real deep output; W10 provides reuse guarantees.
  WP-G: W31(deep) -> Delivery 3 ACCEPTED

Portable full delivery path:
  WP-F: W28 (can develop/test early) -> W29 [also W24–W26] -> W30
  WP-G: W32(final) + W33 -> W34 -> Delivery 4 ACCEPTED
```

**Parallelism policy:** WP-B/C/D/E/F/G may inspect existing implementations and make non-conflicting **isolated proposals** while WP-A reconciles W01. Do **not** parallelize live W01/W02 activation with uncoordinated queue admissions, run two competing Reading releases, race the same source/job/model operation, or modify one production store from multiple worktrees. A held paper must not starve unrelated eligible READY papers. A stalled approval does not block independent semantic/catalog work.

### 9.4 Orchestrator lifecycle, decisions and conflict control

**Execution states for each W item:** `NOT_STARTED` → `DISCOVERY` → `IMPLEMENTING` → `LOCAL_VERIFIED` → `INTEGRATION_READY` → `DEPLOYED` → `RUNTIME_VERIFIED` → `ACCEPTED`. Use `BLOCKED`, `HELD`, or `DEFER_PROPOSED` as explicit side states (with reason, owner and next action). `DEFER_ACCEPTED` requires an actual user decision; it is not inferred from a priority label. Skip inapplicable intermediate states with documented evidence (for example, existing production code can go from `DISCOVERY` to `RUNTIME_VERIFIED` after independent verification).

**Orchestrator procedure:**

1. **Preflight, read-only:** Resolve repository roots, current git commit/worktree, code-owner files, runtime owner, release pointer, relevant source/paper IDs, backing databases and service endpoints. Locate the original test commands and receipts. If any locator is unknown, record `UNKNOWN — discover from authoritative source`; do not invent a path or ID.
2. **Make a baseline snapshot:** Capture the live state with timestamp, timezone, service/release identity, job counts and task receipts. In particular, inspect the **2026-11-04 00:05:05 Malaysia** `UuMA Scholar Digest Recovery v653` outcome; do not assume it ran or succeeded. Never silently replace the 2026-11-03 figures in §3 with later figures.
3. **Publish a dependency board:** One row per W item, work-package owner, blockers, artifact/interface version, current evidence and next action. Flag approval boundaries prominently.
4. **Assign isolated work:** One branch/worktree per package; explicit file/glob ownership after repository discovery. Propose interface changes centrally before implementation. Shared database migrations, generated schemas, public contracts, service startup scripts and live deployment files need a **single appointed editor** or a serialized merge. No arbitrary concurrent direct edits to the base branch or production data.
5. **Integrate with bounded checks:** Each owner returns a small change set and evidence packet. The orchestrator checks interface compatibility and merges in dependency order; run tests relevant to the diff and expand only where risk or failure requires it.
6. **Production gate:** Re-read the current actual owner/process/task and source hashes immediately before any authorized write. Use transactional idle/checkpoint gates, exact durable operation IDs, unique worker ownership, backup/rollback and idempotent readback. Any stale precondition blocks the write pending a fresh plan.
7. **Independent acceptance:** WP-G checks the original `Done when` against **real** output and records supported, unsupported or uncertain scientific observations. Scientific acceptance remains subject to the designated human review.
8. **Close only with evidence:** WP-G may recommend `ACCEPTED`; the orchestrator updates status after verifying evidence and approval conditions. W34 is a final closure/checklist item, **not a signal that work has reached item 34**. Do not mark the whole Goal complete without all retained required acceptance evidence or user-approved explicit deferral.

**Coordination rule:** Any agent encountering a change outside its assigned work package must open a cross-package request with `needed interface`, `reason`, `proposed owner`, `impact`, and `required acceptance`; it must not expand its own authority. If two packages need the same file, the orchestrator assigns one writer and the other contributes a test or patch proposal.

**Approval and action classes:**

| Class | Examples | Required gate |
| --- | --- | --- |
| **R — read-only** | Inspect code, historical receipts, tests, status, non-sensitive sample outputs | Access to source; do not mutate or leak private data |
| **L — isolated development** | Worktree code/test changes, fixture runs, local index fixture, draft documentation | User resumption authorization for implementation; scope-limited workspace and test isolation |
| **O — operational write** | Switch Reading release; admit jobs; touch production queues/stores; migrate location; restart worker | Explicit authorization for that operational scope, fresh live preconditions, single operator and rollback plan |
| **M — external model request** | New production LLM attempt or replay requiring a real call | Approved scope/budget and policy; **v419 still needs its distinct one-call W22 approval** |
| **H — human scientific / scope decision** | Accept scientific semantics or Theme merge, permanently DEFER a retained requirement, approve Goal closure | Actual reviewer/user decision, persisted with specific target and evidence |

An agent must never treat `R` or `L` access as permission for `O`, `M`, or `H`. The 00:00–08:00 night window constrains **automatic reading/backfill**, not unrestricted permission to run newly submitted production tasks. An explicit manual request has priority at a safe work boundary; all data/source protections still apply.

### 9.5 Work-package execution contracts

Each owner delivers a **self-contained, reviewable change and evidence packet**. The entries below are executable *assignments after authorized resumption*, not permission to act now. Where a source location, command, paper ID, model handle or worker identity is omitted, the agent must discover and cite the actual identifier in its packet **before** using it; this plan does not invent values.

#### WP-A — Runtime & Recovery (W01–W05)

- **Input:** current scheduled-task receipt/owner-event history; pinned original job/model/source IDs; manifest of observed `catalog-12c4571ce546` and prepared `catalog-48cece41023e`; associated tests, guards and rollback artifacts. Both identifiers are **historical observations** until read back live.
- **Procedure:** (1) reconcile W01's scheduled digest without duplicate admission; (2) only when safe, activate and verify exactly one combined W02 worker; (3) scope W03 four dimension-state repairs, W04 two Theme-ID repairs and W05 three digest cases against original PDF, quotations and unchanged validators; (4) preserve prior successes, raw failures and call receipts.
- **Deliver:** W01 exact outcome; release activation identity and rollback receipt if authorized; 9-row case ledger with `source/job/operation`, original failure, validation, admission, actual outcome/held next action; diff/tests for any newly necessary repair.
- **Acceptance:** the original W01–W05 `Done when` conditions, including real worker and original-job continuation. Prepared helper, test pass or scheduled admission alone is insufficient. **Stop** on ambiguous ownership, stale source hashes, duplicate call risk, non-idle activation, or authorization gap.

#### WP-B — Pipeline & Scheduling (W06–W11)

- **Input:** 12 originally held jobs by error class, actual failed payloads and saved responses, source guard/parse manifests, import intents, queue/worker events, resource-policy tests.
- **Procedure:** W06 diagnose every held item individually before choosing a reusable recovery path; W07 verify genuine eligible and ineligible full-text cases; W08 inspect auto-import/backfill deduplication and stage visibility; W09 observe a **real** Malaysia night window plus safe manual priority; W10 trace original operation across pause/restart and source/profile changes; W11 prove unique supervised worker and actionable UI/API state.
- **Deliver:** 12-row diagnosis and treatment ledger; source-gate test matrix; intent/backfill accounting; timestamped real admission/fairness observation; resume/duplicate-prevention trace; worker status/provenance snapshot.
- **Acceptance:** W06 may close P0 **triage** with visible holds, not silently close the twelve actual recovery tasks. Night behavior and worker health require real events, not only simulated clocks or task registration. Never blanket-reset a held cohort.

#### WP-C — Catalog & Research UI (W12–W18)

- **Input:** canonical paper records, genuine finished initial-reading outputs, PaperSkeleton versioned dimension profile, actual Theme/Field/Topic review states, UI/API implementation and saved layouts.
- **Procedure:** inspect first; demonstrate source-linked W12 card; check W13 assessed/unknown/unassessed dimensions without fake deep units; show evidence-based W14 disposition and reason without creating unauthorized jobs; show W15 multi-Theme roles and unmapped Themes; verify W16 proposal/review/reversal history; test W17 actual columns and save/reload; validate W18 ANY/ALL, overlapping Theme counts and unique-ID union.
- **Deliver:** readback examples, UI screenshots or equivalent native readback, deterministic overlap/count fixtures, versioned content/source locators, column-default decision note, small scoped fixes if necessary.
- **Acceptance:** real cards and state/filters are useful and truthful. **Proposed default** (not yet user-approved): show `Themes`, `Understanding`, `Disposition`, `Next action`; make `Field/Topic`, `Venue`, `Paper type` optional. Preserve saved layouts and existing interface language.

#### WP-D — Semantic Discovery (W19–W21)

- **Input:** current BGE-M3 service/index/API/MCP implementation, source eligibility/parse version, indexed/pending/stale inventory, canonical Scholar entry/tool metadata and real bounded query cases.
- **Procedure:** verify existing code and deployments rather than rebuilding; W19 index eligible located passages and candidate labels under bounded resources; run natural-language search with evidence distinguishable from lexical matching and honest partial coverage; W20 inspect bounded two-sided candidate relations and route review to W16; W21 use the intended Scholar entry point against the **same** canonical paper and current stage.
- **Deliver:** service/index generation + source identity, query text and located top results, indexed/pending/stale coverage report, candidate proposal evidence from both papers, tool readback of actual stage/Themes/evidence.
- **Acceptance:** actual search and Scholar tool use work with clear partial-index caveats. No automatic equivalence merge, no unrelated graph reindex, no unnecessary provider replacement, no unrelated gateway restart.

#### WP-E — Deep Reading & Reuse (W22–W27)

- **Input:** exact original v419 one-call proposal and historic v329 grant/usage, original held model operation, preserved L1–L4 outputs/checkpoints, source coverage plan, dimension profile, purpose definitions and versioned reuse mechanism.
- **Procedure:** W22 record a **distinct direct approve/decline decision** (the old v329 permission is consumed); do not submit another call if absent. After approval only, W23 authenticate at most the exact scoped call and resume the original worker without changing execution identity; W24 prove all required original source windows/layers accounted for; W25 publish derived whole-paper content/writing structure using actual Skeleton IDs; W26 publish separate purpose/value and explicit depth action; W27 verify reuse/freshness across Views, purposes and source changes, including WP-C's initial behavior.
- **Deliver:** approval record or precise blocker; original operation/provenance chain; per-layer/source coverage matrix; native complete Skeleton retrieval; evidence-linked whole-paper views and purpose output; cross-view/version invalidation tests.
- **Acceptance:** original real sample, not an easier substitute, satisfies W22–W27; partial deep completion remains visible. If W22 is declined, mark its dependent scope `BLOCKED` and request an explicit scope/disposition decision; do not fabricate FULL completion.

#### WP-F — Portability & Transfer (W28–W30)

- **Input:** immutable original source/package and parser bytes/hashes, existing location/adoption controller and guard, actual nonempty target identity, complete original FULL sample when ready.
- **Procedure:** W28 introduce/verify explicit source-location and provenance mapping with target-side byte identity and real reader access after workstation path loss; W29 make an actual consistent complete source/history carrier only when authentic W24–W26 outputs exist; W30 adopt that carrier via scoped controller into a **nonempty** target with conflict/idempotency/reversal checks and preservation of existing records.
- **Deliver:** target mapping readback + hashes; archive manifest and actual finished-record guard result; backup and adoption receipt; post-adoption canonical readback and nonempty-target preservation evidence.
- **Acceptance:** W28–W30 original `Done when` on real target, not just detached fixture. No blind database replacement, historical-manifest rewrite, unreconciled rollback, unnecessary remigration, or NAS rescue disruption.

#### WP-G — Independent QA & Handover (W31–W34)

- **Input:** W01–W30 owners' evidence packets; original `Done when`, source quotations, real UI/API/tool results, actual client endpoints, archived approvals/versions/rollbacks.
- **Procedure:** design bounded independent initial and deep scientific sampling for W31 (mechanical invariants by code; sampled semantic claims by a suitable independent reviewer/model only if separately authorized); W32 exercise **first** and **final** actual user journeys with canonical records; W33 run a non-destructive client probe for the *existing* FieldKG owner/schema and required 8892/8887 connectivity; W34 reconcile every W requirement, accepted deferral and operating handover.
- **Deliver:** acceptance matrix, evidence validity findings and disputed cases, genuine user-journey trace, bounded FieldKG client health record, final release/rollback/owner/task inventory and handover document.
- **Acceptance:** does not mark incomplete scientific conclusions accepted, silently modify another agent's feature, claim whole-corpus review from a sample, remigrate FieldKG, or declare Goal complete on prior software receipts alone.

### 9.6 Requirement-to-evidence acceptance matrix (initially unverified)

**This is a checklist of required proof, not proof already collected.** In the last two columns, `—` means *not reverified for this new layer*. Do not convert historical evidence described in §3–§4 into a new acceptance status without actual readback.

| W | Owner | Minimum closing evidence to attach | Acceptance state | Live evidence ref |
| --- | --- | --- | --- | --- |
| W01 | A | Scheduled task outcome + original owner/job/model receipt, no duplicate submission | UNVERIFIED | — |
| W02 | A | Current loaded combined release, unique worker, scoped rollback receipt | UNVERIFIED | — |
| W03 | A | Four source-bound case results with unchanged coverage/evidence checks or explicit remaining cause | UNVERIFIED | — |
| W04 | A | Two original quotation-ID repairs validated and jobs continued or explicitly held | UNVERIFIED | — |
| W05 | A | Three original complete ordered digest inputs checked against actual outcomes | UNVERIFIED | — |
| W06 | B | Twelve itemized diagnoses, next actions, and any verified repair results | UNVERIFIED | — |
| W07 | B | Genuine full-PDF allow case + missing/corrupt/changed/quarantined reject cases | UNVERIFIED | — |
| W08 | B | Import intent, historic backfill stage ledger, deduplication and actual progression | UNVERIFIED | — |
| W09 | B | Actual night timestamps, manual safe-boundary priority, bounded queue fairness | UNVERIFIED | — |
| W10 | B | Original operation continuation without duplicate successful model/parse calls | UNVERIFIED | — |
| W11 | B | Unique owned worker + live queue/held/stopped status and actionable error | UNVERIFIED | — |
| W12 | C | Real canonical source-linked initial content card with qualifications | UNVERIFIED | — |
| W13 | C | Versioned shared profile, evidence-bound assessed states, no fabricated deep IDs | UNVERIFIED | — |
| W14 | C | Real disposition/reasons and proof recommendation did not launch work | UNVERIFIED | — |
| W15 | C | Real multi-Theme roles including searchable unmapped label and sources | UNVERIFIED | — |
| W16 | C | Proposed vs reviewed vs reversed mapping/alias with durable history | UNVERIFIED | — |
| W17 | C | Real state and next-action column/UI readback, saved layout reload, default decision | UNVERIFIED | — |
| W18 | C | Distinct-paper union and ANY/ALL overlap checked on real and deterministic cases | UNVERIFIED | — |
| W19 | D | Actual bounded semantic query, located eligible passages, indexed/stale coverage | UNVERIFIED | — |
| W20 | D | Candidate relation supported by both sources, bounded aggregation, nonautomatic review | UNVERIFIED | — |
| W21 | D | Intended Scholar tool accesses same canonical stage/Themes/evidence/search | UNVERIFIED | — |
| W22 | E | Authenticated independent user decision tied to exact original v419 extra call | UNVERIFIED | — |
| W23 | E | Scoped additional call (if approved) + original operation/worker continuation receipt | UNVERIFIED | — |
| W24 | E | Original complete L1–L4 checkpoint/source-block coverage and readback | UNVERIFIED | — |
| W25 | E | Whole-paper content/writing structure derived from real Skeleton source units | UNVERIFIED | — |
| W26 | E | Separate purpose/version-specific value judgment and authorized depth action | UNVERIFIED | — |
| W27 | E | Canonical cross-View reuse, source/profile invalidation, version history | UNVERIFIED | — |
| W28 | F | Target physical PDF/parser identity, preserved manifest, verified actual reader | UNVERIFIED | — |
| W29 | F | Full authentic source/history archive, hashes and finished-record guard pass | UNVERIFIED | — |
| W30 | F | Nonempty-target adoption, idempotency/conflict/reversal and preservation readback | UNVERIFIED | — |
| W31 | G | Sampled initial + deep semantic review with explicit uncertainty/corrections | UNVERIFIED | — |
| W32 | G | Actual first + full user journey receipts, no owner/version mismatches | UNVERIFIED | — |
| W33 | G | Existing FieldKG service/schema/8892/8887 client probe and dependency identity | UNVERIFIED | — |
| W34 | G | All W items evidenced or user-disposed, final release/owner/rollback/handover | UNVERIFIED | — |

**Accepting evidence:** A row may reach `ACCEPTED` only if the corresponding original §4 `Done when` is satisfied by current credible evidence, all relevant guards and permissions hold, and WP-G records an independent verification reference. A row can remain `BLOCKED` or `DEFER_ACCEPTED` without being counted as completed implementation; the final release can close only under the original user-approved scope.

### 9.7 Standard evidence packet and agent handoff format

Every work package must return a report with the following fields, stored in an orchestrator-selected location **after repository discovery**; the example path is a proposed convention, not an assertion that the folder exists.

```yaml
work_package: WP-A             # WP-A ... WP-G
owner: runtime-agent           # actual worker/agent identifier
branch_or_worktree: null       # real identifier if applicable
base_commit: null              # record actual git revision
current_commit: null
scope: [W01, W02, W03, W04, W05]
execution_mode: READ_ONLY      # READ_ONLY | ISOLATED | AUTHORIZED_OPERATION
approval_reference: null      # mandatory for restricted operations
source_identity: null         # canonical paper/PDF/parse/source/version, as applicable
runtime_identity: null        # task/process/owner/release, as applicable
change_summary: []
changed_files: []
tests:
  - command: null             # actual command executed, never invented
    result: NOT_RUN           # PASS | FAIL | NOT_RUN
    artifact: null
real_world_checks:
  - requirement: W01
    status: UNVERIFIED        # VERIFIED | FAILED | UNVERIFIED
    evidence_reference: null  # durable receipt, UI/API readback, source span
    observed_at: null         # ISO-8601 with timezone
blockers: []                  # exact blocker, dependency and owner
risk_and_rollback: null
next_actions: []
proposed_acceptance: []       # QA decides; never self-certifies ACCEPTED
```

**File/artifact convention (proposal):** The orchestrator may choose `docs/operations/scholar-catalog-agent-execution/` for a version-controlled board, work-package briefs and acceptance matrix, and an existing private evidence store for receipts or sensitive logs. Do **not** copy private source PDFs/model payloads into public Git by default. Keep immutable receipts and exact references to them; redact sensitive material only in shareable reports without weakening the underlying audit trail.

**Definition of a good handoff:** A different agent can reproduce every claimed deterministic check and navigate to every real observation without guessing the release, job, source, environment, timestamp or approval. If that is not possible, `DONE` is prohibited.

### 9.8 Copy-ready dispatcher and specialist agent instructions

**Orchestrator dispatch instruction (after explicit authorization to resume):**

> Implement the accepted Scholar Catalog W01–W34 scope using §9 as the multi-agent execution layer and §4 as the authoritative requirements. Begin with read-only discovery and a timestamped current-owner/receipt baseline. Maintain one accountable owner per W item and separate isolated worktrees. Start independent WP-B/C/D/E/F/G inspection in parallel while WP-A reconciles W01; serialize all production Reading writes and shared migrations. Apply the approval classes in §9.4. Preserve the original full-PDF/night/manual/open-Theme/PaperSkeleton decisions. Have WP-G independently verify each requirement against real source-bound evidence. Report an updated 34-row board, blockers, evidence and requested explicit decisions; do not substitute test pass for deployment/acceptance or mark the Goal complete without valid W34 closure.

**Specialist start prompt — WP-A:**

> Own only W01–W05. Discover authoritative task/worker/source/release identity; first reconcile the 2026-11-04 00:05:05 scheduled digest recovery. Do not duplicate any saved model request. Prepare an activation and rollback proof for W02; execute only with the required authorization and safe owned boundary. Preserve source evidence and provide nine itemized held-case outcomes. Deliver the §9.7 packet and your original W01–W05 acceptance evidence; do not self-accept.

**Specialist start prompt — WP-B:**

> Own only W06–W11. Triage all twelve distinct held jobs individually, verify real full-PDF gates, auto-import/backfill, night/manual fairness, idempotent resume and unique worker observability. Prefer read-only evidence and deterministic tests until live operations are authorized. Report exact unresolved causes, do not reset history or dispatch model retries, and hand WP-A/WP-D authoritative source/scheduling interface evidence.

**Specialist start prompt — WP-C:**

> Own only W12–W18. Reuse Catalog implementation and inspect real canonical initial reading cards, versioned dimensions, disposition, open Themes, reviewed mappings, UI layouts and unique-paper counts. Preserve optional label mapping and candidate statuses; do not invent research claims or trigger deep reads. Provide source-linked readback and scoped test changes. Default columns remain a proposal pending user choice.

**Specialist start prompt — WP-D:**

> Own only W19–W21. Inspect the existing BGE-M3/index/API/MCP path first. Demonstrate bounded real semantic retrieval with located full-text evidence and honest coverage; inspect two-sided candidate proposals and canonical Scholar tool access. Do not auto-merge scientific labels, run a full unbounded reindex, or restart shared gateways. Coordinate W16 review interfaces with WP-C.

**Specialist start prompt — WP-E:**

> Own only W22–W27. Retain the exact original v419 held-operation identity and seek/record a distinct user decision before any extra production model submission; previous v329 permission is not transferable. Reuse original L1–L4 checkpoints, prove full original source coverage, publish actual Skeleton-bound content and separate purpose judgment, and verify version reuse. Until approval, perform only permissible inspection/preparation and report the blocked path.

**Specialist start prompt — WP-F:**

> Own only W28–W30. First verify retained original source bytes, hashes, and existing adoption guards. Prepare portable location mapping and isolated import checks without altering live owner state. After authentic complete W24–W26 results and appropriate authorization, produce and verify the actual FULL carrier and nonempty-target adoption, preserving existing records and rollback history. Fixture success is not final acceptance.

**Specialist start prompt — WP-G:**

> Own only W31–W34 as an independent verifier. Make an evidence matrix from every original W item, audit source citations and sampled scientific interpretations, execute actual first/final journeys when ready, and probe the existing FieldKG client without routine remigration. Challenge missing or stale runtime evidence. Maintain honest `UNVERIFIED/BLOCKED/ACCEPTED` outcomes, preserve human scientific decisions and recommend W34 closure only after the retained scope is genuinely evidenced or explicitly user-disposed.

### 9.9 Decisions, gates and first-dispatch checklist

**Still needed from the user (no default implied consent):**

1. **Resume decision:** Approve the proposed multi-agent strategy and identify what implementation/isolated testing/operational writes are permitted. Merely asking for this revised plan does **not** resume the PAUSED Goal.
2. **Catalog default columns:** Decide whether the WP-C proposal `Themes / Understanding / Disposition / Next action` is the default, with `Field/Topic / Venue / Paper type` optional.
3. **Distinct v419 action:** Approve or decline the **exact separately held one-call** W22 proposal only after inspecting its authentic scope, source and previous history. This cannot be blanket-approved by general plan acceptance.
4. **True deferrals:** Name any W requirement or held job to accept as DEFER/removed scope explicitly; absent such a decision, retain it in W34.

**Before dispatching implementation:**

- [ ] Exact resumption/scope approval recorded; authorization mode clear for each package.
- [ ] Original §§1–8 retained, W01–W34 unchanged, and the 2026-11-03 baseline labelled historical.
- [ ] Live v653 task result, owner/worker identity, release pointers and job inventory re-observed after its scheduled window.
- [ ] Repository/module ownership and shared contract edits assigned only after code discovery.
- [ ] One branch/worktree per package; one designated runtime writer; no concurrent migrations.
- [ ] Approval ledger distinguishes model retries, production writes and human scientific review.
- [ ] QA has independent W01–W34 matrix and genuine proof requirements.
- [ ] Interface handoffs and blockers are visible; independent work is not blocked by unrelated held jobs.
- [ ] Every package is required to return the §9.7 evidence packet and exact remaining actions.

**First usable delivery gate:** Real eligible full-PDF initial reading demonstrably advances under the night/manual/source policies; a real canonical Catalog item shows meaningful initial understanding, multi-Themes, evidence, disposition and truthful next action; overlapping counts work; outstanding held cases remain accurately visible; WP-G verifies the first user journey. **Do not require all 116 historical READY or all 21 historical held jobs to finish** merely to pass this first gate.

**Final handover gate:** Real bounded semantic discovery; original fully covered L1–L4 sample and purpose judgment; portable complete evidence/carrier and actual nonempty-target adoption; final first/full user journeys; current FieldKG client check; every retained W item evidenced or specifically accepted as deferred; genuine release/owner/rollback and provenance handover. W34 closes only after these original requirements are honestly accounted for.

**Document change log:** This section adds orchestration guidance and proposed acceptance mechanics only. No code, jobs, releases, production databases, provider/model calls, approvals or runtime measurements were performed by writing it.
