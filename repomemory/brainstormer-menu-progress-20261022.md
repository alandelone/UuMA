# Brainstormer menu input and runtime progress

## User request

Telegram slash menus cannot submit arguments separated by spaces. Keep commands in the
left Menu, without a persistent reply keyboard. Offer click-first commands that ask for
the required text. Show current backend work separately from saved discussion checkpoints.
Keep the previously cleared production discussion store blank until the user creates content.

## Implementation

`integrations/hermes/uuma_brainstormer_commands/__init__.py` adds `/newtopic`,
`/switchtopic`, `/newissue`, `/progress`, `/guide`, and `/cancel`. Bare `/checkpoint`
and `/issue` prompt for input. Forms expire after five minutes, are limited to the
authenticated owner private chat, and are canceled by another command. Responses keep
the existing signed mutation path. Command deliveries are serialized and duplicate
Telegram message IDs are suppressed in bounded process memory. Forms are not persisted
across gateway restarts. Existing commands with arguments remain supported.

`/progress` reads Brainstormer's authenticated worker runs and intake state, and current
gateway dialogue counts captured on the gateway event loop. Gateway dialogue counts cover
all specialists and are labeled accordingly. Task records are not proof of live execution;
heartbeat timestamps and stale/unknown explanations qualify them. Saved topic context is
displayed separately. Each click refreshes sources; this is not a background notification.

## Deployment status

Local rollout tooling and receipts are under ignored
`.uuma-local/brainstormer-menu-progress-20261022/`. Candidate preparation uses read-only
backend requests and sends no Telegram/model messages or production test data.

The first activation attempt for candidate
`b782b69354dbef81eddafad06502952c05f018efbf0dadfbbedc08342d1bb59d`
was correctly refused: five HONC and one Forge governed runs remained RUNNING.
Native gateway dialogue count was zero, which does not satisfy the full drain contract.
No plugin/runtime version or Telegram Menu was changed. Owned drain markers and all five
intake gates were restored by the existing failure path. Do not cancel or reclassify those
unrelated runs to force a deployment. A subsequent heartbeat wording improvement means the
final candidate hash must be regenerated before activation.

The user was asked whether to wait for those tasks or authorize restarting the shared
gateway while they still report RUNNING, and explicitly selected immediate restart.
An additional Forge run appeared during the discussion. The final activation snapshots
all existing affected run IDs after pausing intake under that authorization; new unexpected
runs still prevent proceeding. Native gateway work must drain to zero. Preserve governed
run records without cancellation or replay and preserve concurrent deployments.

## Publication procedure

Use the agent development/release runbook. Prepare the final candidate, inspect its exact
preview, drain the shared gateway and affected governed runs, activate only the Brainstormer
plugin, verify all five adapters, reopen owned intake gates, then update the owner's chat
Menu and verify its readback. Preserve gateway environment, profile config, navigation
daemon source, databases, and unrelated specialist files. Do not publish Menu commands
before their handlers are active. Static lint passed before the final heartbeat wording
change. Final static lint passed. Final prepared candidate is
`10aaeab5a80964275b792a4c07f20a84169a3afe573c9413490637b372bb0dd0`,
plugin SHA256 `19f96afbfea12e2393e9f2e8f17e900b1b615271ab0c93fe22788684ec4de66d`.
Its preparation confirmed zero production topics/groups and generated no reply keyboards.
The user subsequently explicitly authorized restarting the shared gateway while governed
runs still report RUNNING. The release records that authorization and snapshots the
existing run IDs after pausing intake, preserving those records without cancel/replay.
The final candidate was activated and verified at 2026-10-22T15:05:36Z. Gateway PID
122480 serves all five connected Telegram adapters; navigation daemon PID 112910 was
not restarted. All owned drain markers were removed and intake reopened. Gateway env
and Brainstormer profile config were byte-preserved. The domain readback remains zero
topics and zero groups, with no new production test records or test messages.

Owner chat Menu publication was read back successfully (default chat language scope),
with newtopic, switchtopic, newissue, progress, topics, brainstorm, agenda, issue,
checkpoint, guide, cancel followed by preserved existing commands. Menu receipt plan ID:
`d96f3b8065da5128a119d353843678222324163eb7822b9dc436aa36d4abbb0a`.
The new command names do not conflict with native Hermes commands. Local session journal
projection occasionally raised MemoryError after commands had completed; retries retained
all history and did not change lifecycle assertions. No automated test suite was requested
or run. No real user Telegram click sequence was submitted on the user's behalf.
