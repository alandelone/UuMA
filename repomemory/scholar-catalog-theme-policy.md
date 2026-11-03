# Scholar Catalog theme policy

User decision, 2026-10-22, Asia/Kuala_Lumpur:

Paper-content labels must form an open vocabulary across the entire Catalog.
A paper can cover multiple Themes, including domains not defined as current
research Fields or Topics. Such unmapped labels must be included, retained,
displayed, searchable and available to semantic aggregation. Do not restrict
extraction or label discovery to the user's present research plan.

The user explicitly requested the independent multi-label and semantic-aggregation
design after asking whether the existing Catalog already provides it. Distinguish
these content Themes from collection/evidence-based research-scope associations.
Research mappings are optional; creating a Field or Topic remains an independent
user-directed planning decision. Counts use unique paper IDs within each set;
per-Theme counts overlap and cannot be summed as a unique-paper total.

Further user clarification, 2026-10-22: direct Theme mappings are limited to Field
and Topic. Do not map Themes directly to Track/RQ or confuse these tags with the
separate research-workflow associations. This supersedes the prior draft's broader
Theme-to-Track suggestion.

The user wants discussion of the complete paper-processing design first:
initial bibliographic/QuickRead understanding, then value-driven PaperSkeleton
deep decomposition, whose internal L1–L4 layers include writing/argument structure.
Source inspection confirms QuickRead can queue Skeleton through deep_read_reasons;
the full adaptive depth/value policy remains to be agreed. Views may initiate
selection/acquisition, while Catalog-owned paper/source-version analyses should
be reusable across Views. Initial and deeper Theme evidence must remain distinct.

Further initial-reading clarification: initial understanding may be the final
chosen depth for the current purpose. Retain the paper/content card and all
provisional Themes, including unmapped labels; do not deep-read papers solely
because they exist in the Catalog. Distinguish an intentional initial-only
decision, a reasoned deep-read recommendation and insufficient information.
These are separate from job execution status and citation expansion decisions.
Current source saves QuickRead first and queues Skeleton only for nonempty
deep_read_reasons; the prompt allows empty values, so that branch alone does not
encode all three dispositions. Explicit user-requested deep read also exists.
This remains design discussion, with no new policy/status/runtime implementation.

Catalog column analysis, 2026-10-22: the user requested a missing-column audit and
the decisions they need to make while discussing the workflow. Current source
has22 configurable columns, mostly identity/files/output-presence/workflow fields.
New discussion proposal `RSTV4/docs/catalog-columns-and-decisions.md` prioritizes
Themes, source-aware Understanding, Reading disposition, optional Field/Topic
mapping and Next action. Paper type/Journal are optional additions; current Source
means import/provider rather than a dedicated venue column. Reasons/evidence and
receipt details belong in expandable details. Open choices cover initial-reading
triggers, deep-read execution policy, value reasons, machine-label review policy
and default column selection. Recommendations in that document are NOT accepted
user decisions and do not authorize automatic processing or implementation.

Design: `C:/Users/Alandelone/CodeSpace_Local/RSTV4/docs/catalog-themes-and-semantic-aggregation.md`.
This turn performed read-only inspection and authored the design. It did not
implement or publish a Themes feature, assign paper labels, merge vocabulary,
run inference, migrate the Catalog, or resume research jobs. English labels and
authored research artifacts follow the existing Scholar content-language policy.

## User response, 2026-10-23

This response supersedes the earlier open-choice/recommendation descriptions
where specified below; retain the preceding paragraphs as discussion history.

- All newly imported papers should receive automatic initial reading in the
  background. This is not limited to a selected View or an opted-in Collection.
  Source readiness and actual abstract/full-text coverage remain explicit.
- The user accepted reasoned deep-reading recommendations and batch decisions,
  and requested an example explaining how reasons are selected and displayed.
  Per-Collection automatic deep reading is still an optional explicitly enabled
  mode; automatic initial reading does not enable it.
- The user wants broader and more detailed value dimensions, including the whole
  writing structure, argumentation, viewpoints, synthesis, technical and research
  methods, data and further useful dimensions. Do not reduce deep reading to a
  fixed shortlist or a single paper-quality score.
- Machine-proposed Themes are immediately visible, searchable and available to
  aggregation as candidates, retaining their review state and evidence. Candidate
  inclusion does not approve scientific claims or vocabulary merges.

