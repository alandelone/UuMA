# Scholar Catalog requirement audit, 2026-10-29

The full goal is not complete. This audit supersedes the earlier statement that only the initial recovery, deep recovery and actual FULL import remain. Current source and runtime expose an additional independent implementation gap: global natural-language full-text retrieval and evidence-backed candidate semantic relation generation. A prior rough80percent estimate was not a weighted acceptance measurement.

The existing Catalog query supports candidate-inclusive Theme text filters, coverage-role/status filters, distinct-paper ANY/ALL operations, and reviewed alias/merge groups. It does not search the source passages semantically: the whole normalized user sentence is tested as a substring of Theme labels/definitions. A zero-result live query is supporting behavior, not the sole proof of missing semantic recall. Current global API/MCP definitions and the query implementation were inspected. Field-scoped FieldKG semantic runs do not satisfy global unmapped content.

| Accepted requirement | Current evidence state | Evidence and limit |
| --- | --- | --- |
| Full PDF before initial and deep reading | IMPLEMENTED; CURRENT REAL RECOVERY INCOMPLETE | paper_sources.py and reading policy; v258 strict-source tests; current actual job v291. |
| Automatic initial intent for every import, independent of a Field or View | IMPLEMENTED; CORPUS COMPLETION NOT CLAIMED | Catalog-owned reading/source pipeline and current v25 runtime. Initial recovery remains queued. |
| All automatic reading 00:00-08:00 KL; manual requests first | CURRENT POLICY AND QUEUE VERIFIED | reading_policy.py constants/admission, v258 software cases, actual manual_priority0/READY/fence55 in v291. |
| Visible missing stage and gradual nightly backfill | IMPLEMENTED; BACKLOG STILL INCOMPLETE | Reading overview/inventory and actual admitted initial queue. Do not treat queued as completed. |
| Open multiple Themes including unmapped domains | LIVE INITIAL EXAMPLE; DEEP EXAMPLE INCOMPLETE | v145 rendered14 candidate Themes, current HTTP candidate query and unchanged served JS in v291. |
| Candidate visibility, review state and all three coverage roles | IMPLEMENTED; SCIENTIFIC ACCEPTANCE NOT IMPLIED | CatalogUnderstanding.query defaults CANDIDATE/ACCEPTED and CENTRAL/SUBSTANTIAL/PASSING_MENTION; actual candidate view. |
| Distinct-paper union/intersection and reviewed alias grouping | IMPLEMENTED; NOT NATURAL-LANGUAGE SEMANTIC RECALL | Current query uses grouped paper ID sets and ANY/ALL. Existing grouping follows reviewed alias/merge edges. |
| Optional direct Field/Topic mappings; separate Track/RQ use | IMPLEMENTED; NO MAPPING AUTOMATICALLY APPROVED | propose_mapping accepts Field/Topic; no artificial research Field required by global Catalog. |
| Shared extensible PaperSkeleton dimensions and original L1-L4 | PARTIAL ACTUAL END-TO-END | Actual native completion and retained28 content parts; content view blocked, purpose absent (v288). |
| Source-backed reasons and initial-sufficient / recommend / uncertain decisions | IMPLEMENTED; FULL DEEP PURPOSE EXAMPLE INCOMPLETE | Initial card/depth profile and source contracts; actual purpose judgment not yet produced. |
| Reuse across Views/purposes and safe version-specific reprocessing | IMPLEMENTED; FINAL REAL FULL TRANSFER PENDING | Source/profile compatibility and durable cached part histories; v284 software source identity and no duplicate dispatch. |
| Whole-paper content view then separately bound purpose judgment | ACTUAL SAMPLE INCOMPLETE | v288 content NEEDS_HUMAN, no purpose job; no fabricated success. |
| Correction, rejection persistence, review and compensating reversal history | SOFTWARE VERIFIED; EXISTING DATA PRESERVED | v276 40 targeted history cases, v284 completed transaction/reversal fixture, v262 original table prefixes. |
| Accepted columns and saved preferences preserved | LIVE UI VERIFIED AT v145; CURRENT SERVED BYTES VERIFIED | v145 actual UI14 candidates/saved layout, v291 exact current JS and four owned processes. |
| Global natural-language retrieval across full text and evidence | MISSING | Inspected query normalizes entire sentence and uses substring matching only against Theme label/definition; no global passage semantic retrieval path exposed. |
| Evidence-backed candidate semantic vocabulary relation generation | MISSING GLOBAL PATH | Manual propose_link/propose_mapping exist. Existing FieldKG semantic runs are Field-scoped and cannot satisfy global unmapped content. |
| Scholar Catalog tool integration | HISTORICALLY VERIFIED; NEW RETRIEVAL TOOL STILL NEEDED | v146 eight actual stdio/cache tools. Current source list has no global semantic full-text query operation. |
| FieldKG service on server and endpoint availability | SERVER OWNERSHIP VERIFIED IN v148; FRESH FINAL PROBE STILL REQUIRED | alandelone-server-001 project2/ScholarFieldKG, services active and owned8892/8887 forwards at v148; do not migrate again. |
| Lightweight independent model spot-check and deterministic validation | SAMPLED REAL EVIDENCE ONLY | v137 actual thinking gemini-3.1-pro supports3 sampled local Theme claims/14; whole-paper centrality unknown; do not demand corpus-wide review or approve scientific claims. |
| Production deployment, immutable receipts and scoped ownership | CURRENT v25 VERIFIED | v291 all423 files hash-exact, four owned process births/modules/PYTHONPATH exact, served current JS, no restarts. |
| Actual complete archive/import of the original FULL sample | NOT ACHIEVED | v284 five software transaction cases passed; public actual original guard remains NOT_READY. No actual FULL import exists. |

## Next independent implementation

Implement global full-text/evidence retrieval and candidate semantic aggregation against the Catalog-owned frozen source/parse/Skeleton identities. Reuse eligible initial and completed deep evidence without starting new deep extraction. Retrieval must include unmapped content and immediately visible candidates, preserve distinct-paper counting, explain matches with located evidence, and retain source/review/freshness metadata. A semantic similarity result must never apply a vocabulary merge or accept a scientific claim. Keep Field/Topic mapping independent and do not create a synthetic Field to use the existing Field-scoped service.

Use the existing service/model integration where its actual capability and ownership can be verified; do not invent an embedding endpoint or send text to a new destination. Build source-fenced, rebuildable retrieval projections separate from canonical scientific records. Automatic model/index work must honor night/resource/manual policy. User queries must make stale/unavailable/incomplete indexing explicit and never relabel lexical matching as semantic matching. Verify focused behaviors with deterministic fixtures and perform one bounded real read-only retrieval check after deployment; do not rerun unchanged full suites or the original successful paper analyses.

The original deep one-role proposal remains unapproved. Initial-only recovery stays the same night-queued job, not a new manual request. Completing this retrieval feature cannot bypass those separate real-paper gates. No whole-corpus scientific acceptance or user review of every label is required by this implementation audit.
