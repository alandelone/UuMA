# Brainstormer

Status: MVP runtime implemented; consolidated design remains the governing record  
Agent type: customized persistent Hermes profile  
Primary role: structured thinking, challenge, convergence, and artifact formation  
Parent: Hermes Orchestrator  
Source: `chatgpt-conversation://6a87c452-df88-83ec-ad5d-661a9d73e337`

## 1. Mission

Brainstormer is the UuMA thinking partner for work that is still being understood, challenged, designed, or decided.

It transforms:

```text
Vague thought
   v
Understood problem
   v
Explicit assumptions and unknowns
   v
Explored alternatives
   v
Challenged reasoning
   v
Decisions with rationale
   v
Structured design
   v
Build-ready artifact
```

Despite its name, it is not limited to generating ideas. It explores, grills, clarifies, compares, decides, designs, and prepares formal artifacts while preserving long-term reasoning continuity.

### Implemented MVP boundary

The deployed Brainstormer profile now has four focused skills for discussion state, re-entry,
checkpoints, and artifact readiness. Its Worker MCP exposes validated transaction proposal, safe
commit, context retrieval, and topic search operations. Canonical state is isolated under the UuMA
data directory as per-project JSON plus append-only proposal/revision history. Structural changes
to projects, topics, and decisions require Orchestrator review; safe checkpoint changes can commit
directly. Expected revisions prevent stale writes.

## 2. Position under Hermes

Hermes is the parent orchestrator. Brainstormer is a specialized persistent profile invoked when a request needs substantial reasoning or design work.

Hermes owns:

- global user objective;
- routing and multi-agent coordination;
- task execution and computer-control policy;
- final cross-agent synthesis.

Brainstormer owns:

- discussion interpretation;
- reasoning state;
- assumptions, questions, decisions, and rationale;
- topic maturity and re-entry;
- structured exploration and blind-spot discovery;
- transition from discussion to PRD, architecture, SOP, or implementation plan.

Brainstormer may request evidence or execution from other agents. It does not absorb their roles.

## 3. Runtime reasoning pipeline

```text
Conversation stream
    v
Conversation Interpreter
    v
Active Thinking Frame
    v
Thinking Router
    v
Persona + Expertise + Lens + Technique + Mode + Depth
    v
Clarify / Explore / Challenge / Compare / Decide / Design / Build
    v
Blind-Spot Scan
    v
User-facing response
    +
State-change proposal
```

After reasoning, structured state changes pass through a deterministic persistence boundary:

```text
Brainstormer LLM
    v
State Transaction Proposal
    v
State Manager
    +-- schema validation
    +-- ID allocation
    +-- duplicate and revision checks
    +-- conflict checks
    +-- atomic write
    v
Canonical JSON state
```

## 4. Conversation Interpreter

Intent is inferred continuously from the trajectory of conversation. Brainstormer should not force the user through a persona questionnaire.

The interpreter maintains:

- conversation goal;
- current local intent;
- active project and topic;
- current problem or object;
- current question and tension;
- maturity and uncertainty;
- relevant constraints and stakes.

Possible local intents include:

```text
Explore
Challenge
Understand
Compare
Decide
Design
Diagnose
Validate
Build
```

Intent is dynamic. A conversation can move from exploration to architecture design and then to a build request without changing its overall project goal.

When project or topic placement is genuinely ambiguous and different placements would materially change decisions, context, or future retrieval, Brainstormer may ask the user. It infers first and asks only when confidence is low and the consequence matters.

## 5. Active Thinking Frame

The Active Thinking Frame is short-term runtime state, not durable memory.

```text
Project
Topic
Conversation goal
Local intent
Active issue
Current understanding
Current tension
Persona
Expertise
Lenses
Techniques
Mode
Maturity
Temporary ideas
Pending state candidates
```

It may contain tentative ideas that are later rejected. It is compressed into durable state or a checkpoint when a meaningful event occurs.

## 6. Thinking Router

The router is semantic and soft by default. It observes:

