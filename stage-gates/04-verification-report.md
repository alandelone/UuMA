# Verification Report

## 2026-09-20 control-plane remediation implementation

- Closed all six findings from `docs/reviews/2026-09-18-agent-engineering-review.md` without
  changing the `uuma.db` / `wisdom.db` / Hermes `state.db` ownership boundaries.
- SQLite `BEGIN IMMEDIATE` now encloses state preconditions, event append, and projection updates.
  Graph compare-and-swap, scoped task idempotency, active-Run epochs, and terminal transitions no
  longer rely on checks performed through separate connections or process-local locks.
- Worker graph flags and assignment booleans are no longer approval authorities. Graph writes and
  committing tasks require durable approval events, and heartbeats cannot write blocked, review,
  cancellation, or terminal status.
- Worker completion now produces a digest-bound REVIEW result. A different verifier must bind its
  evidence to the frozen acceptance digest, current result digest, artifacts, and identity before
  the current Run and Task can become COMPLETED. Revised results invalidate earlier evidence.
- The additive migration backfills request identities and Run epochs, preserves event history,
  rebuilds all projections including verification records, and fails closed on duplicate
  idempotency keys or ambiguous active Runs instead of deleting or overwriting records.
- Control API and MCP contracts now expose explicit Run registration/takeover, verification context,
  and result verification. Existing Hermes guard, diagnostics, and configuration contract tests
  passed; no deployment or live Hermes mutation was performed in this work.
- Focused remediation and integration regression: 53 passed with 5 subtests and one existing
  third-party Pydantic warning. Full UuMA regression: 149 passed with 5 subtests and the same
  warning. Full `src`/`tests` Ruff and scoped diff checks passed.

Status: six local remediation findings verified; live Hermes acceptance and user gate review remain
pending, and `mission_status.json` remains at verification / pending_review

## 2026-09-20 Question Orbit governed core

- Added additive `wisdom.db` projections for durable Question Orbits and explainably ordered
  frontier items. Question, gap, and research-run records gained backward-compatible Orbit fields.
- Added semantic Knowledge MCP operations for answer-first preflight, start/reuse, status, list,
  frontier, pause, resume, and stop. Active duplicate questions reuse one normalized Orbit.
- Wisdom Direct Run preflight now binds the UuMA task/run and conversation route outside the model.
  Wisdom cannot self-escalate beyond QUICK, and all lifecycle transitions remain hash-chain audited.
- Added and allowlisted the `wisdom-question-orbit` skill and refined the Wisdom SOUL contract.
- The production switch defaults off until the independent runner, discovery providers, usage
  ledger, safe ingestion, and notification outbox are implemented; this prevents orphaned queues.
- Focused Orbit/control/configuration tests: 30 passed. Full UuMA regression: 141 passed with one
  existing third-party Pydantic warning. Changed-source Ruff, PowerShell syntax, and diff checks
  passed.

Status: governed core verified; unattended Orbit execution and production enablement remain pending

## 2026-09-16 UuMA control-pipeline activation

- Added a fail-closed Hermes delegation guard requiring successful Control MCP task creation,
  routing, and assignment before specialist dispatch, including one ready Task Contract per batch
  child.
- Added throttled Control MCP health checks that exercise Hermes' supported stdio respawn path and
  prevent delegation while control health is unavailable.
- Made the Orchestrator SOUL block upgradeable, persisted Kanban enablement, bounded control-profile
  context at 48,000 tokens with earlier deterministic pruning, and canonicalized deployed executable
  paths.
- Focused control/configuration/plugin tests: 15 passed. Full UuMA regression: 110 passed with one
  existing third-party Pydantic warning. Changed Python lint and PowerShell syntax checks passed.
- Deployed to Hermes and restarted the gateway. The guard is enabled, `uuma-control` discovered all
  15 tools, and a live `system_health` call reported `status: ok` with a valid event chain.

Status: implementation repaired and deployed; first production specialist delegation will create
the initial post-remediation task/run records

## 2026-09-09 Wisdom-Oldman implementation audit repairs

- Fixed supersession snapshot completeness and reversal dependency integrity.
- Added leased recovery for interrupted projection jobs.
- Preserved canonical conditions, conflicts, gaps, and evidence stance in knowledge answers.
- Enforced research budgets and added complete chunk pagination.
- Original audit probes: 6 passed. Focused Wisdom regression: 19 passed.
- Full UuMA regression: 95 passed with one existing third-party Pydantic warning.
- Full source and test lint: passed.

