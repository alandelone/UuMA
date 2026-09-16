# UuMA Agent Design Archive

Status: working design archive  
Last consolidated: 2026-08-26

This directory converts four long ChatGPT design conversations into durable project documents. The files are consolidated design records, not verbatim transcripts: later decisions override earlier proposals, accepted boundaries are separated from open questions, and each document keeps a link to its source conversation.

## Current system map

```text
User / Live Interface
        |
        v
Hermes original profile (Orchestrator / Commander)
        |
        +-- Brainstormer
        +-- Scholar
        +-- Wisdom-Oldman
        +-- 锻造Lab_Bot (Physical Lab & Engineering Memory)
        |    +-- forge_lab_skillset
        |    +-- Procurement (sub-capability / sourcing)
        |    +-- Notion (external raw worklog SoT)
        |    +-- eschematic-bridge (controlled integration)
        |            ^
        |            | (read-only / proposals)
        +-- eSchematic (Design Intent Authority & EDA)
        |    +-- eSchematic_skillset
        |
        +-- CopyCat MCP
             computer-observation and replay capabilities
```

The original Hermes agent is the orchestrator. It routes work, monitors specialized agents, coordinates results, and owns computer-control policy. 

The two primary engineering domain authorities are:
1. **`eSchematic`**: Owns component catalog specifications, schematic design, design BOMs, and immutable design revisions.
2. **`锻造Lab_Bot`**: Owns physical inventory, purchase lots, build execution, as-built configuration, commissioning, failure logs, and derived candidate engineering lessons.

Integration between physical lab operations and electronic design occurs through the controlled **`eschematic-bridge`**, guaranteeing that `forge-lab-bot` can consume immutable design manifests and propose design feedback without directly mutating eSchematic's authoritative design store.

The Live Interface at `C:\Users\Alandelone\CodeSpace_Local\livechat_agent` is an optional client surface. It may connect by text or voice to the orchestrator or directly to an agent, but it is not the architectural center of UuMA.

## Documents

| Document | System role | Canonical source conversation |
|---|---|---|
| [Wisdom-Oldman](./wisdom-oldman.md) | Long-term knowledge discovery, formation, maintenance, and retrieval | [shared design conversation](https://chatgpt.com/share/6a9015ad-2ee8-83ec-a155-3d9844ffecb6) |
| [Scholar](./scholar.md) | User-directed scientific research lifecycle through RSTV4 | `chatgpt-conversation://6a8da0b9-3674-83ec-af3a-90b65e17ffcc` |
| [锻造Lab_Bot](./forge-lab-bot.md) | Hardware lab operations, inventory, build traceability, procurement, and engineering lessons | `chatgpt-conversation://6a8d3f19-c4c4-83ec-8342-bbd5d823e0a3` |
| [Brainstormer](./brainstormer.md) | Persistent reasoning partner that explores, challenges, converges, and turns discussion into build-ready artifacts | `chatgpt-conversation://6a87c452-df88-83ec-ad5d-661a9d73e337` |
| [Multi-Agent Logic Graphs](../logic-graphs.md) | Multi-Agent orchestration, decision trees, and profile workflows | Architecture & Implementation baseline |

## Naming decisions

- `Wisdom-Oldman` is the canonical name. Earlier voice-transcription variants are not system names.
- `锻造Lab_Bot` is the canonical system and display name. `forge-lab-bot.md` is only its ASCII file slug.
- `Scholar` is the customized agent name. Its source discussion sometimes used `Researcher` as the role description.
- `Brainstormer` remains the canonical name even though its function is broader than idea generation.

## Cross-system ownership

The four profiles must not become four copies of the same general assistant.

| Concern | Owner |
|---|---|
| Routing, monitoring, delegation, final coordination | Hermes Orchestrator |
| Discussion state, assumptions, decisions, design convergence | Brainstormer |
| Scientific questions, methods, experiments, claims, publication lifecycle | Scholar |
| Reusable world/domain knowledge, evidence map, knowledge gaps | Wisdom-Oldman |
| Component definitions, schematics, design BOMs, design revisions | eSchematic |
| Physical inventory, builds, as-built state, commissioning, lab lessons | 锻造Lab_Bot |
| Raw engineer worklogs and Lab Journal notes | Notion |
| Sourcing search, vendor quote comparison | Procurement (Lab_Bot capability) |
| Learned observation and replay actions | CopyCat MCP |

Other-agent output is input or evidence, not truth by default. Every receiving agent keeps its own judgment and references the source rather than silently copying the source system's entire state.

## Documentation rule

These documents record product and architecture decisions. Hermes profile implementation should later be split by nature:

```text
SOUL.md     stable identity and invariant behavior
Skills      reusable procedures and methods
MCP/tools   executable capabilities and integrations
AGENTS.md   project-specific operating instructions
Backend     domain truth and durable structured state
Runtime     current run/session progress
```

Conversation history remains provenance, but these documents are the working design baseline for the UuMA project.