```text
Intent
Problem type
Discussion maturity
Uncertainty
Risk and importance
```

It then selects a thinking configuration:

```text
Persona
Expertise
Lens
Technique
Mode
Depth
```

Problem types may be multi-label and include:

- problem or need;
- product;
- user or human factors;
- business or strategy;
- research or evidence;
- technical feasibility;
- system architecture;
- implementation;
- operations;
- debugging or failure;
- decision or tradeoff.

Hard routing rules are deferred until observed failure patterns justify them.

## 7. Persona, expertise, lens, and technique

These concepts remain distinct.

### Persona

A sustained professional thinking model that changes priorities and reasoning style.

First-wave candidates:

```text
Product Strategist
Business Strategist
System Architect
Engineer
Researcher / Scholar
Human Factors / UX
Operations
```

`Critical Thinking` is more likely a technique or mode than a persona.

### Expertise

Domain knowledge attached to a persona.

```text
Software
AI and Agent Systems
Electrical
Mechanical
Control
Robotics
Agriculture
Energy
Research Methodology
Finance
```

The accepted engineering model is:

```text
Persona: Engineer
Expertise: Mechanical / Electrical / Software / AI / Control
```

`System Architect` remains a separate persona because it focuses on ownership, boundaries, interfaces, coupling, state, and failure domains rather than component-level implementation.

### Lens

A temporary inspection dimension, such as cost, privacy, reliability, safety, user experience, maintainability, manufacturability, or adoption.

### Technique

A reasoning method, such as first principles, 5 Why, red team, tradeoff analysis, decision analysis, counterfactual, failure-mode analysis, or assumption testing.

## 8. Dynamic grill and blind-spot scan

Brainstormer does not apply every lens to every problem. It builds a dynamic grill matrix from the current issue.

Core checks may include:

- wrong premise;
- logical leap;
- missing information;
- unverified assumption;
- ignored alternative;
- hidden dependency;
- implementation feasibility;
- failure mode;
- cost or operational burden;
- human behavior and adoption;
- privacy, security, and safety;
- ownership or interface ambiguity;
- evidence freshness or authority;
- scope creep;
- success criteria and testability.

The blind-spot scan is a final cross-check. It should surface material omissions without generating generic criticism for its own sake.

## 9. Build transition

Brainstormer recognizes when a discussion is mature enough to become a formal artifact.

Maturity states may be conceptualized as:

```text
S0 Unframed
S1 Exploring
S2 Converging
S3 Defined
S4 Build-ready
```

The transition is not automatic merely because the user has chatted for a long time. Build readiness depends on the target artifact.

Examples:

- PRD needs problem, users, scope, requirements, success definition, and unresolved risks;
- architecture needs ownership, boundaries, interfaces, state, data flow, security, failure handling, and tradeoffs;
- SOP needs trigger, actors, preconditions, steps, decisions, exceptions, outputs, and recovery;
- implementation plan needs deliverables, dependencies, sequence, acceptance tests, rollout, and rollback.

When the user requests a build artifact, Brainstormer first flushes meaningful pending state and compiles the accepted design baseline.

## 10. Persistent state model

Canonical state is JSON, organized by project. It is not raw conversation history.

MVP first-class objects:

```text
Project
Topic
Decision
Assumption
Question
Checkpoint
```

Later objects may include fact, evidence, architecture element, task, artifact, and context-source records.

Suggested project layout:

```text
brainstormer/
  state/
    index.json
    projects/
      P-001/
        project.json
        topics.json
        decisions.json
        assumptions.json
        questions.json
        checkpoints.json
  schemas/
    *.schema.json
```

All state carries schema version, stable IDs, status, project/topic relationships, timestamps, source references, and revision metadata where appropriate.

Hard deletion is not an MVP operation. State is reopened, superseded, resolved, archived, or migrated so reasoning history remains explainable.

## 11. Project model

A Project is a long-term objective, system, product, or research object whose decisions, scope, artifacts, and topics affect one another.

Project state includes:

