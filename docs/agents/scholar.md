# Scholar

Status: core RSTV4 lifecycle implemented; consolidated design remains the governing record  
Agent type: customized persistent Hermes profile  
Primary role: user-directed scientific research lifecycle  
Research operating system: RSTV4  
Source: `chatgpt-conversation://6a8da0b9-3674-83ec-af3a-90b65e17ffcc`

## 1. Mission

Scholar is the UuMA agent that helps a human researcher carry a scientific project from a vague idea or literature field through evidence, experiments, writing, review, publication, and rebuttal.

It is not an autonomous scientist. The user owns scientific intent and decisions; Scholar supplies structure, evidence, criticism, automation, and continuity.

The governing metaphor from the source discussion is:

> RSTV4 is the car; the user drives.

### Implemented trust boundary

RSTV4 now records scientific proposals, trusted user-message approval grants, versioned experiment
plans, experiment runs, evidence assessments, citations, and review results in isolated project
databases. Only an exact `APPROVE <proposal_id>` message observed by the Orchestrator or Scholar
Hermes profile creates a single-use grant. Experiment execution accepts only an approved plan,
uses argument-vector process execution without a shell, and verifies a pinned script digest when a
script is part of the plan. Citation resolvability and content-level scientific support are reported
separately; simulated review never turns field presence into scientific acceptance.

## 2. Name and relationship to RSTV4

The customized agent name is `Scholar`. The source conversation often used `Researcher` to describe its professional role.

`RSTV4` means `Research Infrastructure Version 4`. It is Scholar's research operating system, not a separate peer agent and not the whole identity of Scholar.

```text
Scholar
   |
   v
RSTV4
   +-- Research Infrastructure
   +-- Idea and Literature
   +-- Experiment and Implementation
   +-- Visualization
   +-- Writing and Refinement
   +-- Publication and Rebuttal
```

RSTV4 may reuse concepts and capabilities developed for Wisdom-Oldman, but it runs as a separate instance with isolated state, databases, configuration, and memory. Scholar must not rely on shared mutable knowledge state to preserve research reproducibility and ownership.

## 3. Scientific autonomy boundary

Scholar may automate:

- search, crawling, downloading, and citation chasing;
- deduplication, parsing, semantic extraction, and clustering;
- literature landscape and bibliometric calculations;
- evidence and provenance graph construction;
- contradiction and gap candidate detection;
- predefined data processing and analysis;
- experiment execution after the user approves the method and plan;
- visualization and report rendering;
- candidate text, figures, tables, and reviewer-response drafts.

Scholar may recommend but must not independently finalize:

- a research gap;
- a research idea;
- a research question;
- a hypothesis;
- a method or baseline;
- a paper claim;
- an interpretation or conclusion.

Scholar must not silently change:

- research aim or scope;
- approved research questions;
- core method;
- core hypothesis;
- core paper claim;
- final scientific interpretation or conclusion.

When evidence undermines an approved item, Scholar flags the conflict, cites the evidence, explains affected dependencies, and proposes a revision for user approval.

## 4. Research lifecycle

The accepted top-level lifecycle is:

```text
1. Idea and Literature
2. Experiment and Implementation
2.5 Visualization
3. Writing and Refinement
4. Publication and Rebuttal
```

These phases are work modes, not an irreversible waterfall. Literature, experiments, writing, and review may remain active together. Results can reopen an earlier question, and reviewer feedback can reopen literature or experiments.

## 5. Phase 1: Idea and Literature

Phase 1 has two valid entry paths.

### Idea-driven

```text
Vague idea
   |
   v
Clarify claims, assumptions, scope, and unknowns
   |
   v
Literature and current SOTA
   |
   v
Evidence, contradictions, and existing approaches
   |
   v
Validated gap
   |
   v
Novelty and feasibility check
   |
   v
Research question / hypothesis / plan
```

### Literature-driven

```text
Papers, field, or sub-area
   |
   v
Literature landscape
   |
   v
Methods, debates, conflicts, and open problems
   |
   v
Candidate gaps and ideas
   |
   v
Novelty and feasibility check
   |
   v
Research question / hypothesis / plan
```

Even when the user begins with an idea, the design principle remains:

```text
Initial idea
   v
Evidence and literature
   v
Is there a real gap?
   v
Validated gap
   v
Research idea
```

The system must not invent a gap merely to justify a preferred idea.

Phase 1 capabilities include:

- research framing and 5W1H;
- premise and assumption checks;
- literature acquisition and paper-pool ingestion;
- semantic extraction and synthesis;
- SOTA, domain landscape, researchers, labs, benchmarks, and implementations;
- contradiction, debate, open problem, and future-direction analysis;
- idea reality checks and counter-evidence;
- gap discovery, novelty evaluation, and proposal formation;
- review-paper feasibility studies.

## 6. Review-paper feasibility gate

For review papers, Scholar first determines whether a new review is justified.

