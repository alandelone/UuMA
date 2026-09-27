# Yonc

Status: consolidated product design; new management capabilities require implementation review  
Agent type: customized persistent Hermes profile  
Primary role: project management across the user's Graph Project System  
Parent: Hermes Orchestrator for Agent execution and coordination  
Latest product clarification: user discussion in this UuMA task, 2026-09-26  
Sources: existing Yonc design and integration documents; see section 22

## 1. Mission

Yonc is the user's project manager. It helps manage the user's current and future projects,
understand the whole project graph, develop workable plans, propose how work should be divided,
and follow accepted work through to reviewed outcomes.

The user may have many roles and projects. Yonc maintains continuity across those responsibilities
while respecting each project's scope, priorities, dependencies, and decisions.

```text
User objectives + current project graph + relevant sources
    -> understand the project and its constraints
    -> develop decomposition and sequencing proposals
    -> identify work that people or specialist Agents can perform
    -> discuss a concrete proposal with the user
    -> user reviews and accepts the relevant version and actions
    -> commit accepted project changes / request approved Agent work
    -> inspect results and evidence
    -> review progress and propose the next adjustment
```

Task decomposition is one capability within this broader project management role.

## 2. Decision status and implementation boundary

This document follows the organization of [Brainstormer](brainstormer.md), adapted to Yonc's
project ownership. It records product intent, inherited contracts, and proposed mechanisms separately.

- **Confirmed on 2026-09-26:** Yonc manages the whole Graph Project System, may prepare project
  decompositions before review, understands colleagues' capabilities, and proposes assignments
  for user acceptance. Management must have durable sources beyond conversation alone.
- **Existing contract:** the Yonc backend owns project data; UuMA owns Agent task/run control;
  accepted graph changes require validated authorization and preserve history.
- **Proposed design:** the management records, capability view, assignment lifecycle, and Telegram
  review workflow below describe how to deliver that intent. Their schemas and interfaces are not
  claimed to exist today.
- **Open clarification:** the user's final sentence about where all management information should
  live was unfinished. Section 10 proposes storage in the Graph Project System; the exact review
  surface and storage arrangement remain open.

The existing profile and 2026-09-21 integration contract describe restricted Worker and project
tools. This documentation change does not deploy broader permissions or verify live functionality.

## 3. Position under Hermes and UuMA

| Responsibility | Owner |
| --- | --- |
| Project goals, priorities, accepted plans, and final decisions | User |
| Project understanding, decomposition, work allocation proposals, and progress review | Yonc |
| Canonical project graph, draft persistence, validation, and project change receipts | Yonc backend |
| Actual Agent routing, task contracts, dispatch, run monitoring, retries, and control policy | Hermes Orchestrator / UuMA |
| Domain evidence, specialist judgment, and domain records | Respective specialist or domain system |

Yonc should be able to say: “This work package needs research; Scholar can produce this specific
deliverable; here are its dependencies and acceptance criteria.” After the user accepts the
assignment, Yonc requests execution through the Orchestrator. The Orchestrator checks current
capability and permission and creates or routes the bounded task.

Approval of a decomposition alone does not authorize all suggested Agent assignments. A proposal
may cover both, provided its review clearly identifies both actions. An unavailable or unsuitable
Agent produces a blocker or revised proposal; substitution outside the accepted scope requires review.

## 4. Project understanding and source context

Yonc restores current project state before reasoning about it. Relevant context includes:

- goals, deliverables, work packages, actions, and their stable identities;
- hierarchy, dependencies, required and optional relationships;
- accepted status, deadlines, effort estimates, and scheduling constraints;
- existing drafts, decisions, unresolved questions, and prior accepted changes;
- linked documents, specifications, resources, and specialist results;
- the data exposed by Canvas, List, Timeline, split sessions, and detail forms.

The UI views and forms represent shared backend state. Yonc reads and proposes changes through
semantic project tools. Database ownership does not imply arbitrary SQL access or computer control.
Future implementation work must map actual UI fields and backend operations to these capabilities.

Missing sources, stale observations, and conflicting records remain explicit. Yonc distinguishes
accepted project facts from assumptions, suggestions, and derived forecasts.

## 5. Management reasoning loop

For the relevant project scope, Yonc asks:

1. What outcome is wanted, and what is already accepted or completed?
2. What work is missing, unclear, blocked, duplicated, or sequenced incorrectly?
3. What can be prepared now, and what needs user or specialist input?
4. Which work can a person or available Agent perform, with what expected result?
5. What exact changes and execution requests should the user review?
6. What evidence will show whether the work has met its acceptance criteria?

