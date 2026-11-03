# UuMA A2A integration contract v1

Status: draft for review. Describes the current implementation and records gaps.
Protocol baseline: A2A 1.0. Document revision: 2026-10-23.
This application contract does not define a new public A2A standard or certify
complete A2A conformance. It does not approve a mission gate.

## 1. External standard and implementation versions

A2A is the public Agent2Agent communication standard. The pinned reference for
this document is the [official A2A 1.0.0 specification](https://a2a-protocol.org/v1.0.0/specification/).
The [official Python SDK](https://github.com/a2aproject/a2a-python) implements
protocol types and server routes. UuMA pins `a2a-sdk[http-server]==1.2.3` in the
`distributed` dependency extra; the inspected workstation installation is 1.2.3.
The SDK package version and protocol version are different version numbers.

The existing [distributed architecture discussion](five-agent-server-discussion-2026-10-21.zh-CN.md)
already specifies official A2A transport, UuMA authority and state, and MCP tools
as distinct responsibilities. This document makes their current boundary explicit.

## 2. Which parts are standard and which are application rules

| Concern | Owner | Current UuMA mapping |
| --- | --- | --- |
| Agent description and interface advertisement | A2A | SDK `AgentCard`, `AgentInterface`, `AgentSkill` |
| Message and task wire objects | A2A | SDK-generated `Message`, `Part`, `Task`, `TaskStatus` |
| Remote operations | A2A | JSON-RPC binding; `SendMessage`, task observation and cancellation via SDK routes |
| Protocol declaration | A2A | `A2A-Version: 1.0`; Agent Card interface declares `JSONRPC` / `1.0` |
| Business task, capability routing, assignment and execution attempt | UuMA | `TaskContract`, `RunRegistration`, registry binding and execution epoch |
| Who may dispatch and what may be executed | UuMA | Orchestrator identity plus current assigned Run checks |
| Result and independent acceptance | UuMA | `ResultContract`, `VerificationDecision`, control event history |
| Duplicate execution prevention and uncertain delivery | UuMA | Durable node journal keyed by Agent / Run / epoch |
| Access to worker, knowledge or model tools | MCP and adapters | Profile-specific tools and their existing permission boundaries |
| Analysis model selection | Worker/router configuration | `complex` alias through the router HTTP API |

Consequently, the sample's protocol path is:

```text
Orchestrator --MCP control tool--> UuMA dispatcher
UuMA dispatcher --A2A JSON-RPC--> Brainstormer node
Brainstormer --MCP--> analysis worker --router HTTP API--> complex
Brainstormer --Worker MCP/control API--> result store
Orchestrator --Control MCP--> returned result and verification state
```

Only the dispatcher-to-specialist boundary in this path is the A2A wire hop.
The worker model call does not establish an additional independent A2A agent.

## 3. Current executable dispatch rules

These requirements describe existing UuMA guards, not additional A2A requirements:

1. A dispatch MUST refer to an existing Task and explicitly registered Run.
   Assignment alone does not create a Run.
2. The caller MUST authenticate as Orchestrator for execution dispatch. Transport
   authentication does not grant a specialist control or knowledge-approval rights.
3. The destination MUST come from the trusted Agent registry binding. A task
   prompt cannot choose an arbitrary destination or replace its credentials.
4. Agent, assignee, current Run and execution epoch MUST match current control
   state. Only `PENDING` or `RUNNING` attempts pass the current authorization guard;
   a fresh runtime launch additionally requires a pending Orchestrator/kanban Run.
5. `metadata.uuma_run_id` and `metadata.execution_epoch` MUST accompany the
   assigned-task request. These are UuMA-defined metadata keys. A2A provides the
   metadata container; it does not define these keys or their authorization meaning.
6. The node MUST reserve a durable dispatch receipt before invoking Hermes.
   An existing receipt with a runtime reference is reused. An uncertain original
   start MUST be reconciled before a further launch; network retries do not prove
   that no work started.
7. Cancellation MUST remain a request until confirmed. It does not reverse
   completed external actions or knowledge changes.
8. Runtime completion, result submission and independent acceptance MUST remain
   distinguishable. A transport acknowledgement alone is not accepted work.

The workstation's explicit `UUMA_A2A_LOOPBACK_FORWARDS` configuration only maps
known loopback origins to existing SSH forwards while preserving the Agent path.
It does not change the registry identity or authorize another Agent.

## 4. Current wire example

Illustrative identifiers below are placeholders. The client constructs this
request through SDK protobuf types and ProtoJSON serialization:

```json
{
  "jsonrpc": "2.0",
  "id": "uuma:run_example:2",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "uuma:run_example:2",
      "role": "ROLE_USER",
      "parts": [{"text": "Execute the existing authorized UuMA contract"}]
    },
    "configuration": {"returnImmediately": true},
    "metadata": {
      "uuma_run_id": "run_example",
      "execution_epoch": 2
    }
  }
}
```

The actual business objective and input references are read from the authorized
control-plane Task. The incoming text is not permission to execute arbitrary work.
The response carries a standard A2A Task plus UuMA receipt metadata, including the
separate native runtime reference. The A2A Task ID, UuMA Task ID, UuMA Run ID and
Hermes Run ID MUST NOT be treated as interchangeable identifiers.

## 5. Business task and result records

`TaskContract` currently provides objective/title, requesting identity and source,
capabilities/tools, risk and execution class, input references, output schema,
acceptance checks/authority, optional external references and an idempotency key.
These fields belong to UuMA; sending them does not itself prove their contents.

`ResultContract` carries Task/Run/Agent IDs, outcome, summary, artifact references,
checks, rationale, assumptions, errors and partial state. A completed submission
must satisfy the Task's declared acceptance checks. Independent verification is
bound to the acceptance and result digests to identify the reviewed version.

The official A2A terminal execution state and UuMA acceptance are separate:

| Observed condition | Current A2A projection | UuMA acceptance meaning |
| --- | --- | --- |
| Execution still active | `WORKING` | Work not yet accepted |
| Native completed; submitted result awaits review | `COMPLETED`, metadata reason `result_pending_review` | `REVIEW` |
| Native completed; result accepted | `COMPLETED`, metadata reason `accepted` | `COMPLETED` |
| Unknown native outcome or reconciliation needed | `INPUT_REQUIRED` | Inspect the existing attempt |
| Superseded attempt or execution failure | `FAILED` | Preserve the failure/supersession history |
| Control confirms cancellation | `CANCELED` | Cancellation recorded; no external rollback implied |

Consumers MUST inspect the application acceptance metadata/control record before
interpreting protocol completion as approved business work.

## 6. Current evidence and conformance limits

The [real sample report](../operations/brainstormer-a2a-complex-20261023.md) records
Orchestrator MCP dispatch, actual A2A acceptance, specialist execution, real
`complex` inference, result submission, independent verification and read-back.
It is evidence for that bounded path. The prior 47 focused tests are recorded
there; this documentation pass did not run new tests or inference.

| Area | Current evidence or gap |
| --- | --- |
| SDK use, version declarations and standard object construction | Present in source; SDK version pinned and installed |
| Governed `SendMessage` dispatch and result return | Live synthetic sample completed |
| Agent discovery | SDK Agent Card routes are mounted per Agent; actual dispatch uses an administrator-bound registry, not arbitrary public discovery |
| Streaming | Advertised and SDK routes provided; the cited live sample did not certify streaming behavior |
| Push notifications | Explicitly advertised as unsupported |
| Listing and pagination | Current node rejects a nonempty page token; listing/filter/pagination semantics need an explicit compatibility audit |
| Formal application extension | UuMA metadata keys are implemented; no formal versioned AgentExtension declaration or extension negotiation is established by this document |
| Production transport requirements | Current loopback HTTP crosses hosts through SSH; strict deployment conformance to the specification's HTTPS/TLS requirements has not been established |
| Complete protocol/error/version compatibility | No full conformance or cross-vendor interoperability claim follows from the sample or SDK dependency |
| Autonomous Telegram first hop and Wisdom reuse | Not established by the sample |

## 7. Adoption and evolution rules

- Use official A2A types and method semantics at the communication boundary.
- Version UuMA task/metadata semantics separately. Do not silently reinterpret a
  protocol Task state as a different business approval state.
- Any formal extension proposal must specify its identifier, schema, negotiation,
  permissions and compatibility behavior before claiming third-party support.
- Future autonomous handoffs need their own bounded request/return contract and
  independent evidence. A prompt telling an Agent to delegate is not that contract.
- A claim of complete A2A compatibility requires a documented specification
  mapping and conformance/interoperability evidence beyond the existing sample.

## 8. Implementation references

- `src/uuma/a2a_client.py`: SDK request construction and loopback transport mapping.
- `src/uuma/a2a_node.py`: SDK routes/cards, dispatch guards, persistence and projection.
- `src/uuma/node_journal.py`: durable dispatch receipts.
- `src/uuma/models.py`: UuMA task, execution, result and verification records.
- `src/uuma/mcp_control.py`: Orchestrator-facing dispatch tool.
- `src/uuma/gemini_worker.py`: bounded analysis worker and durable router call.
- `pyproject.toml`: pinned distributed dependency extra.

Draft review does not change these runtime implementations or the pending mission gate.