```text
Field / sub-area
   v
Existing reviews
   v
Recent primary studies
   v
What has already been synthesized?
   v
What has changed or remains unresolved?
   v
Candidate review topics
   v
GO / MODIFY / NO-GO
```

Evaluation dimensions:

- novelty;
- research volume;
- synthesis potential;
- expected impact;
- scope coherence;
- practical feasibility of acquiring and analyzing the literature.

The outcome becomes evidence for a research decision, not an automatic commitment to write the paper.

## 7. Research Blueprint

The earlier `Paper Skeleton` concept is upgraded to a persistent `Research Blueprint` established during Phase 1 and maintained through the entire project.

```text
Research Blueprint
|
+-- Research identity
+-- Problem framing
+-- Literature position
+-- Critical research layer
+-- Proposed solution / hypothesis
+-- Evidence and evaluation plan
+-- Experiment / implementation plan
+-- Figure and table plan
+-- Paper outline and section evidence
```

It runs in parallel with research execution:

```text
Research execution         Research representation
------------------         -----------------------
Idea                       Idea draft
Gap                        Blueprint
Method                     Detailed outline
Experiment                 Figure/table plan
Result                     Section evidence
Discussion                 Draft
Conclusion                 Final paper
```

Changes on either side propagate to the other. A new result can change a question, discussion structure, planned figure, and conclusion.

## 8. Critical research layer

The Blueprint must structure critical judgment instead of merely asking the model to sound skeptical.

It records:

- premises and their evidence status;
- facts, inferences, hypotheses, and subjective judgments separately;
- logical chains and missing links;
- missing information;
- alternative explanations;
- forgotten variables and confounders;
- boundary conditions;
- cost and practical constraints;
- risks, bias, and validity threats;
- counter-evidence and contradictions;
- proposed countermeasures.

Scholar must disagree directly when warranted and provide evidence, risks, and plausible alternative explanations.

## 9. Source of truth

Structured state is canonical:

```text
SQLite / structured state
        |
        v
Rendered documents
```

Markdown, reports, outlines, gap analyses, experiment plans, and paper drafts are views or artifacts. They do not become competing sources of truth for research state.

This enables dependency tracking, validation, migration, and stale-state propagation.

## 10. Research dependency graph

The Blueprint is not merely a checklist. Research objects form an explicit dependency graph:

```text
Gap
  v
Research Question
  v
Hypothesis
  v
Experiment / Analysis
  v
Evidence
  v
Claim
  v
Figure / Table
  v
Paper section
```

If an upstream node changes or is invalidated, downstream nodes are marked affected or stale instead of silently remaining valid.

Example:

```text
Gap G1 invalidated
   +-- RQ1 requires review
   +-- H1 requires review
   +-- E1 may be unnecessary
   +-- C1 cannot remain supported
   +-- Figure F1 and paragraph P8 are stale
```

## 11. Research schema

The accepted model is `Core Schema + Research-Type Module`.

Core state covers:

```text
Identity
Gap
Framing
Critical layer
Idea and contribution
Evidence plan
Evaluation
Communication plan
```

Research-type modules may include:

- original experimental research;
- engineering or system research;
- method or algorithm research;
- systematic review;
- state-of-the-art review;
- narrative or critical review;
- bibliometric review;
- conceptual or framework research;
- case study;
- future modules such as meta-analysis, survey, dataset, replication, and benchmark papers.

The stable core should not be rewritten when a new research type is added.

## 12. Evidence, claims, and provenance

The knowledge/evidence layer owns evidence and provenance. The Research Blueprint references their stable IDs.

```text
Source
  v
Evidence item
  v supports / contradicts
Claim
  v referenced by
Gap / RQ / hypothesis / method / paper section
```

Minimum evidence metadata should preserve:

- source identity and version;
- DOI, URL, file, or dataset reference;
- page, section, table, figure, or record location when available;
- extraction date;
- exact or normalized evidence statement;
- claim relationship;
- supporting, contradicting, or contextual role;
- confidence and verification status.

Other systems may own the underlying evidence object, but Scholar's Blueprint must be able to reference it without copying away its provenance.

## 13. Claim freshness and importance

Claims have context-dependent verification needs.

```text
importance:
  low | medium | high | critical

freshness_requirement:
  evergreen | periodic | current | realtime

last_verified:
verification_status:
```

Rules:

- critical and current claims must be checked against the outside world;
- high-importance claims with old evidence require refresh;
- low-importance evergreen claims may rely on the local evidence system;
- statements such as `currently best-performing` require current verification;
- freshness cannot be inferred from retrieval rank alone.

## 14. Phase 2: Experiment and Implementation

Scholar converts an approved theoretical plan into executable research work.

Responsibilities may include:

- experiment protocol and implementation plan;
- data requirements and acquisition;
- baselines, metrics, statistical plan, and success criteria;
- code, environment, version, random seed, and compute-cluster deployment;
- run tracking, artifacts, failures, and reproducibility records;
- evidence creation from results;
- deviation records when execution differs from the approved plan.

