# Brainstormer Telegram topics

Implemented 2026-10-20 following the discussion: the requested distinction is switching
discussion topics, without imposing a business-model-specific workflow.

## User entry points

User preference (2026-10-22): commands belong in Telegram's left Menu only.
Do not add a persistent reply keyboard below the composer. Navigation replies send
`ReplyKeyboardRemove`; topic switching and pagination are described with text commands.

- `/topics`: formal Topics and inferred legacy topic groups, with per-topic counts and text commands for switching.
- `/topics <name>` or `切换到 <name>`: restore a formal Topic or enter a legacy group. Duplicate names require selection by ID.
- `/topics new <name>` or `新建议题：<name>`: an explicit user-authorized topic creation.
- `/brainstorm`: current-topic overview, question tree, recommended next question, blockers, latest progress, and command options.
- `/brainstorm help`: command guide.
- `/agenda`: question tree, recommendation, and blockers.
- `/issue <id>`, `/issue new <text>`, `/issue sub <id> <text>`: inspect a question, add a question, or add a subquestion.
- `/checkpoint <summary>`: explicitly save a progress checkpoint; turns are still auto-saved individually.
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

Observatory previously grouped records by `topic_id` and displayed each group as a Topic even
when no Topic object existed. Telegram now shows these separately as inferred legacy groups,
with their question/decision/assumption/checkpoint counts. Selecting one scopes navigation to
those records without migrating or promoting them to formal Topics.

Each real user/assistant turn is preserved as a source-stamped append-only checkpoint.
Transport references deduplicate retries. A response finishing after a switch retains the
original project/topic identity. Raw dialogue is progress, not an approved decision. Existing
safe transaction tools persist important questions/assumptions/evidence; decisions still
require explicit user or Orchestrator review. Creating a topic is reviewed only because the
authenticated user explicitly issued the create command; ordinary conversation cannot approve it.
Explicit `/issue` and `/checkpoint` writes require a signed owner command; they create safe
question/checkpoint records and do not turn discussion text into decisions.

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

Telegram commands are available through the left Menu; navigation replies remove the
persistent reply keyboard. Text commands use the same authenticated command parser;
there are no unauthenticated callback mutation endpoints. Exact names take
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

On 2026-10-22, the current state graph was found to contain six records in two `topic_id` groups
and zero formal Topic objects. The code changes documented above address this by showing both
record groups in Telegram and labeling them as inferred in Observatory. This source update has
now been deployed to the server navigation daemon and Telegram command plugin.

## Server publication: 2026-10-22

Release `3b0efabdc924140d7be61b5022d21d8aeb912b70392ddea5bedf2817292931cb`
copies the actual pinned server source and overlays only the five navigation/state
modules plus the Brainstormer command plugin and its unchanged manifest. The daemon
selects this immutable source through `30-topics-release.conf`; the shared gateway's
environment, pinned Hermes/provider imports, and Brainstormer profile configuration
remain byte-identical. No production records were promoted, imported, or recreated.

The installed plugin's authenticated calls to the live backend return both record
groups and their counts. Both group switches and scoped agendas were exercised on
an isolated production-data copy. Forty focused tests and targeted Ruff passed.
Unauthorized live navigation was rejected. All five server Telegram adapters
reconnected after the drained gateway restart, and their owned intake gates reopened.
No test chat messages or model calls were initiated by this publication.

The authenticated owner's private-chat Telegram menu was also published and read
back with `/topics`, `/brainstorm`, `/agenda`, `/issue`, and `/checkpoint` first.
Its chat-specific scope survives the shared gateway's default-menu refresh and
avoids the unrelated global `/topics` description. Previous menu values and the
exact menu preview are retained with the release receipts.

The exact preview, applied receipt, verification, domain snapshot, consistent SQLite
backup, and previous plugin/configuration are retained on the server under
`~/.local/share/uuma/brainstormer-command-releases/<release-id>/`.
Sanitized receipts are also retained in
`.uuma-local/brainstormer-topics-live-20261022/` on the workstation.
Rollback restores the saved plugin and navigation version metadata, removes only
this release's daemon drop-in, and reloads the services after draining; retain current
domain data and navigation records rather than restoring an old data snapshot.

The subsequent menu-only plugin release
`37b08d98207004d128b376e6f8ab814d7807f6864015994b13ffa5146d23bfa6`
removes the reply keyboard introduced by the earlier release. It changes only the
Brainstormer plugin and its version metadata, retains the existing Menu commands,
and leaves the navigation service running. The shared gateway is drained and
reloaded; prior plugin/version files and exact receipts are retained in the same
server release root. Local receipts are in
`.uuma-local/brainstormer-menu-only-20261022/`.
One user-requested UI confirmation carries `remove_keyboard: true` to clear the
keyboard already displayed in the owner's chat. The Telegram API acknowledged it;
the five Menu commands were read back unchanged. Fourteen focused tests, including
normal/error reply removal, and targeted Ruff passed.

## User-requested test data reset: 2026-10-22

The user identified the previous discussions as test data and requested a blank
start. Operation
`f3d56d0b333b3ac7445ffb3b409b0f358419b440d7f1c3749f5945b71dd44445`
archived the one test project, its six objects in two groups, and six proposal
records outside the active store. All archived file hashes were verified and the
navigation database was backed up consistently before clearing its stale
`default/default_topic` binding. The original history remains in the archive.

The live authenticated navigation response was verified as zero formal Topics,
zero inferred groups, no active binding and no context. Navigation schema and
authentication receipts were preserved. Only the navigation daemon restarted;
the shared gateway stayed running and all five specialist intake gates reopened.
No Menu, plugin, model/provider configuration or other Agent data was changed.

The verified archive and database backups remain on the server under
`~/.local/share/uuma/brainstormer-test-archives/<operation-id>/`.
Local sanitized receipts are in `.uuma-local/brainstormer-test-clear-20261022/`.
Reconcile any later user-created topics before restoring this archive.