Status: implementation repaired; user completion review remains pending

## 2026-09-08 Scholar hierarchy and paper tracking

- RSTV4 now supports reusable Fields and Topics, immutable Research Foundation versions,
  project-owned Research Tracks, track-scoped Blueprints, and independently tracked output
  manuscripts with immutable generated versions, status history, blockers, review flags, and
  append-only submission events.
- Existing catalog papers remain reference literature. Legacy projects migrate to one default
  Track with IDs and approval records preserved; legacy databases receive a one-time pre-v2 backup.
- Foundation updates are opt-in and do not import scientific approvals. Multi-Track calls require an
  explicit Track, and manuscript compilation, citation checks, and review use selected content only.
- RSTV4 regression: 11 passed. Full RSTV4 source/test lint: passed.
- UuMA regression: 78 passed with one third-party Pydantic warning.
- The RSTV4 MCP exported 46 tools including the new Track, Foundation, manuscript, progress, and
  explicit Blueprint snapshot operations. Scholar's deployed skill and SOUL were synchronized, and
  the Hermes gateway restarted cleanly.

Status: passed; user completion review remains pending

## 2026-09-08 executable session lifecycle

- Full regression: `python -m pytest -q` — 72 passed, one third-party warning.
- Six new tests cover missing/stale/modified handoff, file deletion, unfinished-session recovery,
  command failure/interruption, CLI exit code 2, version retention, and argument secrecy.
- This implementation's commands were journaled through `python -m uuma.session run --` after the
  initial bootstrap edits. Earlier operations are represented by manual notes, not retroactive events.
- A first focused run hit Git exit 128 in a temporary repository; a rerun passed, followed by six
  focused tests and the complete regression suite. Cause unconfirmed; snapshot errors fail closed
  and now report Git stderr. No safety assertions were relaxed.
- Scope: managed CLI commands and close checks; direct desktop shutdown and outside commands
  are not intercepted. Use one writer at a time. Logs are application-append-only, not tamper-proof.

Status: passed; completion review pending

## 2026-09-08 specialist capability and trust completion

- UuMA regression: 78 passed with one third-party Pydantic warning.
- RSTV4 regression: 6 passed.
- Focused lint for every changed UuMA Python file: passed.
- Full RSTV4 source/test lint: passed.
- Brainstormer now has four enabled discussion skills and durable, revision-checked JSON state.
- Scholar now uses single-use Hermes user-message approval grants, approved experiment plans,
  shell-free argument-vector execution, optional script digest pinning, and content-level evidence
  assessments. Citation resolution no longer claims faithfulness, and simulated review remains a
  human-review input.
- Forge Lab Bot exposes all eleven intended hardware-lab skills in the Hermes skill inventory.
- Every specialist has a managed SOUL with no pending conflict file. Forbidden specialist
  toolsets are absent; Scholar also has no general Gemini worker execution path.
- OpenSPG/KAG v0.8.0 is ready on project 1, its canonical projection lag is zero, and a live
  knowledge answer returned KAG trace/citation metadata.
- The deployment script and gateway restart completed successfully after final configuration.

Status: passed; user completion review pending

## Required evidence

| Check | Command or inspection | Result |
| --- | --- | --- |
| Root guide budget | line and word count for `AGENTS.md` | Pass: 49 lines, 383 words |
| State syntax | parse `mission_status.json` | Pass |
| Bootstrap syntax | Git Bash `bash -n init.sh` | Pass |
| Isolated initialization | Git Bash `./init.sh` | Pass: local databases and 5-record fixture |
| Static checks | `.venv/Scripts/python.exe -m ruff check src tests --statistics` | Baseline: 81 existing errors; no application Python changed |
| Regression suite | `.venv/Scripts/python.exe -m pytest` | Pass: 66 tests, 1 third-party warning |

## Baseline finding

Ruff reports 23 import-order, 17 UTC modernization, 9 unused-import, and 32 other existing
diagnostics. They predate this context-only change and are recorded in `repomemory/findings.md`.
`rules/linting-guidelines.md` prevents broad cleanup from contaminating this mission.

## Review boundary

The context system and regression suite satisfy the execution brief. Only Orchestrator/user review
may change `mission_status.json` from verification to complete.

## 2026-09-16 specialist direct-chat control remediation

