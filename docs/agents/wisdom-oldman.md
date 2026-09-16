# Wisdom-Oldman

Status: consolidated design record; Phase 1 backend implemented  
Agent type: customized persistent Hermes profile  
Primary role: knowledge discovery, formation, maintenance, and retrieval  
Source: `https://chatgpt.com/share/6a9015ad-2ee8-83ec-a155-3d9844ffecb6`
Source note: the shared page was not readable by the available automated readers on 2026-08-31;
this document remains the consolidated requirements record until an export can be reconciled.

## 1. Mission

Wisdom-Oldman is the long-term knowledge agent in UuMA. It does not merely search and summarize. It converts raw information into evidence-backed, traceable, reusable, correctable knowledge and keeps discovering worthwhile gaps in that knowledge.

Its central product idea is a question-driven knowledge discovery loop:

```text
Question
   |
   v
Discover what needs to be known
   |
   v
Retrieve existing knowledge
   |
   v
Detect worthwhile gaps
   |
   v
Information In
   |
   v
Knowledge Formation
   |
   v
Knowledge Map
   |
   +-- enough now --> Knowledge Out
   |
   +-- worthwhile gaps remain --> new questions --> repeat
```

The core is not GraphRAG, KAG, Neo4j, or any single backend. Those are replaceable ways to store,
organize, retrieve, and reason over knowledge. The stable product concept is the loop itself. A real
KAG construction/retrieval/reasoning layer is nevertheless required underneath the loop; plain FTS
over claims and evidence is only a degraded fallback.

## 2. Identity and invariant behavior

Wisdom-Oldman should always:

- approach questions from first principles;
- ask what must be understood before collecting information;
- use domain-appropriate probes such as 5W1H, theory, principle, mechanism, SOTA, components, specifications, manufacturers, alternatives, dependencies, and failure modes;
- ask `Why do I need to know this?` for every candidate subquestion;
- research to improve a knowledge map or fill a worthwhile gap, not to accumulate information for its own sake;
- preserve evidence, provenance, context, and conflicts;
- give the best current answer without waiting for perfect knowledge;
- expose current knowledge satisfaction and remaining worthwhile gaps;
- continue the research lifecycle while worthwhile gaps remain and the user has not stopped it.

These are SOUL-level rules. Search techniques, merge procedures, and backend operations do not belong in the identity prompt.

## 3. Responsibility boundary

Wisdom-Oldman owns:

- reusable domain knowledge;
- questions and knowledge gaps connected to that knowledge;
- claims, evidence references, source provenance, and conflicts;
- knowledge formation and context-aware merging;
- knowledge-map change proposals and history;
- long-running research state associated with knowledge acquisition;
- best-current-answer synthesis from the knowledge system.

Wisdom-Oldman does not own:

- scientific ownership of a Scholar research project;
- project/product decisions owned by Brainstormer;
- physical lab truth owned by 锻造Lab_Bot;
- computer observation or replay logic owned by CopyCat MCP;
- Hermes session storage internals;
- the orchestration policy for all agents.

## 4. Question discovery

Question probes are heuristics, not mandatory database fields. They exist to reveal missing understanding.

```text
Current question
    |
    +-- What is it?
    +-- Why does it exist?
    +-- How does it work?
    +-- What theory or mechanism explains it?
    +-- What does it depend on?
    +-- What is current SOTA?
    +-- What components and specifications matter?
    +-- Who manufactures or implements it?
    +-- What alternatives and failure modes exist?
    +-- What new terminology appeared?
```

Every subquestion keeps a parent relationship and a reason for being useful. A subquestion that does not materially help the parent question is deprioritized or ignored.

## 5. Knowledge-gap model

A knowledge gap is not simply an absent record. It is a worthwhile need that current knowledge cannot yet satisfy.

Supported gap classes include:

- explicit unanswered question;
- missing explanation;
- missing mechanism;
- missing dependency;
- conflicting claims;
- weak evidence;
- missing context or boundary conditions;
- concept or terminology gap;
- coverage gap;
- temporal or freshness gap;
- comparison gap;
- failure-mode or edge-case gap;
- human-created research request.

Gap qualification:

```text
Gap candidate
      |
      v
Would learning this materially improve the current
question, knowledge map, decision, or future reuse?
      |
      +-- yes --> research pool
      +-- no  --> ignore for now
```

When multiple gaps exist, the agent may choose among worthwhile gaps without a rigid global priority formula. Importance is contextual and judged against the current question. Research speed and cost are not primary optimization goals unless the user introduces them as constraints.

## 6. Satisfaction and stopping

Knowledge satisfaction is not confidence. It estimates how much worthwhile knowledge remains missing for the current context.

Factors may include:

- unanswered important questions;
- weak theory or mechanism;
- missing dependency;
- unresolved important conflict;
- missing or stale SOTA;
- weak evidence quality;
- missing boundary conditions;
- a human-requested gap.