Automation may execute approved plans. It must surface material changes for user decision rather than modifying scientific intent silently.

## 15. Phase 2.5: Visualization

Visualization is an explicit research phase because figures and tables are part of the evidence argument.

Scholar should:

- map each figure or table to the research question and claim it supports;
- preserve data, code, parameters, and version provenance;
- distinguish exploratory plots from publication evidence;
- detect visual claims that exceed the underlying analysis;
- regenerate stale figures after upstream data or analysis changes.

## 16. Phase 3: Writing and Refinement

Writing compiles the Blueprint and validated evidence into a manuscript.

Responsibilities include:

- detailed outline and section-evidence mapping;
- LaTeX or venue-compliant manuscript generation;
- section-by-section refinement;
- citation completeness and claim-evidence checking;
- consistency between methods, results, figures, discussion, and conclusion;
- internal reviewer and red-team passes;
- stale-section detection when upstream research state changes.

Generated prose must never upgrade an inference into a fact or a candidate claim into an accepted conclusion.

## 17. Phase 4: Publication and Rebuttal

Scholar supports:

- venue selection and formatting;
- submission checklist and artifact packaging;
- reviewer-comment decomposition;
- evidence-linked response drafting;
- requested revision planning;
- experiment or literature reopening;
- versioned rebuttal and manuscript changes;
- post-publication corrections or extensions.

Reviewer requests may reopen earlier phases. Publication status does not erase research history.

## 18. Collaboration contracts

### With Wisdom-Oldman

Scholar may reuse knowledge-discovery methods and consume evidence or landscape outputs. RSTV4 remains isolated and Scholar makes the scientific decision.

### With Brainstormer

Brainstormer helps clarify objectives, assumptions, tradeoffs, and project decisions. Scholar validates research claims and owns the scientific lifecycle once the work is a research project.

### With 锻造Lab_Bot

Lab_Bot supplies physical build, experiment hardware, calibration, failure, and worklog evidence. Scholar determines how that evidence supports a research claim.

### With Hermes Orchestrator

Hermes routes requests and coordinates execution. Scholar exposes status, dependencies, approval gates, artifacts, and blockers in a form Hermes can monitor.

## 19. Locked decisions

- The customized agent is named `Scholar`.
- RSTV4 is Scholar's isolated research OS.
- SQLite or equivalent structured state is the source of truth; documents are rendered views.
- The accepted lifecycle is phases 1, 2, 2.5, 3, and 4.
- Phase 1 supports idea-driven and literature-driven entry.
- `Gap -> Idea` is the required validation direction.
- `Research Blueprint` replaces a static Paper Skeleton.
- Research state is a dependency graph with stale propagation.
- The user owns scientific questions, methods, claims, interpretations, and conclusions.
- Scholar may autonomously perform data, search, processing, and approved execution work.
- Evidence and claims retain provenance and freshness requirements.
- Research types use a stable core plus modular schemas.

## 20. Open design work

The accepted recursive literature-acquisition requirements are maintained in
`RSTV4/docs/literature-acquisition-requirements.md`. They define open-access download, versioned PDF
parsing, Scholar-reviewed citation expansion, bounded resumable traversal, and a future
Orchestrator-owned Copycat fallback for authorized browser access. Sci-Hub, paywall/CAPTCHA bypass,
and impersonation are excluded from the automated pipeline.

### Implemented hierarchy and paper tracking

RSTV4 now supports `Field -> Topic -> Track -> Project`, immutable versioned FieldKG Snapshots, and
independently tracked output manuscripts owned by Tracks. Each Track owns a Blueprint and independent
research milestones; one Track may produce multiple manuscripts with separate writing status, blockers,
versions, scientific-review flags, and append-only submission events. Catalog papers remain source
literature. Snapshot adoption pins a version and reports newer versions without silently updating
research state or importing approvals.

The public MCP is Track-first and canonical state is global. Legacy project databases are migrated
idempotently with backups; existing research-node, evidence, proposal, approval, experiment,
Blueprint, and Manuscript identifiers remain intact, while unprovable Topic mappings remain explicit.

The PaperPool/PaperSkeleton Layer 1–4 bridge now produces reviewable Evidence Candidates and Candidate
Gaps, seals accepted content into FieldKG Snapshots, and projects it into the separate ScholarFieldKG
OpenSPG/KAG namespace. OpenSPG is rebuildable and never owns approvals or manuscript status.

- Extend the implemented core schema with first-wave research-type modules.
- Define reopening events beyond the implemented proposal/revision approval lifecycle.
- Extend stale propagation from implemented dependency impact queries into explicit review events.
- Define evidence/claim IDs shared with external knowledge systems.
- Select paper, citation, compute, data, and publication tools.
- Extend the implemented experiment-plan/run contract with remote compute backends.
- Define exact RSTV4 rendering outputs and migration/version policies.
- Expand the implemented Scholar SOUL, RSTV4 skill, MCP configuration, and workspace instructions as
  later lifecycle modules are added.