- Brainstormer and Wisdom-Oldman Telegram routes had shared one session ID. The gateway was
  drained, both routes were reset to distinct IDs, and missing profile-local session rows were
  created. The old transcript and default Orchestrator route were preserved. Native reset could
  not link a cross-profile parent row because of the profile DB foreign key; the repair tool now
  creates an independent profile row while retaining `_reset_from` lineage metadata.
- Backup: `%LOCALAPPDATA%/hermes/uuma-route-backups/20260916T135220Z` (pre-repair state DB and
  legacy routing index); a second snapshot at `20260916T135314Z` precedes row materialization.
- Multiplexed profile identity now comes from Hermes' context-local home in guard, audit, and
  Phoenix observer plugins, instead of the gateway process environment. Direct specialist turns
  automatically register a safe Worker MCP Direct Run and prefetch their semantic domain state
  (Wisdom `knowledge_answer`, Brainstormer `brainstormer_search_topics`). Other tool use and a
  normal final answer require successful preflight. Control, computer, and file-mutation tools
  remain blocked even after a Direct Run is registered. A post-turn hook submits a terminal Worker
  result, including a failure outcome for recognized generic model errors.
- Both specialist profiles have the guard installed and enabled. Gateway restarted and reports
  running. SQLite checks confirmed three distinct Telegram route IDs and matching profile-local
  session rows.
- Full UuMA regression: 120 passed, one third-party Pydantic warning. Focused Ruff checks for
  `src`, `tests`, changed deployment/configuration/repair code, audit and guard: passed. The
  existing observability plugin has unrelated pre-existing Ruff diagnostics under a wider check.
- Local CLI live smoke: Wisdom Direct Run completed; `knowledge_answer` wrote a reasoning trace
  with `degraded=true` because the KAG Docker runtime is offline, so the canonical fallback was
  used without attempting runtime recovery. Brainstormer Direct Runs completed with successful
  topic-state search. One `thinking` model invocation returned a generic provider error; a retry
  succeeded, and a `standard` override also succeeded. No persistent model change was made.
- Live audit spool now attributes specialist events correctly. Phoenix API's newest 1,000 spans
  include 21 Brainstormer and 12 Wisdom-Oldman spans, where the earlier sample contained only
  Orchestrator attribution. Gateway is running after final deployment.
- A fresh Telegram inbound turn has not yet occurred after restart. That last transport-level
  acceptance check remains for the next real specialist message.

Status: implementation deployed; live specialist-turn acceptance pending

## 2026-09-16 remaining specialist profile extension

- The same per-turn Direct Run guard now covers all four specialist profiles: Brainstormer,
  Wisdom-Oldman, Scholar, and Forge Lab Bot. Scholar preflights against RSTV4 PaperPool's
  read-only catalog listing; Forge preflights against the lab inventory ledger's status.
  Each still uses its own profile MCP permissions. Direct specialist control/computer/file
  mutation remains blocked, and Forge's ordering, inventory mutation, physical build/status,
  and candidate-approval tool calls are additionally blocked.
- Deployment installed and enabled `uuma_control_guard` in all four profile homes. Installed
  copies match repository source; the Hermes gateway is running after restart.
- Local CLI smoke tests created completed Worker runs for Scholar and Forge. Audit spool events
  carried the correct profile names; the Phoenix live API's newest 1,000 spans included Scholar
  and Forge spans as well as Brainstormer and Wisdom spans.
- Full UuMA regression: 124 passed, one existing third-party Pydantic warning. Focused Ruff
  checks passed. No changes were made to the pending-review mission gate.
- New inbound Telegram turns for Scholar and Forge have not yet occurred after this deployment;
  those transport-level paths still need confirmation from real messages.

Status: four-profile local execution verified; Telegram inbound acceptance pending

## 2026-09-17 Wisdom-Oldman KAG on-demand lifecycle

- Wisdom direct-chat preflight now permits automatic KAG recovery and uses SIMPLE retrieval. Its
  Hermes hook callback cap is 450 seconds so a cold start is not abandoned by the former 30-second
  default. Normal Knowledge MCP calls still support AUTO/DEEP reasoning.
- The isolated bridge tracks in-flight projection, retrieval, and extraction work. After 30 minutes
  idle it exits and stops only the `uuma-wisdom-kag` compose project. A cross-process lock serializes
  start and stop. Docker Desktop, volumes, downloaded models, and `wisdom.db` are untouched.
- Before answering through KAG, pending canonical projection jobs are replayed; unresolved lag
  degrades explicitly. Wisdom's final response now visibly discloses a degraded fallback.
