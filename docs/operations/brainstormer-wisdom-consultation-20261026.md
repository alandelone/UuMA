# Brainstormer to Wisdom consultation publication — 2026-10-26

## Authorization and scope

The user explicitly approved deploying and verifying the prepared direct consultation feature.
This publishes the scoped Brainstormer to Wisdom question/reply contract, its two worker tools,
and the two role instructions. It does not implement a separate Brainstormer critic.

Release: `f68069659e53bca5877dba472d6ac711e2a4728f23ffcd2313df32f75a278753`.
Production node: `alandelone-server-001`.

## Publication and preservation

The release uses separate control, A2A, worker and shared-model overlays built from the actual
production source baselines. It retains the provider pool as the gateway's first import prefix,
the existing provider preflight, Wisdom daily quota configuration and all old worker tools.
The shared overlay contains only the compatible source enum reader and package namespace.

All five specialist intakes were paused under this publication plan. The gateway confirmed
draining with zero executing agents. Eight individually inspected old unclosed chat registrations
had no executing runtime, assigned tools or capabilities; their records were preserved unchanged.
They were not reported completed or cancelled.

Consistent control and Wisdom database backups and original profile/configuration backups are
private in the server operation directory. Hashes of protected records were equal before and
after the switch. No database schema migration or canonical knowledge approval was performed.

The control, A2A and shared Hermes services restarted with these process IDs:

| Service | Previous PID | Published PID |
| --- | ---: | ---: |
| `uuma-control.service` | 99734 | 220878 |
| `uuma-a2a-pilot.service` | 98541 | 220882 |
| `uuma-hermes-pilot.service` | 162514 | 220949 |

The shared Hermes service also owns the native API; no separate native API service was restarted.
All five intakes were reopened. Gateway state returned to running, all five Telegram bindings
were connected, and the native API and control health checks passed.

## Verification and recovery evidence

- 41 isolated server checks passed without skips: 22 existing control contracts, 13 consultation
  contracts and six real HTTP/A2A SDK boundary checks. No model calls in that isolated suite.
- Actual configured process environments resolve the new control/A2A/shared modules to this release.
- Actual Brainstormer worker MCP initialized and discovered both consultation tools.
- Brainstormer was denied global A2A receipts (403).
- The real Brainstormer MCP dispatched a bounded question with new research disabled to the
  Wisdom runtime; receipt `9728995c-8751-41f5-8738-158c3178de0c` and runtime
  `run_cc43c12ac4f3437faaa9fd273080aeea` prove acceptance, separately from a final answer.

An earlier isolated candidate failed because current Starlette lacks the older application
middleware decorator. The ASGI boundary implementation was corrected; assertions were preserved,
and the final immutable candidate passed all 41 checks. Its failed predecessor remains retained.

The first activation helper shadowed the Python copy module with a path variable. It stopped
after backups/profile copies and before service restarts. Recovery verified unchanged old PIDs,
all backups and protected records, then continued that exact switch. The frozen release was not
modified, and the operation was not replayed from the beginning.

## Live answer acceptance

The real Brainstormer MCP read structured PARTIAL replies from Wisdom through the scoped status
tool. These distinguish general existing evidence from missing local parameters. They remain
pending review; no scientific or canonical knowledge acceptance is claimed.

Two model responses falsely claimed question retention: the first used invalid record fields,
and the second claimed IDs that actually failed `knowledge_get`. Both immutable results and
failed tool receipts remain preserved. The role-only correction was not accepted as a persistence
fix. The resulting execution contract now saves and reads back unknowns in Wisdom's own worker
submission path using the existing semantic MCP. It preserves the original model response, uses
stable per-run record IDs, checks existing record contents and rejects stale submissions before
any new save. It starts no Orbit and approves no claim.

Retention component: `5ed701334adfc131ae8a45c5924351b46d601a40567f12f5805b0a5986e22d63`.
Only Wisdom's worker MCP binding was updated, with the original source/environment retained.
The component adds no shared service restart. Four focused checks passed in the actual server
interpreter. The actual MCP protocol check then saved and independently read a root question,
child question and gap; Brainstormer's scoped receipt returned the true IDs. A repeated result
submission was rejected. This acceptance invoked no model and asserted no scientific answer.
It supplements the separately proven real A2A/model question-and-answer path.

The first actual synchronous MCP guard invocation exposed that FastMCP called it inside an
already-running asyncio loop. The failure was preserved; a tested dedicated-loop bridge fixed
that execution context without weakening record readback assertions. Previous immutable
retention candidates remain available for audit.

One additional model validation stopped producing events. Only this task-owned runtime was
stopped after the bounded observation interval; its observed native failure was reconciled as
a failed validation run. It was not counted as successful research, cancelled user work or used
to justify replaying an uncertain request. The manual verification parent submitted its final
result and remains REVIEW under the ordinary independent-review boundary.

The user's later consolidation request restored one current Brainstormer topic from Telegram
history through semantic proposal/review, preserving original conversation data. Its detailed
business content and source snapshots remain private in the domain and operation receipts.
The active domain has one canonical topic, zero inferred groups, eight questions, five unconfirmed
assumptions and two checkpoints. The later checkpoint links the verified retention records.

The local Observatory readback still returned its placeholder Brainstormer card. This operation
does not claim to have published a remote-owner Observatory adapter or synchronized that view.

## Receipts and rollback

Server release and private operation directories are respectively:

- `~/.local/share/uuma/components/brainstormer-wisdom-consultation/<release>`
- `~/.local/share/uuma/operations/brainstormer-wisdom-consultation/<release>`

The latter holds the source preview, staging report, consistent database backups, original file
backups, configuration changes, activation, runtime verification and intake recovery receipts.
Local private copies/helpers are in `.uuma-local/brainstormer-wisdom-consultation-20261026`.

Rollback must compare each changed path with its recorded new digest, drain only when execution
is idle and restore only the backed-up configuration/profile paths and task-owned service drop-ins.
Never overwrite a database with the backup over later writes. Since consultation events now exist,
retain a compatible reader for `source=consultation` even if the dispatch feature is disabled.
