# ADR 0002: Independent MCP Worker Instance for Native Host

**Status**: Original process model accepted; authorization and delivery constraints revised for review, 2026-09-27.
**Scope**: Architecture decision, not implemented governance.

## Context and decision

Retain a Native Messaging host that spawns its own stdio MCP worker. Use the same versioned
environment/path resolution as other UuMA clients, with UUMA_AGENT_ID=forge-lab-bot and a new
restricted native-client mode. Use the pinned MCP SDK, including initialization completion,
request correlation, error handling and child shutdown.

The original alternatives were an HTTP MCP transport, direct Python calls, or file-only manual
handoff. The independent worker retains existing transport compatibility and supports real-time
integration; files remain durable evidence, not the only command channel.

## Governance correction

MCP transport and an agent identity do not prove user approval. Existing inventory_receive checks
the Forge identity but does not implement the proposed receipt confirmation/idempotency contract.
Hermes hooks do not run around calls from this host.

The native mode must enforce a narrow tool allowlist at dispatch, including tasks, leases, batch
submission and recovery status. It cannot call inventory_receive or generic arbitrary tool/SQL/path
operations. All entry points use shared service-side validation. Approval references for inventory
mutations are issued by a trusted user-confirmation path and verified against an exact preview.
They cannot be supplied as an unverified approved=true field.

## Command and storage contract

The agent-facing worker queues commands in uuma.db. While connected, the native worker claims them
through semantic tools and passes them via the host to Chrome. Leases/fencing tokens prevent stale
workers from advancing tasks. A disconnected browser leaves WAITING_FOR_BROWSER, not false success.

Control state remains in uuma.db; lab evidence and inventory remain in lab.db. Immutable raw batches
and review artifacts use the local commerce archive, including non-lab lines. No cross-database JOIN
or Hermes state.db reuse is introduced. Host direct SQLite dedup access is superseded by semantic
status/reconciliation tools.

Raw batch persistence precedes lab transaction commit; task checkpoint advancement and ACK follow.
These are separate failure boundaries, recovered by stable batch IDs and receipts. Receipt approval
reservation and lab inventory commit likewise recover through one stable confirmation ID, not a
claimed cross-database atomic transaction.

## Consequences and validation

- One more process exists while the extension connection is enabled; closing the connection cleans
  up its child and preserves persisted task state.
- A shared database does not itself supply authorization, idempotency or conflict resolution.
- Configure and verify SQLite journal mode, busy timeout and short transactions explicitly;
  existing WAL mode is not assumed.
- Verify simultaneous clients, stale leases, duplicate batches, process termination and lost ACKs.
- Inventory receipt migration must close legacy bypass paths before new receiving is enabled.
- Keep current transport behavior for existing clients; new contracts require targeted regression.

See the [implementation plan](../plans/labbot_implementation_plan.md) for phases and acceptance.