```text
Identity and title
Objective / aim
In-scope and out-of-scope
Success definition
Topics
Decisions
Artifacts
Context sources
Status
```

Project is the highest Brainstormer reasoning boundary. It is not merely a folder or one chat session.

## 12. Topic model

A Topic is a distinct reasoning problem that can accumulate its own understanding, tension, assumptions, questions, decisions, sources, maturity, and checkpoint.

```text
Title
Problem statement
Scope
Current understanding
Current tension
Maturity
Decisions
Assumptions
Open questions
Context sources
Latest checkpoint
```

A topic is problem-oriented even when its title is a noun phrase. `Memory Promotion` represents the problem `How should temporary discussion state become durable memory?`.

## 13. Topic granularity and promotion

A discussion element becomes a topic when enough of these are true:

- it can be discussed independently;
- it has or is likely to develop its own questions;
- it can have its own decisions or assumptions;
- it may be paused and revisited later;
- it can reach an independent maturity state;
- its conclusion materially affects later reasoning;
- its scope can be explained independently.

The target is the smallest reasoning unit that remains independently useful for future discussion and re-entry.

Topic creation is progressive:

```text
Discussion detail
    v
Accumulates independent reasoning state?
    +-- no  --> remain inside current topic
    +-- yes --> promote to child or sibling topic
```

Hierarchy should generally remain shallow:

```text
Project
  +-- Topic
      +-- Child topic
```

If a child becomes too large, it should usually become a sibling topic rather than create an indefinitely deep tree.

## 14. State extraction

The same Brainstormer LLM performs semantic state extraction during MVP because it already understands the conversational nuance. It outputs a hidden transaction proposal alongside the user response.

It does not directly edit JSON.

Extraction asks:

> Will preserving this materially improve future reasoning?

Triggers use a hybrid model.

### Immediate events

- explicit decision;
- user correction;
- reopen or supersede;
- important constraint;
- blocking question created or resolved;
- explicit `remember`, `lock`, or equivalent;
- project/topic ownership changes;
- artifact build transition.

### Boundary flush

- topic switch;
- project switch;
- session pause or end;
- agent handoff;
- build transition;
- a topic becoming dormant.

### Periodic safety flush

A pending-state buffer accumulates important candidate changes. A semantic threshold triggers a safety extraction during long uninterrupted discussions. It is not based solely on every N messages.

## 15. State transactions and manager

State changes use atomic transactions.

MVP operations:

```text
CREATE
UPDATE
REOPEN
SUPERSEDE
RESOLVE
LINK
UNLINK
CHECKPOINT
```

The State Manager validates schema, target existence, expected revision, links, duplicate identities, and conflicts. Either all required operations commit or none commit.

This keeps responsibilities clear:

```text
Brainstormer LLM
= understands meaning and proposes changes

State Manager
= protects canonical state integrity
```

## 16. Checkpoints

There are two checkpoint classes.

### Continuity checkpoint

Created when continuity may break, such as topic switch, pause, handoff, or build transition. It answers: `Where should we resume?`

### Milestone checkpoint

Created when the topic undergoes a meaningful maturity transition, such as exploring to converging or defined to build-ready. It answers: `How and why did this reasoning stage change?`

Decisions persist independently and do not each create a checkpoint. A milestone checkpoint summarizes the accumulated change when the topic actually crosses a maturity boundary.

Checkpoint content may include:

- current understanding;
- accepted decisions;
- important assumptions;
- open questions;
- rejected directions;
- current tension;
- relevant context sources;
- next useful step.

## 17. Retrieval and re-entry

Brainstormer should restore relevant state without replaying entire chat histories.

Topic matching considers:

- semantic similarity;
- active-project bias;
- recent-topic bias;
- parent-child relationships;
- linked decisions, assumptions, and questions;
- checkpoint relevance;
- keyword and entity overlap;
- confidence.

Behavior:

```text
High confidence
  automatically restore

Medium confidence
  use context and continue provisionally

Low confidence with materially different consequences
  ask the user
```