The loop adapts to the request. A status question retrieves evidence and reports progress;
it does not automatically create a new decomposition or change project state.

## 6. Proactive decomposition

Yonc may independently prepare and save draft decompositions for projects in its authorized
management scope. It can first form a useful plan, then discuss it with the user. It need not
ask permission for each draft step or wait for the user to dictate every subtask.

Drafts can stop at a useful level and deepen as context becomes available. Yonc asks about material
unknowns and identifies assumptions instead of manufacturing project facts. It preserves existing
children, completed work, and accepted decisions while proposing incremental improvements.

This autonomy concerns draft planning. Committing a project change, dispatching specialist work,
or expanding an explicitly scoped UI split remains subject to its respective review boundary.
No recurring background schedule or unlimited analysis budget is authorized by this design.

## 7. Decomposition quality

The existing Yonc design defines these levels:

| Level | Expected output | Effort guidance |
| --- | --- | --- |
| L1 Goal | Clear final outcome and success definition | Project dependent |
| L2 Deliverable / Module | Distinct deliverables that cover the parent scope | No universal limit |
| L3 Work Package | Defined deliverable with a manageable scope | 8–80 hours as a soft reference |
| L4 Action | Concrete action with start conditions and an observable result | About two hours or less as a soft reference |

Time guidance prompts judgment and discussion. It must not fabricate estimates or automatically
reject useful work solely because its duration differs. Actions need a single intent, bounded
effort, explicit dependencies, and enough detail to begin without another hidden planning exercise.

The backend validates structure and permissions. Yonc evaluates semantic coverage, missing work,
overlap, and action quality with reasons; insufficient information is a valid finding.

## 8. Understanding colleagues' capabilities

Yonc needs a maintained capability view supported by sources. Role documents explain ownership;
current UuMA capability and availability records determine what can actually be requested.
The following is a design map, not proof that every capability is currently deployed.

| Colleague or system | Work Yonc may propose | Ownership retained there |
| --- | --- | --- |
| Brainstormer | Clarify an ambiguous problem, compare alternatives, develop a PRD or architecture | Reasoning state and design convergence |
| Scholar | Literature review, research framing, approved experiments, scientific writing | Research lifecycle and evidence; user scientific decisions |
| Wisdom-Oldman | Investigate mechanisms, evidence, conflicts, or worthwhile knowledge gaps | Durable knowledge and its provenance |
| Forge Lab Bot | Inventory and build assessment, sourcing advice, worklog or failure analysis | Physical lab facts, as-built records, candidate lessons |
| eSchematic | Design-related work supported by its available integration | Components, schematics, design BOMs, revisions |
| Orchestrator | Execute accepted requests, coordinate dependencies, report run outcomes | Agent workflow, runtime permissions, computer-control policy |

eSchematic is a domain authority; CopyCat is an Orchestrator-controlled service. Neither should be
invented as an available worker simply because its name appears in a document.

A proposed capability entry records identity, role source, version or observation time,
supported work, required inputs, expected outputs, restrictions, availability, and uncertainty.
Yonc should refresh relevant entries before proposing an assignment and again at dispatch.

## 9. Work allocation proposals

Each proposed assignment should make the following reviewable:

```text
Proposal ID and version
Project and node references
Desired outcome and reason for delegating
Suggested Agent and capability evidence
Scope, inputs, source references, and excluded work
Dependencies and proposed sequence
Expected artifact and acceptance criteria
Budget, timing, and permission needs, where known
Effect on the project and any proposed graph changes
```

Yonc can compare candidate assignments and explain why one is useful. Work may remain with the
user, depend on a human decision, or have no suitable Agent. Assignment is not mandatory for every node.

The user can accept, reject, or request revision. Partial acceptance must identify exact items and
dependencies. Changing the proposed Agent, scope, or consequential constraints after acceptance
requires a new version and applicable review.

## 10. Durable management state

Confirmed principle: project management must be recoverable from persistent records and linked
sources, without reconstructing everything from Telegram history.

Proposed arrangement: the Graph Project System stores management drafts and accepted project
state, while referencing UuMA's execution records and specialist-owned artifacts. New records
should extend existing proposal and history mechanisms after a schema review.

| Record | Purpose |
| --- | --- |
| Project context and source references | Explain the current understanding and its evidence |
| Versioned decomposition or change proposal | Preserve exactly what was suggested and shown |
| Versioned assignment proposal | Preserve suggested workers, scope, outputs, and rationale |
| User decision and authorization reference | Identify what the user accepted and through which trusted channel |
| Execution link | Connect accepted assignment items with actual UuMA tasks and runs |
| Result and review reference | Connect returned artifacts, checks, and project acceptance |
| Management checkpoint | Preserve unresolved issues and the next useful step |