- Full UuMA regression: 133 passed, one existing third-party Pydantic warning. Source/test/guard
  Ruff checks, PowerShell syntax, and `git diff --check` passed. Hermes deployment and gateway
  restart succeeded; installed Wisdom guard matches the repository source.
- Local CLI cold-start acceptance: Direct Run `run_29bbbaa0be5a4ef2a310a05e1a23d269` completed;
  reasoning trace `trace_d2fae77987a545159d59d96c47a2d468` recorded `degraded=true` and SIMPLE
  mode. The response explicitly stated that graph/vector reasoning was not used.
- Live KAG success and timed idle-stop remain unverified: the bridge is unreachable, the
  `com.docker.service` Windows service and `docker-desktop` WSL instance are stopped, and Docker
  Desktop did not become ready after the bounded normal recovery wait. Starting the service under
  current and escalated execution failed with a service-access error. No Docker/WSL reset was done.

Status: on-demand lifecycle deployed and fallback verified; live KAG/idle-stop acceptance awaits
administrator restoration of Docker Desktop service and a fresh Wisdom-Oldman turn

## 2026-09-17 Docker-restored KAG acceptance

- Docker engine became reachable after user restoration, although Windows still reports
  `com.docker.service` as stopped. The isolated Neo4j container initially
  restarted because its `neo4j.conf` had 37 NUL bytes on one appended line. The original config was
  backed up to `.uuma-local/kag/neo4j.conf.corrupt-20260917.bak`; only those bytes were removed
  from the container config. No Docker volumes, models, or knowledge records were deleted.
- First live Wisdom-Oldman turn still degraded because the bridge lacked an LLM API credential.
  The Knowledge MCP now passes only a path to Wisdom's existing `.env`, and bridge cold-start reads
  the credential there without placing the key in Hermes YAML. A local end-to-end retry recorded
  `trace_7c178139d1e64f0484b801fd3d9690e9` with `degraded=false` and semantic KAG retrieval.
- For a controlled cold-start test, only `uuma-wisdom-kag` was stopped. The next Wisdom-Oldman
  direct turn restarted its containers and recorded `trace_ac4d5135550f4bbfb4d5ae4b61856086`
  with `degraded=false`, SIMPLE semantic retrieval, and projection lag 0. The Hermes gateway was
  restarted and is running for Telegram. No fresh inbound Telegram turn was sent in this test.
- Full regression: 135 passed, one existing third-party Pydantic warning. Ruff checks passed.
  The 30-minute idle-stop remains covered by the lifecycle contract test but has not yet been
  observed at its production duration. Docker Desktop's own stop/restart was not tested because it
  could disrupt other workloads.

Status: live on-demand KAG start and retrieval verified; timed production idle-stop and inbound
Telegram acceptance remain to be observed

## 2026-09-17 WSL bootstrap recovery

- Docker Desktop reported `running wsl-bootstrap: exit status 1`. Its host log showed the vpnkit
  bridge and Docker's main WSL distro exiting at 11:08:59, about 12 seconds after the four KAG
  containers were cold-started. The machine's `.wslconfig` limits WSL to 8 GB while the upstream
  OpenSPG/Neo4j JVM maxima exceeded 12 GB. No direct kernel OOM record was available, so memory
  pressure is the leading local risk indicated by configuration and timing, not a claimed proof.
- The KAG runtime now caps OpenSPG at 4 GB and Neo4j at a 2 GB heap plus 512 MB page cache. Stable
  observed usage was about 2.6 GB for all four containers. Docker remained responsive after repeated
  container restarts.
- Abrupt WSL exit had also reintroduced 37 NUL bytes into Neo4j's container-layer config. Bootstrap
  now seeds and mounts the full Neo4j config directory from the Windows runtime folder. A subsequent
  Neo4j restart remained healthy and the mounted config had zero NUL bytes.
- Compose restart policy is now `unless-stopped`, preserving the intended idle-stop state across a
  Docker Desktop restart. A later Wisdom turn can still start the named project on demand.
- Post-restart live acceptance recorded `trace_58ab8db00a2d4c3484696bf89b281788`
  with `degraded=false`, SIMPLE mode, and semantic KAG retrieval. Full regression: 137 passed;
  Ruff and PowerShell syntax checks passed.

Status: Docker/WSL and live KAG retrieval recovered; production-duration idle-stop and inbound
Telegram acceptance remain to be observed
