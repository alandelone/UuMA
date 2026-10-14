---
name: yonc-colleagues
description: Understand UuMA colleagues, their inputs, deliverables and authority before proposing project work assignments.
---

# Yonc colleague roles and work allocation

Use this skill when identifying who could perform a project work package. The full role
documents are deployed under `references/`; the source manifest records each source and SHA-256.
The role descriptions explain intended ownership. They do not certify every feature as deployed.

Call the directly available `mcp__uuma_worker__yonc_get_colleague_capabilities` before a concrete
proposal. With no arguments it returns the registered roster; `agent_id` selects one colleague
and `capability` filters an exact capability tag. The receipt includes current registration,
declared capabilities, permissions, workload counts, source references and observation time.
An enabled registration means enabled in UuMA, not online. Domain service readiness is NOT_CHECKED.
Unavailable role sources, unregistered roles and failed queries stay explicit.

## Work guide

| Colleague | Suitable work | Supply | Expected deliverable | Boundary |
| --- | --- | --- | --- | --- |
| Brainstormer | Problem framing, alternatives, decision analysis, PRD and architecture | Goal, constraints, current options and sources | Reasoned options, assumptions, unresolved questions and a design proposal | Owns reasoning state; no specialist facts or cross-Agent dispatch by assertion |
| Scholar | Literature and scientific evidence, research gaps, methods, experiments and writing | Research question, Track, available papers/evidence, scientific approvals | Evidence synthesis, candidate gaps or Blueprint, research/manuscript artifact | User owns scientific decisions; graph readiness and approved RSTV4 plans required; check deployed workflows |
| Wisdom-Oldman | Mechanisms, conditions, conflicts, knowledge gaps and best-current answers | Specific question, purpose, conditions, scope and sources | Evidence-linked answer, topic document and worthwhile gaps | Own knowledge graph required; new-topic approval and budget boundaries apply |
| Forge Lab Bot | Inventory and purchase evidence, BOM/build assessment, sourcing advice, worklogs and failures | Object/specification, design/order references, observations and physical state | Inventory/order evidence, build or failure analysis, worklog and candidate lesson | Purchase evidence is not on-hand stock; no payment or hardware actuation; lessons need review |
| Orchestrator | Accepted task routing, dispatch, coordination, monitoring and governed computer operations | Accepted scope, inputs, deliverables, acceptance criteria and permission needs | Task/Run receipts, status, results, verification or blocker | Enforces execution policy and user approval; Yonc does not bypass it |
| Yonc | Project context, decomposition, portfolio recommendations, assignment proposals and progress review | Current project graph, goals, constraints, decisions, sources and colleague data | Saved graph draft, proposed work packages and reviewable progress | Graph writes use exact-version trusted UI authorization; dispatch remains a handoff |

eSchematic is a domain system for components, schematics, design BOMs and revisions. Propose
supported design work through the available integration, normally coordinated with Forge Lab Bot.
CopyCat is an Orchestrator-controlled computer service. Do not list either as an independent Agent.

## Read the full sources

- `references/brainstormer.md` and `references/brainstormer-SOUL.md`
- `references/scholar.md` and `references/scholar-SOUL.md`
- `references/wisdom-oldman.md` and `references/wisdom-oldman-SOUL.md`
- `references/forge-lab-bot.md` and `references/forge-lab-bot-SOUL.md`
- `references/yonc.md` and `references/yonc-SOUL.md`
- `references/agent-index.md` and `references/orchestrator-policy.md`
- `references/source-manifest.json`

Use skill_view with the relevant reference file for detail. These are source snapshots from
deployment; refresh current capabilities with the semantic lookup rather than inferring availability
from a source document's historical status heading.

## Make a useful proposal

1. Define the outcome and the current project/node scope. Identify prerequisites and source gaps.
2. Match the work to registered capability tags and the full role boundary. The user may do work
   personally; do not force every node into an Agent assignment. Explain any provisional match.
3. Specify worker, reason, bounded work, inputs and sources, dependencies, deliverable, acceptance
   criteria, timing/budget if known, permission needs and proposed project effects.
4. Show the proposal for user review. Separate acceptance of graph changes from assignment items.
   Execution requires Orchestrator validation and an actual dispatch receipt. Current Yonc tools
   do not dispatch or persist a dedicated assignment record; describe that handoff as pending.
5. Check returned evidence against acceptance criteria. A finished Agent Run alone does not
   complete a project node. Preserve source ownership and unresolved review issues.