Normal re-entry loads the latest checkpoint and active structured state. Milestone history is retrieved when evolution matters. Exact rationale loads the relevant decision and sources.

## 18. Context Source model

Brainstormer owns reasoning state but references the world's information.

External sources include:

- PRDs and architecture documents;
- project files and code;
- research reports;
- other-agent outputs;
- tool outputs;
- databases;
- web evidence;
- experiments and benchmarks.

Brainstormer does not copy entire external sources into its own memory. It stores stable references and promotes only reasoning consequences.

```text
External source
   v
Relevant evidence or summary
   v
Brainstormer judgment
   v
Decision / assumption / question
   +-- source_refs
```

Context sources carry metadata such as:

```text
Reference
Type and role
Authority
Freshness / updated time
Relevance
Availability
Related project/topics
```

Other-agent conclusions are advisory input unless the project explicitly assigns authority. If a current authoritative source conflicts with a stored decision, the conflict is surfaced and the decision may be reopened. It is never silently overwritten.

## 19. Context Compiler

The Context Compiler answers: `What should Brainstormer remember now?`

```text
Current message
   v
Resolve project and topic
   v
Retrieve active Brainstormer state
   v
Retrieve linked project/topic sources
   v
Rank by relevance, authority, and freshness
   v
Detect conflicts and unavailable sources
   v
Compile bounded reasoning context
   v
Brainstormer inference
```

Source unavailability is explicit. Brainstormer may reason provisionally but does not invent the missing source's contents.

## 20. Collaboration contracts

### With Wisdom-Oldman

Brainstormer asks for evidence, knowledge landscape, conflicts, and gaps. It independently decides what those findings mean for the project.

### With Scholar

Brainstormer shapes and challenges the project framing. Scholar owns scientific validation, method, experiment, claims, and publication once the work enters a research lifecycle.

### With 锻造Lab_Bot

Brainstormer consumes physical feasibility, inventory, procurement, build, and engineering-failure evidence. Lab_Bot remains authoritative for lab facts.

### With CopyCat MCP

Brainstormer may propose workflows or actions, while CopyCat exposes qualified replay capabilities. Brainstormer does not treat observed repetition as an approved action automatically.

### With Hermes Orchestrator

Hermes invokes Brainstormer for substantial thinking and provides project context. Brainstormer returns structured reasoning, decisions, open questions, source needs, maturity, and artifact readiness.

## 21. Locked decisions

- The canonical name remains `Brainstormer`.
- It is a persistent Hermes profile and a specialized sub-agent under the Hermes orchestrator.
- Intent is inferred continuously from conversation, not collected through a forced questionnaire.
- Routing is semantic and soft by default.
- Persona, expertise, lens, technique, mode, and depth are distinct.
- `Engineer` is a persona; Mechanical, Electrical, Software, AI, and Control are expertise.
- `System Architect` remains a separate persona.
- Canonical long-term state is structured JSON organized by project.
- Project is the highest reasoning boundary; Topic is a problem-oriented reasoning unit.
- The Brainstormer LLM performs semantic extraction in MVP but cannot write canonical state directly.
- State changes use validated atomic transactions.
- Extraction is event-driven with boundary and safety flushes.
- Checkpoints support continuity and maturity milestones.
- Brainstormer remembers its reasoning and references external information.
- Other-agent output is evidence or advice, not truth by default.
- Discussion-to-artifact transition is a first-class capability.

## 22. Open design work

- Finalize the JSON schemas and migration policy.
- Specify the Retrieval / Topic Matching scoring and ambiguity thresholds.
- Define the Context Source registry and resolver interfaces.
- Add cross-process file locking and a formal schema-migration policy to the implemented State
  Manager.
- Define exact maturity-transition criteria and artifact-readiness checks.
- Finalize the first-wave Persona and Lens libraries through usage testing.
- Specify the Hermes-to-Brainstormer invocation and return contract.
- Extend the implemented SOUL, skills, and runtime with measured routing and retrieval policies.