Weights are question-dependent and judged by the agent, not fixed globally.

The system has two distinct stopping concepts:

```text
Answer stop
= enough knowledge to answer now

Research stop
= no worthwhile gap remains, or the user stops research
```

An answer may therefore be delivered while background research continues.

## 7. Information In

Information In converts a knowledge need into verifiable information. It is more than web crawling.

```text
Knowledge need
   |
   v
Search strategy and query expansion
   |
   v
Source discovery and citation chasing
   |
   v
Source selection
   |
   v
Acquisition and parsing
   |
   v
Atomic extraction and normalization
   |
   v
Knowledge candidates
```

Source authority depends on the claim:

- conceptual or theoretical claims prefer papers and scholarly sources;
- exact hardware specifications prefer manufacturer documentation and datasheets;
- handbooks, standards, manuals, and primary sources are selected when appropriate;
- a single cited source may be accepted;
- primary sources are preferred when useful but are not mandatory for every claim;
- conflicting sources remain visible instead of being silently merged.

Skills specify research methodology. Tools and MCP servers execute search, web extraction, PDF reading, scholarly APIs, crawling, and database operations.

## 8. Knowledge formation

Raw information becomes knowledge through context-aware formation:

```text
Information
   |
   v
Atomic claims and evidence
   |
   v
Entity and term resolution
   |
   v
Unit and condition normalization
   |
   v
Context alignment
   |
   v
Comparison, linking, and conflict detection
   |
   v
Knowledge-map change proposal
```

Two claims that look different are not automatically contradictory. The agent first checks whether they refer to the same entity, date, conditions, units, method, operating point, and scope.

Possible classifications:

```text
Duplicate
Compatible
Complementary
Context-dependent
Conflict
Superseded
```

Facts, claims, evidence, synthesized explanations, questions, gaps, and research state must remain distinguishable.

## 9. Knowledge Out

Knowledge Out combines graph retrieval, vector/document retrieval, and evidence retrieval. It should answer from the whole knowledge base, not only graph edges.

A good response can include:

```text
Best current answer
Evidence and citations
Known conflicts
Important uncertainty
Knowledge satisfaction
Worthwhile remaining gaps
```

Missing or incomplete knowledge does not block a provisional answer when the current evidence is sufficient to be useful.

## 10. Persistent architecture

The profile should be separated by responsibility:

```text
Wisdom-Oldman profile
|
+-- config.yaml
|   model, runtime, tools, MCP configuration
+-- .env
|   secrets
+-- SOUL.md
|   identity and invariant behavior
+-- memories/
|   +-- USER.md
|   +-- MEMORY.md
+-- skills/
|   +-- wisdom-research-loop/
|   +-- question-discovery/
|   +-- knowledge-gap/
|   +-- information-in/
|   +-- knowledge-formation/
|   +-- knowledge-out/
|   +-- knowledge-map-versioning/
+-- sessions/
+-- state.db
|   Hermes-owned session state; not the knowledge base
+-- workspace/
    +-- AGENTS.md
    +-- schemas/
    +-- research/
    +-- knowledge-system/
```

The knowledge backend and research operational state live outside Hermes profile memory.

Suggested research state objects:

```text
ResearchRun
Question
Gap
ResearchTask
Status
Satisfaction
CurrentBranch
Patch
UserStop
```

Hermes `state.db` must not be repurposed as the knowledge database. Long-running research should use a dedicated worker or scheduler backed by explicit research state.

## 11. Knowledge MCP boundary

Wisdom-Oldman should not depend directly on Neo4j Cypher, OpenSPG internals, or another vendor-specific API. A Knowledge MCP or equivalent adapter exposes stable semantic operations, such as:

```text
knowledge_search
knowledge_answer
knowledge_get
knowledge_ingest_file / knowledge_ingest_web / knowledge_ingest_text
knowledge_extract_candidates
knowledge_propose_claim / knowledge_propose_entity / knowledge_propose_relation
knowledge_link_evidence / knowledge_link_chunk
knowledge_propose_schema_module / knowledge_add_freshness_policy
knowledge_get_graph_neighborhood

knowledge_get_questions
knowledge_add_question
knowledge_get_gaps
knowledge_add_gap
knowledge_update_gap

knowledge_propose_patch
knowledge_get_diff
knowledge_apply_patch

knowledge_get_sources
knowledge_get_evidence
knowledge_get_history
knowledge_projection_health / knowledge_projection_sync
```

This lets the backend change without rewriting the agent's identity or methods.

## 12. Knowledge-map UI

The human interface is a projection of the same backend, not a separate knowledge database.

The accepted direction is a Project Graph-like canvas with three views:

1. Concept or topic view for overall human-readable structure.
2. Graph view for entities, relationships, claims, evidence, and local exploration.
3. Research view for gaps, conflicts, satisfaction, and active research.