Companion design: `RSTV4/docs/catalog-reading-value-and-reason-examples.md`.
It proposes evidence -> observed feature -> purpose/value -> unresolved detail ->
expected deep-reading output, an extensible dimension catalog and a hypothetical
review-paper example. Its detailed schema/display choices are proposals rather
than further user approvals. Default Catalog column presentation remains open.
This response updates design and policy memory only; no worker/deployment change,
live inference, historical backfill or new research job has been performed.

## PaperSkeleton binding reaffirmed, 2026-10-23

The user explicitly reaffirmed that deep decomposition and all the discussed
evaluation dimensions are concerns of the existing PaperSkeleton framework and
must be strongly bound to it. PaperSkeleton remains the canonical semantic and
writing-structure framework. Initial reading previews the same dimensions; deep
reading produces the source-located versioned Skeleton; dimension views and
Themes refinement use its units, propositions, relations, intents and macro roles.
Do not create a parallel assessment/extraction framework or 22 new sequential
layers. A preliminary assessment binds to real source spans and intended layer
targets without fabricating a completed Skeleton or unit IDs.

Architecture document: `RSTV4/docs/catalog-paperskeleton-bound-workflow.md`.
It maps every dimension to combinations of L1-L4, defines shared profile/version
and evidence links, preserves optional initial-only outcomes, and distinguishes
multi-paper derived comparisons from each original paper's Skeleton. The user
requested a complete visible workflow; final response should show the flow and
the shallow-preview -> full-Skeleton -> grounded-view binding.

Source review found the current QuickRead prompt has no shared dimension profile;
the inspected acquisition handler runs block-local four-layer calls; its following
assessment model payload uses parsed blocks rather than Skeleton units. Existing
typed source/atom/relation/intent/macro-role contracts and parser-outline identity
are useful foundations. The proposed strong binding is not fully implemented by
these pieces alone. This clarification edits design/memory only, with no runtime,
database, model, research job, deployment or gate change.

## Continued framework discussion, 2026-10-23

The user asked whether the implementation architecture has any issues and asked
to continue discussing the framework. Respond with the bounded finding: the
proposed architecture is consistent with the original PaperSkeleton direction,
but its complete implementation and correctness have not been certified.

Extended `RSTV4/docs/catalog-paperskeleton-bound-workflow.md` with proposed
component responsibilities, source/version ownership, reuse across Views and
purposes, independent status dimensions, completion meanings and implementation
connections. These elaborations are proposals, not additional user-approved
policy. Catalog owns canonical papers/sources; initial reading previews shared
Skeleton definitions; PaperSkeleton owns deep structure; content facets and
purpose judgments reference evidence; global Themes preserve unmapped content;
research-scoped FieldKG use consumes explicit references. Strong semantic binding
does not require a shared process/database or an artificial Field for all papers.

Distinguish source readiness, understanding depth, reading disposition, execution,
semantic coverage, record review and freshness. A completed initial card plus a
deep recommendation with no requested job is coherent. Full-source extraction,
complete dimension understanding and scientific acceptance remain distinct.
No runtime/source/DB/job/model/deployment change or mission gate approval was
performed in this continuation. Default column presentation remains open.

## Per-paper contracts and reuse continuation, 2026-10-23

The user's next "continue" remains framework discussion, not a request to switch
to implementation or deployment. Extended the same architecture document with
proposed logical records, change/reuse rules, task coordination/version-bound
publication and a first end-to-end implementation increment. Do not present
these detailed choices as new user approvals.

Separate source-backed initial content from purpose-specific usefulness/depth
judgments. Reimporting an identified source or using another View should reuse
compatible understanding. Theme aliases/mappings change projections rather than
force rereading; changed source/profile contracts require explicit compatibility
checks and only necessary new work. Model configuration changes alone do not
silently rerun the corpus. Running jobs freeze their inputs; late old-version
results cannot overwrite current-source cards or decisions. A compatible existing
Skeleton can support a derived initial card when coverage/contract requirements
are met; do not fabricate a purpose assessment or force redundant QuickRead.

First proposed coherent increment: import -> background initial understanding ->
candidate Themes/evidence -> reasoned depth recommendation, with requested deep
work bound to existing PaperSkeleton. Example acceptance inputs are multi-Theme
review/unmapped content, useful initial-only output and honest limited/partial
coverage. This remains documentation only; no source/runtime/DB/model/task change,
test execution, migration, service publication or mission gate approval.

