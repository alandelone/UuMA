# Brainstormer server topics in Observatory

## Scope

The workstation Observatory reads Brainstormer's authoritative navigation and graph
responses on `alandelone-server-001`. The restored Malaysia green-onion plan is the
initial connected topic. Its observed revision is 4, with one canonical topic,
eight questions, five unconfirmed assumptions, eleven user-input evidence records,
two checkpoints, and no decisions.

This change affects the local Observatory adapter. It does not publish an Agent
release, restart the shared gateway, invoke a model, switch a Telegram topic, or
modify Brainstormer's project data or conversation history.

## Connection

`BrainstormerAdapter` selects remote ownership when
`<UUMA_DATA_DIR>/brainstormer.remote-owner.json` exists at startup. The default data
directory is `%LOCALAPPDATA%/UuMA`. An explicit
`UUMA_OBSERVATORY_BRAINSTORMER_OWNER` path can select the marker instead.
An explicitly configured missing marker produces an unavailable remote source.
When the default marker is absent, the adapter also checks the physical Codex
package cache at
`%USERPROFILE%/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/UuMA/brainstormer.remote-owner.json`.
Windows redirects writes made by the packaged Codex app to this directory; a
background service launched outside that package otherwise misses the marker.
The physical path was confirmed using the open file handle, rather than inferred
from the path's spelling.

The marker contains `agent: brainstormer`,
`owner_node: alandelone-server-001`, and the existing Telegram user's
`navigation_user_id` as a numeric string. It contains no credentials.

`RemoteBrainstormerReader` uses the existing `ubuntu-server` SSH alias; an explicit
`UUMA_OBSERVATORY_BRAINSTORMER_SSH_HOST` can override it. Authentication remains in
the user's SSH configuration. The server reads its own Brainstormer token locally
and calls the existing loopback navigation service on port 8773:

- `GET /health` checks the expected state-daemon service.
- `POST /api/v1/navigation`, with `action: list`, reads the user's navigation scope.
- `GET /api/v1/graph/<project_id>` reads each listed project's semantic graph.

The navigation `list` action is read-only. No domain service is constructed and no
database is copied, initialized, joined, migrated, or resumed. Tokens are not
returned to the workstation.

## Presentation and failures

The remote graph is projected into the existing decision-DAG and topic detail
payloads. Questions, assumptions, evidence, checkpoints, current-question identity,
hierarchy, revisions, source references, and record status are preserved. Project
and topic metadata are not counted as checkpoints. An active saved discussion
means `ACTIVE`; it does not establish that a worker is executing.

A shared in-memory response cache lasts ten seconds. SSH connection timeout is
five seconds, the overall SSH request timeout is eighteen seconds, and each owner
API read has a four-second timeout. Refreshes remain subject to the UI polling
interval and other Observatory sources' response time.

If a refresh fails, the current response becomes unavailable and the adapter shows
`服务器议题暂不可用` with warning health. Remote ownership never falls back to old
workstation projects or Hermes sessions. A successful empty response instead shows
`服务器暂无议题`.

## Runtime and rollback

The existing hidden `scripts/run-observatory-service.ps1` supervisor runs the
editable repository source on port 8790. Refresh only its verified Observatory
child process after installing source and marker configuration. Leave specialist
services and the shared gateway running.

Private preparation, source hashes, before-source backup, API readback, and
activation receipt are kept under
`.uuma-local/brainstormer-observatory-20261028/`. They include private user content
and must not be published as public documentation.

For an intentional rollback, first verify the current source against the receipt
and preserve later edits. Stop the local Observatory through its existing
supervisor stop procedure before restoring only this integration from the
before-source backup. The old adapter does not honor remote ownership, so keep
Observatory stopped until an owner-aware replacement is available; retaining a
marker alone cannot make the old adapter safe to serve. Remove the newly added
remote module only if no later changes depend on it. Brainstormer's server data
requires no rollback because this integration performs semantic reads only.

No automated tests were added or run for this task. Recorded checks consist of
source lint, direct readback of the authoritative server API, and inspection of
the running local API and UI.

## Applied readback

The local API returned ten items: one project DAG, one canonical topic, and eight
questions. It reported owner `alandelone-server-001`, revision 4, eight questions,
five assumptions, and two checkpoints. The stale standby item was absent.
The existing supervisor remained PID 106680; the refreshed Observatory process
was PID 145736 at readback. These are historical observations, not enduring
process identifiers to use for later termination.

Browser inspection confirmed the Brainstormer card, its expanded topic contents,
and the topic Inspector all render the server records. The Inspector's source
points to the server-owned project and topic. The screenshot is
`.uuma-local/brainstormer-observatory-20261028/connected-topic.png`.
The full fleet's initial page load was slow during inspection; this task did not
change its other adapters or the global refresh scheduler.
