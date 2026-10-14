# Yonc colleague awareness acceptance

Date: 2026-10-01. Scope: give the existing Hermes Yonc profile sourced knowledge of its
colleagues and current registered capabilities so it can propose useful project work allocation.

## Delivered

- Always-present role guidance in Yonc SOUL; a `yonc-colleagues` skill with work, input,
  deliverable and authority guidance; twelve complete agent/source documents with a digest manifest.
- A Yonc-only read interface, `yonc_get_colleague_capabilities`, with current registration,
  capability tags, permissions, source digests, observation time and aggregate active Run counts.
  It preserves disabled registrations, exposes no task contents and creates no assignments.
- The guard retrieves and caches colleague context for a turn. Missing lookup data remains
  explicit rather than implying that no colleagues exist. Concrete proposals refresh the lookup.
- Targeted installation into `C:/Users/Alandelone/AppData/Local/hermes/profiles/yonc`.
  The model, project endpoint and Worker data directory were preserved. The installed profile
  has two reviewed Yonc skills and six directly exposed Worker tools. Ninety-one inherited
  unrelated skills were moved to recoverable quarantine.

The first backup is `.uuma-local/yonc-profile-backups/20261001-085849965287`; the final
documentation refresh backup is `.uuma-local/yonc-profile-backups/20261001-094148083073`.
The repeat deployment quarantined zero additional skills. The shared gateway restarted cleanly;
its subsequent status check reported a running process, PID 84496.

## Verification

| Check | Observed result |
| --- | --- |
| Focused role lookup, configuration, guard and skill contracts | 58 passed |
| Full UuMA regression on the current shared workspace | 364 passed, 5 subtests passed; two dependency deprecation warnings |
| Ruff on the nine changed Python implementation/test files | Passed |
| PowerShell deployment syntax | Passed |
| Scoped diff whitespace checks | Passed after correcting the two edited metadata lines |
| Installed SOUL, both skills and guard | Matched managed repository sources |
| Full source references and manifest | All 12 files matched their source bytes and SHA-256 |
| Live Worker capability lookup | Returned all six registered Agents with readable role sources |
| Live project status, before and after the conversation | Healthy, schema 1.2, graph version 18, 687 nodes |
| Real local Hermes conversation | Correct work allocation with bounded inputs, deliverables, acceptance and dependencies |

The local conversation is `20261001_170136_afdc25`, using Yonc's existing
`deepseek/deepseek-v4-flash` model. Its persisted record contains three model tool calls:
`skill_view(yonc-colleagues)`, `yonc_get_colleague_capabilities`, and `yonc_status`, each with
a successful result. Guard-generated Yonc Direct Run `run_c7cf6cee50984446b7b8b9a44c1afb1f`
submitted a result and reached `REVIEW`. The test created no project nodes, saved decomposition
or specialist dispatch; graph version and node count stayed unchanged. No Telegram message was sent.

Sanitized local evidence remains in `.uuma-local/yonc-role-acceptance.json`,
`.uuma-local/yonc-role-smoke-response.txt`, `.uuma-local/yonc-role-smoke-session.jsonl`,
and `.uuma-local/yonc-role-smoke-run.json`. The automatic guard context is covered by the
focused contracts; the real conversation also explicitly refreshed the capability lookup.

## Observed allocation

Given an ambiguous indoor-growing-device idea, Yonc proposed:

| Work | Suggested owner | Example deliverable |
| --- | --- | --- |
| Clarify needs and compare device approaches | Brainstormer | Explicit requirements, assumptions and two or three alternatives |
| Review scientific literature and evidence | Scholar | Source-linked evidence synthesis and unresolved research gaps |
| Investigate mechanisms and applicable conditions | Wisdom-Oldman | Traceable knowledge document with conditions and uncertainty |
| Inspect components, BOM and build risks | Forge Lab Bot | Evidence-linked BOM, inventory/purchase distinction and risk assessment |
| Approve scope and important decisions | User | Accepted scope and reviewed artifacts |
| Validate readiness, permission and dispatch | Orchestrator | Governed task and Run receipts |

It identified eSchematic as a domain system and CopyCat as an Orchestrator-controlled service,
rather than independent workers. It also reported `NOT_CHECKED` readiness and explained that
enabled registration and observed workload do not prove an Agent is online.

## Remaining management boundaries

Colleague awareness and sourced allocation proposals are implemented and deployed. Dedicated
persisted assignment proposals, accepted-assignment dispatch from Yonc and trusted Telegram
project-write authorization remain design work in `docs/agents/yonc.md`. This acceptance does
not certify every workflow described in colleague role documents or advance the mission gate.
The mission remains `verification / pending_review`.