## Product-level acceptance and open-decision audit, 2026-10-23

The user explicitly accepted the preceding per-paper structure/reuse/workflow
proposal and requested an audit of what still needs discussion. Record that the
five information groups, compatible reuse across Views/purposes, necessary-only
reprocessing and end-to-end flow are accepted product direction. This does not
approve every proposed contract field, physical schema, scheduler or deployment.

Added a confirmed/open-decision section to the same architecture document. The
remaining choices are: existing-library backfill scope/order, missing full-text
automatic acquisition, Theme coverage-role presentation/count defaults, durable
user-correction/reproposal semantics, and default column/detail layout. Suggested
behaviors are proposals and not yet accepted defaults. Do not reopen already
accepted automatic new-import initial reading, candidate Theme inclusion, broad
unmapped vocabulary, Field/Topic-only Theme mappings or PaperSkeleton binding.

Engineering verification includes version/coverage/source integrity, task reuse,
resume and late-result behavior, real Skeleton-backed assessment and existing
preference preservation. The original requested KG server migration/endpoint
availability remains a separate delivery item to verify, not a completed result
established by this design discussion. No service inspection/deployment or new
model/job/backfill has occurred in this turn. No source/runtime/DB/UI changes or
mission gate approval; only design and append-only policy memory updated.

## Full-text gate and night processing confirmed, 2026-10-23

The user's annotated reply settles the first two choices and adopts the preceding
recommendations for the other three. These rules supersede earlier abstract-only
fallback proposals and the earlier open-choice list; preserve that history.

- Incomplete per-paper results must expose the missing stage. Complete eligible
  work gradually in night-time batches with resources reserved for interactive
  use rather than running the backlog while the user is working.
- A readable full-text PDF is mandatory before even initial reading, not merely
  before PaperSkeleton. Missing full text means acquisition/source work remains.
  Retain discovery metadata, but do not run abstract-only initial/deep analysis
  or create new inferred content Themes as a fallback. Historical limited outputs
  are retained as history and do not fulfill the current gate.
- The user's explicit follow-up sets the window to00:00-08:00 Asia/Kuala_Lumpur
  and chooses all automatic reading to wait for night; manual requests take
  priority. Creating an import/reading intent is not immediate execution or an
  explicit manual read. Manual work still requires full text.
- The user accepts coverage roles (central/substantial/passing mention), all
  retained/searchable with clear filtering/count scope; correction with history
  respected by future processing and changed-evidence candidates; and the default
  columns Name/Themes/Understanding/Reading disposition/Next action/Year/PDF status,
  with other columns optional and evidence expandable. Preserve saved preferences.

Updated all four Catalog design documents consistently, including active source
readiness, completion definitions, mermaid flow, initial-reading examples and the
decision register. The operating choices are no longer open. Exact stage labels,
batch sizes, capacity coordination and safe checkpoint mechanics remain technical
implementation proposals. No arbitrary quota/concurrency number is approved.
Do not auto-deep-read a mere recommendation, resume human-paused/stopped work,
discard valid progress at08:00 or claim instant preemption of in-flight model calls.

Inspection of the local acquisition worker found ordinary durable claim/complete/
defer operations and a polling loop; the inspected loop has no night-window
admission check. This is a source observation, not a complete audit of any external
scheduler or the server. No runtime/scheduler/app automation was activated, no
model/backfill/deployment occurred, and no mission gate changed. Final response
must address both annotations using :codex-annotation index1 and index2, state
the confirmed window/manual priority, and distinguish recorded design from live
implementation.


## Catalog implementation checkpoint, 2026-10-24

Implementation has begun under the existing proceed authorization. See
`scholar-catalog-implementation-20261023.md` and RSTV4
`docs/catalog-implementation-progress.md` for current evidence and the complete
remaining scope. Canonical Themes, review history, separate purpose judgments,
scope-independent initial jobs/receipts and semantic HTTP operations now exist
in development. Generic initial recommendations are LIBRARY_OVERVIEW, not
purpose-specific scientific decisions. At00:06 KL the actual Catalog remained
schema14, so these features were not active in that production runtime. The full
objective remains unfinished; historical design-only statements above are kept
as history, not a claim about later source implementation.