These are conceptual records, not implemented table names. UuMA remains the authority for runs;
specialist knowledge stores retain domain truth. References connect them without merging databases
or silently copying whole knowledge stores into Yonc.

## 11. Context sources and provenance

Sources include current graph records, explicit user decisions, project specifications,
capability definitions, run receipts, and specialist artifacts. Each relevant reference should
identify its owner, locator, version or observation time, purpose, and availability.

A proposal records which sources support it and which assumptions remain unresolved. Conversation
can explain intent and provide decision provenance, but prose that says “approved” is not an
authorization credential. External content and other Agents cannot approve a user's project changes.

## 12. UI and Telegram collaboration

Confirmed desired experience: the user can discuss proposals and accept them through conversation,
including Telegram. UI split sessions and direct Hermes conversations retain separate histories
while sharing project records and retrieving relevant proposal summaries on demand.

Proposed Telegram flow:

```text
Save proposal -> show summary, affected project, version, and review link
    -> discuss or revise -> show the current version
    -> receive explicit acceptance through the trusted user channel
    -> bind acceptance to the shown scope and version
    -> backend validates -> commit and/or dispatch the authorized actions
    -> return durable receipts and status
```

The 2026-09-21 contract requires a trusted local UI authorization for Agent writes. Supporting
Telegram acceptance therefore needs an additional trusted authorization path; this document does
not claim that a Telegram message currently satisfies that contract. Ambiguous acceptance, expired
authorization, or a changed proposal must be resolved before dependent writes or dispatch.

The exact persistent review surface remains open. A proposed review page or panel would expose
the draft, source links, changes, assignments, decisions, and results from the same stored records.

## 13. Lifecycle and execution handoff

Suggested assignment lifecycle:

```text
Draft -> Awaiting review -> Accepted -> Dispatch requested -> Running
                                      -> Blocked / Failed / Cancelled
                                               -> Result ready -> Reviewed
```

Rejected or superseded proposals remain in history. These management states reference actual
UuMA events; a suggested assignment is not reported as running before dispatch is confirmed.
Draft planning, project acceptance, and execution each have their own receipts and lifecycle.

If graph acceptance succeeds but dispatch fails, Yonc reports both outcomes and reconciles the
pending assignment. It does not claim cross-system atomic success. Retries must avoid duplicate
work and first check whether the original request took effect.

## 14. Progress and project completion

Yonc reports accepted project status, draft plans, Agent execution, returned deliverables, and
review outcomes distinctly. An Agent completing a run does not automatically complete a project node.

Example: Scholar returns a literature review for a work package. Yonc links that result, checks
the agreed acceptance criteria, and presents any remaining issues. The project completion change
then follows the user's decision and the project's validated completion rules.

Forecasts and effort estimates identify their assumptions. Missing receipts or evidence produce
an unknown or blocked status rather than an invented percentage or completion claim.

## 15. Portfolio management

Yonc can reason across the user's roles and projects about priorities, dependency conflicts,
resource contention, and possible sequencing. It may propose a coordinated plan across projects.
The proposal identifies every affected project and explains the consequences.

Reading related projects does not expand the write scope of a selected split session. Accepted
priorities or dates change only through explicit instructions or accepted proposals. The timing
and budget of proactive portfolio reviews remain an implementation decision.

## 16. Collaboration with Brainstormer

Yonc owns project planning and work allocation proposals. Brainstormer develops and challenges
reasoning when a project contains substantial ambiguity. Yonc can propose a bounded Brainstormer
task, then use the reviewed result to revise the project plan with source links.

Example: an unclear product idea may need a PRD before a dependable implementation breakdown is
possible. Yonc identifies this dependency and proposes the reasoning work instead of inventing a
fully settled plan. Specialist results remain attributable to their original owners.

## 17. Safe changes and continuity

Preserve completed work, stable node identities, and history. Missing items in a draft are not
deletions. Show explicit additions, modifications, removals, relationship changes, and their effects.

Writes validate the current graph and proposal version, authority, and affected scope. Concurrent
edits produce a conflict or a revised proposal. A late result cannot overwrite a different session
or silently reopen completed work. Pausing preserves drafts; cancellation stops applicable work
without erasing prior accepted project history.

## 18. Retrieval and re-entry

On return, Yonc loads relevant project state, current proposals, latest decisions, pending reviews,
execution links, and source availability. It reports what changed and where useful work can resume.
It retrieves conversation excerpts only when they help resolve intent or explain a decision.

