# Brainstormer Telegram topics

Implemented 2026-10-20 following the discussion: the requested distinction is switching
discussion topics, without imposing a business-model-specific workflow.

## User entry points

- `/topics`: current and earlier topics, eight per page, with Telegram reply-keyboard choices.
- `/topics <name>` or `切换到 <name>`: restore that topic. Duplicate names require selection by ID.
- `/topics new <name>` or `新建议题：<name>`: an explicit user-authorized topic creation.
- `/brainstorm`: confirmed decisions, unresolved questions, unverified assumptions, latest progress.
- `今天先到这里，下次继续`: display the progress already saved. Switching does not resolve a topic.

Normal Hermes `/model`, `/new` and `/stop` retain their meanings. `/new` resets chat history,
not the durable discussion topic. No model/provider configuration is changed.

## Actual state path

Telegram authenticated owner DM -> `uuma_brainstormer_commands` -> loopback state daemon
`POST /api/v1/navigation` -> existing BrainstormerStore and `uuma.db` bindings.

Canonical project/topic/question/decision/evidence/checkpoint objects remain under
`%LOCALAPPDATA%/UuMA/brainstormer/projects/<project_id>/state.json`; proposals and explicit
review receipts remain under `brainstormer/proposals/`. The active Telegram topic binding is
in `uuma.db.user_bindings`, keyed by `telegram:<owner id>`. Hermes `state.db` is untouched.

Each real user/assistant turn is preserved as a source-stamped append-only checkpoint.
Transport references deduplicate retries. A response finishing after a switch retains the
original project/topic identity. Raw dialogue is progress, not an approved decision. Existing
safe transaction tools persist important questions/assumptions/evidence; decisions still
require explicit user or Orchestrator review. Creating a topic is reviewed only because the
authenticated user explicitly issued the create command; ordinary conversation cannot approve it.

The plugin injects the active topic's structured state and recent checkpoints on each real
Telegram turn. Authorized-owner checks precede all reads/writes. Other profiles, group chats,
bot senders, scheduled/internal/delegated work do not enter this personal navigation path.
State failures are reported as failures, never as an empty topic list.

## Live relationship and limits

Live and Telegram use the same canonical project/topic objects and state daemon. Live's
existing session-specific binding remains separate: choose the same project/topic in Live
to resume its content. This change does not automatically identify a Live session as the
Telegram owner, or add a Live topic-picker UI. Local daemon APIs retain the existing trusted
loopback model; they are not a multi-user authorization boundary or a public network API.

Telegram reply-keyboard choices send ordinary, authenticated text back through the same
command parser; there are no unauthenticated callback mutation endpoints. Exact names take
precedence, then unique substring matches; ambiguous/missing names never create a topic.

## Deployment

`scripts/deploy-brainstormer-commands.py` backs up the raw profile config and prior plugin,
adds only this plugin/menu, and asserts model and MCP server settings are unchanged.
The daemon runs on port 8772 via `scripts/run-brainstormer-state.ps1`. Restart/reload the
gateway after installation and verify the actual Telegram command menu. Never use getUpdates
as a smoke test against the running gateway, or send unsolicited test messages.

## Discussion record and delivery evidence

The user clarified that the essential operation is: discuss topic A, put it aside, switch
directly to B, and later return to A with its decisions and pending questions intact.
They approved implementation on 2026-10-20 without further design questions. The resulting
entry points are topic navigation and current-topic overview; each topic keeps its own progress.

Validation: 25 focused tests passed, covering canonical state, DAG/planning, navigation,
HTTP API with an isolated database, authenticated delivery, source isolation, duplicate names,
configuration preservation, idempotency, restart recovery and late responses after a switch.
Lint passed for the new Python modules/scripts/tests. A regression exposed and corrected
`get_context` choosing checkpoints by JSON key order instead of save time.

Actual deployment: the `UuMA Brainstormer State` login task is running, loopback health is OK,
the installed commands reached the real backend, and Brainstormer Telegram is connected.
The menu was published and read back in default/private/group scopes, with `/topics` and
`/brainstorm` first. The installed plugin matches repository source; raw config and SOUL
backups are in `.uuma-local/brainstormer-navigation-20261020/deployment/`. Model and MCP
server settings were verified unchanged. Runtime evidence is in that task folder's
`runtime-verification.json`; no production test records or chat messages were created.
The production topic list was empty at verification: earlier free-form chat history has
not been imported into canonical topics. A real model conversation has not been exercised
as a deployment test. Start with `/topics new <name>`.