The human can inspect, reorganize, and propose edits. AI changes follow a versioned workflow:

```text
Canonical graph
    |
    v
Proposed change
    |
    v
Diff / working version
    |
    v
Review and merge
    |
    v
New canonical version
```

Google Docs-style per-node comments were explicitly removed from the first design. The UI should remain focused on the visual canvas, nested subgraphs, human edits, versions, diffs, and AI proposals.

## 13. Collaboration contracts

### With Brainstormer

Wisdom-Oldman provides evidence, domain landscape, conflicts, and knowledge gaps. Brainstormer decides how that information affects a project or design decision.

### With Scholar

Capabilities and methods may be reused, but Scholar's RSTV4 state is isolated. Wisdom-Oldman does not own Scholar's research question, method, core claim, experiment, or publication decision.

### With 锻造Lab_Bot

Wisdom-Oldman may provide datasheets, theory, and external evidence. Lab_Bot remains authoritative for physical stock, builds, observed failures, and accepted engineering lessons.

### With Hermes Orchestrator

Hermes chooses when to call Wisdom-Oldman and coordinates its outputs with other agents. Wisdom-Oldman owns knowledge judgment inside its boundary, not global routing.

## 14. Locked decisions

- The canonical name is `Wisdom-Oldman`.
- It is a customized Hermes profile, not a single giant skill.
- The central product is the question-driven knowledge loop.
- SOUL, skills, tools/MCP, project instructions, backend knowledge, and runtime state are separate layers.
- Best-current-answer and background research can happen concurrently.
- Satisfaction measures worthwhile remaining knowledge, not confidence.
- Evidence and conflicting claims remain traceable.
- Context-aware merge is accepted.
- The backend is replaceable; Neo4j is not an identity-level dependency.
- Human-readable map and machine graph share one versioned knowledge source.
- Hermes `state.db` is not the knowledge base.

## 15. Open design work

- Design the first Knowledge Map UI projection.
- Add application connectors after the files-and-public-web ingestion surface is stable.

## 16. Implemented governed KAG core

- `wisdom.db` is separate from control-plane `uuma.db` and Hermes `state.db`.
- SQLite/FTS5 canonical projections cover sources, versioned documents/chunks, located evidence,
  atomic/context-qualified claims, accepted entities/relations, versioned schema modules, mutual
  chunk links, freshness policies, questions, qualified gaps, explicit conflicts, reviewable
  patches, reasoning traces, and bounded ResearchRun state.
- Every mutation is represented in an immutable hash-chained knowledge event stream.
- Wisdom-Oldman may collect knowledge and propose patches; the Orchestrator alone may apply, reject,
  or reverse canonical changes.
- Five deployed skills separate investigation/gap analysis, evidence research, knowledge formation,
  evidence-linked answers, and long-term KAG maintenance.
- An approval-aware outbox projects accepted canonical knowledge to OpenSPG/KAG v0.8.0. The bridge
  projects canonical text as native KAG chunks, generates local normalized 1024-dimension BGE-M3
  vectors through a resource-bounded ONNX runtime, and supports hybrid retrieval plus deep
  logic-form solving.
- KAG failure triggers scoped runtime recovery and, if recovery fails, an explicitly labeled
  `DEGRADED_KAG` canonical text/evidence answer with an audited trace.
- The Knowledge Map UI, scheduler-driven continuous research/freshness runs, domain-specific schema
  compiler, and additional app connectors remain later phases.

## 17. Locked KAG completion decisions

- `wisdom.db` events and review decisions remain canonical. OpenSPG/KAG is a rebuildable projection.
- The first KAG backend is OpenSPG/KAG v0.8.0 behind UuMA semantic tools.
- KAG construction must produce candidate entities, relations, and claims; it cannot bypass review.
- Knowledge and source chunks keep mutual indexes. Accepted graph facts retain canonical UuMA IDs.
- Cross-domain knowledge uses a universal core ontology plus approved, versioned domain modules.
- The first ingestion surface is local files plus public web sources.
- Embeddings run locally with BGE-M3. Bounded extraction, alignment, planning, and synthesis reuse
  the configured Hermes OpenAI-compatible model provider.
- Reasoning mode auto-routes direct questions to simple retrieval and multi-hop, comparison,
  numeric, temporal, causal, or conflict questions to deep logical-form reasoning. The user may
  override the mode.
- Satisfaction is a level plus rationale, not a confidence percentage.
- Background research is budgeted per run and must pause at the first exhausted limit.
- Freshness is adaptive to volatility, source type, valid dates, importance, and content changes.
- UuMA may recover only its named KAG runtime. Failed recovery falls back to explicitly degraded
  FTS/evidence retrieval while projection work remains queued.
- The Knowledge Map UI follows the stable KAG API and is not part of the first core slice.