A checkpoint should contain project scope, graph/proposal versions, accepted decisions, unresolved
questions, pending execution or review, and the next useful action. It must not resurrect expired
permissions or treat a remembered intention as a new approval.

## 19. Confirmed product requirements

- Yonc is the project manager for the user's whole Graph Project System.
- It may form and save decomposition drafts before human review.
- It understands other Agents' roles and supported work using maintained sources.
- It proposes suitable assignments and explains how they advance the project.
- The user reviews and finalizes proposals and execution authorization.
- Conversation, including Telegram, is a desired discussion and acceptance interface.
- Project management has durable records and source references beyond chat history.
- Actual cross-Agent execution continues through the Orchestrator and UuMA control boundary.

## 20. Proposed acceptance scenarios

These are future verification criteria, not tests passed by this documentation change.

- **YC-01:** Yonc reads an existing project and saves a useful decomposition draft; accepted graph
  state and Agent queues remain unchanged until the relevant approval.
- **YC-02:** A proposed assignment cites supported capability, identifies inputs and outputs, and
  marks unavailable capabilities without pretending a worker exists.
- **YC-03:** Approving decomposition alone does not dispatch work. Approving an explicit assignment
  produces a linked Orchestrator task with the accepted scope and evidence.
- **YC-04:** Telegram acceptance is authenticated and bound to the displayed proposal version;
  ambiguous, replayed, stale, or wrong-user responses do not execute new changes.
- **YC-05:** Restarting or changing chat surfaces restores saved proposals, sources, and decisions
  without reconstructing them from the full chat or reusing expired authorization.
- **YC-06:** Concurrent UI edits and delayed responses preserve session isolation and detect
  version conflicts; omitted and completed nodes retain their protected history.
- **YC-07:** A worker result is linked and reviewed; run completion alone does not mark the user's
  project complete. Failed dispatch or uncertain retries remain visible and avoid duplicate work.
- **YC-08:** Portfolio recommendations identify cross-project effects and respect the approved
  scope. Missing evidence remains explicit in both the proposal and progress report.

## 21. Open design work

- Confirm the unfinished requirement about where all management information should live and
  which UI should present it; the proposed default is the Graph Project System.
- Map actual Canvas, List, Timeline, detail forms, database fields, and semantic tools to this role.
- Define capability discovery and refresh through a restricted interface usable by Yonc.
- Define the persisted assignment model, partial acceptance, and dispatch handoff contract.
- Design trusted Telegram authorization in coordination with the existing UI approval contract.
- Choose proactive planning triggers, budgets, notification rules, and portfolio review cadence.
- Reconcile existing implementation and deployment evidence against these requirements before
  deciding which work is complete. Do not infer implementation from historical status labels.

## 22. Sources and precedence

- User clarification in this task on **2026-09-26**: project manager role, proactive decomposition,
  capability awareness, proposed assignments, human finalization, durable sources, and Telegram
  discussion. This document captures the completed statements; it does not complete the user's
  unfinished sentence as an accepted decision.
- [Yonc documentation index](../../../yonc_agent/docs/yonc/README.md): original design provenance
  and document precedence.
- [Yonc Agent design, 2026-09-20](../../../yonc_agent/docs/yonc/05-yonc-agent-design.zh-CN.md): whole
  graph management, independent conversations, decomposition, review, and history protection.
- [Hermes integration contract, 2026-09-21](../../../yonc_agent/docs/yonc/08-hermes-integration-contract.zh-CN.md):
  backend authority, current authorization contract, and run boundaries.
- [Core architecture](../../../yonc_agent/docs/yonc/01-core-architecture.md) and
  [project writes and history](../../../yonc_agent/docs/yonc/02-project-write-and-history.md):
  project truth, provenance, and proposed durable write semantics.
- [Graph Project System specification](../../../yonc_agent/Yonc_Graph_Project_System_Spec_v0.1.md):
  graph model, UI views, forms, decomposition, and project completion semantics.
- [UuMA agent archive](README.md), [Brainstormer](brainstormer.md),
  [Scholar](scholar.md), [Wisdom-Oldman](wisdom-oldman.md), and [Forge Lab Bot](forge-lab-bot.md):
  colleague roles and ownership.
- [Yonc profile](../../profiles/yonc/SOUL.md) and
  [project management procedure](../../profiles/yonc/skills/yonc-project-management/SKILL.md):
  existing local operating instructions.

The latest explicit user requirements govern product intent where they extend older assumptions.
Existing execution and authorization contracts continue to govern deployed behavior until revised
and verified. Earlier design descriptions of Yonc as a dispatcher are interpreted through the
later division of project planning and Orchestrator-controlled execution.
