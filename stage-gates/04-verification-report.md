# Verification Report

## 2026-09-25 Wisdom document link 404 repair

- Reproduced the reported topic's 404 with a valid unescaped URL while the topic existed in the
  canonical database. The scheduled reader used the logical LocalAppData directory, which resolves
  differently outside the packaged Codex process. Prior index-page acceptance did not detect this.
- Installer now resolves the existing wisdom.db redirection target before registering the task,
  so the reader opens the physical canonical data directory. Removed the token command-line
  workaround and temporary fingerprint-file write; the reader loads the token from that directory.
- Authenticated old links containing Markdown-escaped underscores are redirected to the canonical
  URL. Newly generated topic links percent-encode underscores to avoid Telegram escaping.
- Redeployed the document task. The exact reported topic returned HTTP 200 for both the normal
  and escaped URL; invalid-token regression remains 403. Seven topic tests and targeted Ruff pass.

## 2026-09-24 Wisdom-Oldman durable topic documents

- Added persistent topic, question, route, document, document-version, and topic-knowledge-link
  records to `wisdom.db`. Cross-chat matching reuses the durable topic; focus requests add a
  high-priority branch and short follow-ups use the routed question. Broad topics create five
  idempotent research branches covering scope, mechanisms, practical parameters, failure modes,
  and evidence freshness.
- Initial answers and completed Orbit cycles publish append-only Markdown versions containing
  synthesized text, conditions, conflicts, source URLs, evidence locations, research state, and
  change summaries. Telegram digests use the readable answer and stable topic/section URL.
- The local document view is text-first with a secondary read-only graph toggle. It runs on
  `127.0.0.1:8767`, requires the independent `wisdom-view-token`, and is installed as the
  per-user `UuMA Wisdom Document View` logon task. The existing `wisdom.db` was backed up to
  `wisdom-before-topic-docs-20260924-161410.db` before deployment.
- Orbit background cycles now require the owned Wisdom graph to pass bridge, project, schema, and
  storage-read checks before reasoning, discovery, projection, or document publication. A failed
  check blocks the cycle and preserves the reason. The graph lifecycle fix keeps Scholar/Wisdom
  bridges alive after MCP disconnect and was accepted by the companion deployment task.
- Full regression after the final changes: 259 tests passed, 5 subtests passed, with only the
  existing third-party FastAPI/httpx deprecation warnings. Focused topic/Orbit tests: 35 passed;
  Ruff, PowerShell parsing, read-token denial, and live loopback page checks passed.

Status: implementation and local deployment verified; fresh end-to-end Telegram inbound/digest
delivery still requires a new user-originated Telegram message and is intentionally not marked
observed here.

## 2026-09-24 Mandatory specialist graph readiness

- Scholar and Wisdom now require their own graph before domain tools, answer delivery and
  completed Worker results. Semantic Worker preflight checks bridge identity, registered
  namespace/project, required schema and a real graph-store read. Empty graphs are healthy
  but supply no evidence. Failed recovery blocks knowledge work; reporting remains available.
- Wisdom Knowledge MCP rejects degraded answers and does not start an Orbit from them.
  The independent topic-document task retains ownership of background Orbit integration.
- Existing Docker/bridge recovery is reused without creating graphs or changing schemas.
  Windows services now start hidden outside the MCP Job Object, with environment over stdin;
  closing a tool connection no longer kills the recovered bridges. Background Wisdom startup
  supplies usable logging streams. Empty Docker version output is not accepted as ready.
- Wisdom idle shutdown preserves shared Docker services while a Scholar bridge is present.
  Profile configuration and guard were backed up/deployed; gateway clean restart was verified.
- Full regression: 257 passed and five subtests, two third-party warnings. A final additional
  Docker-probe contract change passed all 13 lifecycle tests. Targeted Ruff passed before
  that final two-condition change. Six transient git-init fixture errors passed isolated and
  on the full rerun without assertion changes.
- Live MCP verified both graphs, Scholar bridge stop-to-recovery, and bridge survival after
  MCP close. A later stopped Docker Desktop was recovered by the new gate; both profiles
  again returned ready=true/recovered=true. No Telegram message or new knowledge was created.

Status: graph gate deployed and live recovery verified; mission remains verification/pending_review.

## 2026-09-24 Scholar reporting and FieldKG recovery

- Direct-chat preflight now exposes the registered run/task/agent identifiers together in
  Worker MCP reporting context, including failed domain lookup and repeated model calls.
  The Scholar deployed plugin received the scoped fix with a backup. Guard regression:
  20 passed; targeted Ruff, diff check and deployed syntax validation passed.
- Docker Linux engine became reachable; started the four existing OpenSPG containers and
  the existing ScholarFieldKG bridge using its saved project-2 configuration. No bootstrap,
  schema reapplication, volume reset, or historical-result reconstruction was performed.
- The real RSTV4 MCP health call returned ready=true for ScholarFieldKG, project 2, with
  zero pending/failed/applied projection entries. OpenSPG listed both Uuma and ScholarFieldKG.
  This is health/connectivity acceptance, not a new semantic retrieval or ingestion acceptance.
- Hermes drained cleanly and restarted; gateway status confirmed the new process running.
  Real Worker MCP registration, progress and result submission succeeded for diagnostic run
  `run_a999fd03fc2246649b69a3d5b25a17b0`; receipt was RUN_RESULT_SUBMITTED.
  No external chat message was sent. The original reported Run ID was not found in the
  current production database and was not fabricated or resubmitted.

Status: runtime restored and reporting acceptance passed; mission remains verification/pending_review.

## 2026-09-23 Forge Journal conversational capture

- Supersedes the disabled-by-default detail in the on-demand lifecycle entry below. The runner is
  now an armed, dormant one-shot: zero time/logon triggers, zero Task Scheduler retries, no
  watchdog, no resident process, and no next scheduled run. Explicit Stop disables delivery;
  Start re-arms the task and drains the queue once.
- Added `lab_journal_capture_chat`. It validates and idempotently records a structured local
  worklog, queues one `CREATE_LOG`, and requests one runner execution. When the chat platform does
  not expose a source identifier, the tool derives a stable content reference and idempotency key.
- The deployed `lab-worklog` skill now performs conversational intake: infer Problem, Experiment,
  Repair, or Build; preserve the raw note; ask only for missing object/action/observation facts;
  and never capture generic advice, hypothetical planning, sourcing discussion, meta-discussion,
  or an opt-out. Direct Forge chat registers as REVERSIBLE and may call only the combined capture
  tool; raw queue/transport tools and higher-risk Forge mutations remain blocked.
- Live profile, guard, MCP schema cache, runner task, and gateway restart were verified. The task is
  Ready/Armed with `--once`, zero triggers/retries/processes. Full regression: 226 passed plus five
  subtests; targeted Ruff passed. No real journal entry or external notification was created for
  verification.

Status: conversational capture and event-driven delivery deployed; mission gate remains
verification / pending_review.

## 2026-09-23 Forge Journal on-demand lifecycle

- User requested explicit start/stop in place of the 15-minute scheduled runner. The installer
  now registers no triggers or failure retries and disables the task unless StartNow is explicit.
  Profile deployment no longer passes StartNow. Migration exports old task XML before replacement.
- Management supports migration and reports trigger/retry counts; start/restart refuse legacy
  automatic configuration. Stop disables the task and any legacy watchdog before process cleanup.
- Live migration passed: Disabled, zero triggers, zero retries, no watchdog, zero runner processes,
  and no next scheduled run. All three changed PowerShell scripts parse; 15 focused Forge Journal
  tests passed. No live sync/notification acceptance was run for this lifecycle change.
- Existing unrelated workspace changes were preserved. Mission remains verification/pending_review.

## 2026-09-23 ChatGPT Bridge on-demand lifecycle

- Supersedes the automatic lifecycle in the deployment-foundation entry below. The user selected
  on-demand operation; the live queue was empty and no accounts were configured before migration.
- Removed the live one-minute watchdog, logon trigger, and automatic failure retries. The new
  manager supports explicit Start, Stop, Status, dashboard launch, and migration with task XML
  backups. The installer now defaults to stopped manual operation; the legacy watchdog script is
  inert. The Start menu shortcut starts the service before opening the dashboard.
- Live migration, healthy start, repeated start with one bridge process tree, and stop passed.
  Stop leaves the task disabled and scoped service processes absent for more than one minute.
  Repeat migration and all five bridge PowerShell parsers also passed. The 23 bridge tests passed
  with two dependency deprecation warnings. No database schema or Hermes profile changes occurred.
- The MCP client now lazy-starts the trigger-free scheduled task after a loopback connection
  failure and waits up to 30 seconds before failing the tool call. Operators should keep the service
  running until research completes; forced interruption uses existing durable recovery and uncertain
  submissions require human review. A live stopped-to-healthy cold start passed with the task in
  Ready state, zero triggers, zero retries, and no watchdog. All 24 bridge tests and targeted Ruff
  passed. Live ChatGPT round trips still await account setup.

Status: on-demand lifecycle selected; mission gate remains verification / pending_review.

## 2026-09-23 ChatGPT browser context recovery

- Diagnosed `BROWSER_UNAVAILABLE` after the dedicated Chrome window was closed or its automated
  login path disconnected. The runner retained a closed Playwright context and reused it on the
  next Open or Verify action.
- The browser adapter now checks that a cached Chrome browser is still connected before reuse,
  discards disconnected contexts, and launches the account's isolated Chrome profile again.
  Unexpected browser and runner exceptions are written to the rotating service log instead of
  being represented only by the generic account status.
- Focused bridge regression is 25 passed; targeted Ruff passed. This recovery does not attach to a
  personal Chrome profile or copy cookies. Chrome's default-profile debugging restriction remains.

Status: disconnected dedicated profiles recover on the next account action; live retry remains.

## 2026-09-23 Human-only ChatGPT authentication

- Clarified the account onboarding boundary: UuMA opens a visible isolated system-Chrome window,
  while the human enters all passwords, email codes, OTPs, and MFA and then explicitly requests
  verification from the local dashboard.
- Removed the minimized-window launch argument and renamed the dashboard actions to `Open browser
  for human sign-in` and `Verify completed sign-in`. The bridge still never copies credentials or
  attaches to a personal Chrome profile; automation begins only after visible identity verification.

Status: authentication is an explicit human step; post-authentication consultation remains automated.

## 2026-09-23 Human handoff page-close recovery

- The first logged `BROWSER_UNAVAILABLE` was a page-close race: the selected ChatGPT page closed
  between enumeration and `bring_to_front`, while the containing Chrome browser still reported a
  connected context. The dashboard later remained at its cached `Connecting` shell because the
  trigger-free bridge service itself was stopped and port 8787 was not listening.
- Account Open now ignores already closed pages and retries once with a fresh isolated context when
  Playwright reports `TargetClosedError`. Focused coverage reproduces the close during human
  handoff and verifies a new ChatGPT page is opened.

Status: page-close race repaired; stopped service still requires lazy agent start or dashboard shortcut.

## 2026-09-23 ChatGPT Web Bridge deployment foundation

- Added a durable, account-serialized ChatGPT Web consultation queue to `uuma.db`, with run-bound
  identity enforcement, idempotent requests, per-agent/project/thread conversation isolation,
  append-only state events, explicit clarification, cancellation, pause, and uncertain-submission
  recovery. A crash during submission cannot blindly replay the prompt.
- Added the loopback account dashboard, human-only account and route administration, a visible
  Playwright browser transport using separate account profiles, and six narrow MCP tools. Browser
  preflight verifies the signed-in email, workspace, requested capability, exact conversation, and
  completed result provenance before returning an answer.
- Deployed chat, search, and deep research to Orchestrator, Brainstormer, and Wisdom-Oldman. Deployed
  lab-related search to Forge-Lab-Bot. Scholar and Yonc have no bridge MCP or skill, and exclusion is
  repeated in the Hermes guard and service authorization boundary.
- Installed a limited-user logon task, one-minute watchdog, loopback-only dashboard on port 8787,
  Start menu shortcut, rotating logs, profile/database backups, and a rollback that removes only
  bridge configuration while preserving later unrelated edits, consultation history, and browser
  profiles. A live two-process-tree termination drill reached zero bridge processes and the watchdog
  restored a healthy service automatically.
- Native Hermes probes connected to all six tools from the four allowed profiles. Scholar and Yonc
  remained excluded. The full regression is 217 passed with three existing third-party warnings;
  full source/test Ruff, dashboard JavaScript syntax, five PowerShell parsers, and the deployment
  health check passed.

Status: service deployed and awaiting human entry of the `main` account identity plus manual
ChatGPT login. Live chat, search, and deep-research round trips remain the final acceptance step.

## 2026-09-23 Forge Journal low-frequency lifecycle

- Replaced the resident 15-second polling process and separate one-minute PowerShell/WMI watchdog
  with one scheduled `--once` run every 15 minutes. Each run drains writes and notifications,
  reconciles Forge Logs and Candidate knowledge, records lifecycle evidence, and exits.
- The Runner task keeps bounded native Task Scheduler retry (`RestartCount=3`, one-minute interval)
  without a second process-scanning task. The legacy watchdog is unregistered during installation.
- Lifecycle controls now preserve operator intent: `Stop` stops exact profile-scoped processes and
  disables future triggers; `Start` re-enables the schedule and runs an immediate cycle; `RunOnce`
  executes one foreground cycle without creating a resident process.
- Production verification passed: the scheduled action completed with 20 logs, zero candidates,
  conflicts, queued writes, or notices; `Stop` remained disabled with zero processes for more than
  one minute; and the subsequent `Start` completed once and scheduled the next run 15 minutes later.
  All 217 repository tests, 15 focused Forge Journal tests, full Ruff, three active deployment
  PowerShell parsers, and `git diff --check` passed.

Status: low-frequency unattended synchronization selected; expected maximum notification and
manual Notion-ingestion latency is approximately 15 minutes.

## 2026-09-22 Forge Journal V2 unattended activation

- Bound the durable queue to the existing default Hermes `notion` connection at runtime without
  copying its credential into the Forge profile, `lab.db`, source files, or queued payloads. The
  connector maps create, visible append-only patch, Candidate-only upsert, and refresh operations
  to the existing lease/finish contract with remote hash evidence and visible sync status.
- Activated 15-second write/notification polling and 15-minute full reconciliation. A limited-user
  logon task runs the connector, and a one-minute watchdog restored the exact runner automatically
  after a zero-process recovery drill.
- Implemented LAB_BOT/Hermes notification delivery through the latest eligible Forge route, with
  the latest default Hermes route as the bootstrap fallback. A reversible live acceptance appended
  `LAB_BOT Enrichment` and `Change Notice`, synchronized successfully, removed all five temporary
  blocks, restored the original content hash, and delivered its notice as `SENT`.
- The first REST reconciliation exposed hyphenated versus compact Notion page IDs as two local
  identities. The runner was stopped, the additive normalization migration merged 40 local rows
  back to the canonical 20 while preserving jobs, events, and notifications, and the restarted
  runner reports 20 `SYNCED`, zero conflict, zero queued job, and zero pending notice records.
- Production backup before activation:
  `%LOCALAPPDATA%\UuMA\backups\lab-before-forge-journal-activation-20260922-doit.db`.
- The host Scheduled Task startup evidence reports 20 canonical pages, zero queued jobs, a clean
  queue drain, and reconciliation of all 20 logs with zero candidates or conflicts. The foreground
  read-only refresh health probe completed as `SYNCED` in one attempt.
- Forge Journal regression at the activation snapshot: 15 focused tests passed; targeted Ruff,
  five deployment PowerShell parsers, and `git diff --check` passed. At that snapshot the full
  repository suite was 213 passed and one unrelated `chatgpt_bridge` failure; this was superseded
  by the 217-test passing low-frequency lifecycle verification above.

Status: unattended synchronization and agent notification delivery active; reviewed conflict
resolution remains a separate user-authorized product action

## 2026-09-22 Forge Journal V2 synchronization foundation

- Added an additive Forge Journal synchronization ledger to `lab.db`: page identity and hashes,
  idempotent pull/push jobs, worker leases, bounded exponential retry, append-only events, visible
  conflict state, and a separately retried notification outbox. A successful write requires remote
  hash evidence; a queued or failed write cannot be reported as synchronized.
- Enforced the agreed knowledge boundary in Worker MCP: LAB_BOT may create or refine candidates but
  cannot accept, reject, supersede, deprecate, or promote its own lesson. Direct-chat mutation guard
  coverage includes the new journal queue/delivery tools.
- Backed up production `lab.db` to
  `%LOCALAPPDATA%\UuMA\backups\lab-before-forge-journal-v2-20260922-2139.db`, then performed a
  non-destructive read-side reconciliation. All 20 legacy Forge Logs are registered with current
  Notion identity and content hashes; all 20 Notion rows and all 20 local records report `Synced`.
  No journal body was rewritten and no conflict or pending notification was created.
- Added the linked Notion implementation page `Forge Journal V2｜同步实施计划`. The next deployment
  boundary is the unattended OpenClaw transport and Hermes-route notification worker; neither is
  represented as active yet.
- Final regression: 185 tests plus 5 subtests passed with one existing third-party warning.
  Changed-code Ruff and `git diff --check` passed.

Status: durable foundation and initial reconciliation verified; unattended transport remains next

## 2026-09-22 Question Orbit runtime reliability acceptance

- Hardened deployment with a separate one-minute Watchdog task that starts the logon-triggered Runner
  only when its exact profile-scoped process is absent. Both tasks use `StartWhenAvailable`,
  battery-safe execution, the existing failure restart policy, and `MultipleInstances IgnoreNew`;
  the Runner also retains its process-level singleton lock and starts immediately after installation.
- Added a user-readable `orbit-runner-lifecycle.log` for launcher start, exit, and error evidence.
  Enabling the system-wide Task Scheduler Operational channel was attempted but Windows correctly
  denied it to the limited user token; that optional channel requires an elevated administrator
  command and does not affect recovery.
- Production recovery drill passed: the exact two-process Wisdom runner tree was force-terminated,
  zero runner processes were observed, and the repeating trigger automatically restored two Python
  processes in one runner tree at the next minute. No database, Orbit, notification, or knowledge
  history was reset.

Status: unattended runner self-healing passed. Final regression is 176 tests passed with one existing
third-party Pydantic warning; Ruff, all four deployment PowerShell parsers, `git diff --check`, the
live acceptance report, and the current singleton task state passed.

## 2026-09-21 Yonc specialist deployment acceptance

- Synchronized UuMA to `447ea6d` and `yonc_agent` to `22aae72` while preserving both
  dirty worktrees. The Yonc pre-pull state remains recoverable in the named Git stash
  `pre-uuma-yonc-deploy-20260921`; the three runtime-data conflicts were resolved in favor
  of the user's local state.
- Installed the `yonc` identity, profile, SOUL, project-management skill, audit/guard
  plugins, Worker MCP, and Yonc Project MCP. The profile retains only `uuma-worker` and
  `yonc-project`; unrelated inherited MCP servers and terminal/computer/delegation
  toolsets are absent.
- Created the explicit canonical graph database at
  `yonc_agent/data/project_graph.sqlite3`, applied schema 1.2 migrations, dry-ran and then
  imported all 687 valid legacy records, and verified database identity
  `5db40e09ff89dda4`, graph version 1, and node count 687 through the live loopback API.
- Repaired deployment defects found only on the production Windows path: safe script-root
  defaults, PowerShell 5 RNG and mutable-list compatibility, separate UuMA/Yonc Python
  runtimes, an MCP 1.x compatibility constraint, exact MCP-scope configuration, and a
  scope-aware deployment checker. Repeated deployment passed with manifest
  `yonc_agent/data/deployments/20260921-231545/manifest.json`.
- Native Hermes MCP probes connected to 60 Worker tools and 9 Yonc tools. A real-model
  direct-chat acceptance registered `run_fbc107b667f84d1e80d1f3246b133cd9`, read and
  summarized the live graph without mutation, and submitted a `COMPLETED` result; its
  current UuMA projection is the required `REVIEW` state pending independent verification.
- Regression evidence: UuMA 175 passed plus 5 subtests with the existing third-party
  Pydantic warning; Yonc 181 passed with one environment-dependent skip; frontend 58
  passed and the production build succeeded. UuMA Ruff, deployment PowerShell syntax,
  UuMA diff checks, and scoped Yonc deployment diff checks passed.

Status: Yonc direct-chat deployment and governed read acceptance passed; no production
project write was performed, and the existing mission gate remains pending user review

## 2026-09-21 Question Orbit final production acceptance

- Closed the final unattended-runtime gaps found during acceptance: provisional Cycles reopen their
  frontier, source IDs are not recounted across Cycles, satisfaction requires two newly cited sources
  with located evidence and no conflict, pause/stop cancels active work, and explicit budget changes
  remain reviewer-only. Offline KAG construction now preserves bounded, located chunk evidence and
  continues through the already explicit degraded-reasoning path without approving candidates.
- Made deployment actually single-instance and reversible. The runner holds a cross-process lock;
  install/uninstall terminates only exact Wisdom profile runner processes; and packaged-app
  LocalAppData redirection is resolved to the physical data directory passed to the external Windows
  task. A misrouted acceptance probe was STOPPED with its event history preserved, its temporary task
  was removed, and six verified repository-root runtime artifacts created by one rejected resolver
  attempt were removed after their exact paths were checked.
- Live acceptance Orbit `orbit_7d692f9d89295de6ce3fa0f306af1027` recovered its expired lease as
  attempt 2, completed one durable Cycle, ingested 2 unique public RFC sources, and created 40 unique
  located evidence records. It terminated as `BUDGET_EXHAUSTED` at the QUICK token limit, sent both
  `FIRST_USEFUL_ANSWER` and `BUDGET_EXHAUSTED` through the latest originating Telegram route, retained
  a valid event chain, and produced no `CLAIM_ACCEPTED` or `PATCH_APPLIED` event.
- Docker Desktop initially failed on the stale zero-byte
  `userAnalyticsOtlpHttp.sock`; with all WSL distributions already stopped, the exact socket was moved
  through Debian to `userAnalyticsOtlpHttp.sock.stale-20260921-1147.bak`. No image, volume, database,
  or knowledge history was touched. Docker 27.0.3 then started, all four KAG containers became healthy,
  and 440 pending projection jobs replayed without failure. Final projection health is watermark
  596/596, lag 0, 456 APPLIED.
- Final live state: the hidden `UuMA Question Orbit Runner` task is active with one runner tree,
  `UUMA_QUESTION_ORBIT_ENABLED=true`, and the Wisdom Knowledge MCP connects with 40 tools. Latest
  pre-runner backup: `%LOCALAPPDATA%\UuMA\backups\wisdom-before-orbit-runner-20260921-114123525.db`.
- Final regression: 172 passed with 5 subtests and one existing third-party Pydantic warning. Full
  `src`/`tests`/deployment-verifier Ruff, deployment PowerShell syntax, and `git diff --check` passed.

Status: deployment and production acceptance passed; `mission_status.json` remains at verification /
pending_review for the separate user/Orchestrator gate decision

## 2026-09-21 Question Orbit production deployment

- Historical checkpoint only; the final production acceptance entry above supersedes its tool count,
  regression count, and pending first-Orbit observation.
- Completed the previously deferred unattended runtime: one globally leased Cycle at a time,
  heartbeat and expired-lease recovery, three-attempt retry, idempotent Cycle keys, budget accounting,
  durable provider usage, and a three-attempt notification outbox. Retry delay keeps its Orbit
  active so another runner cannot create a duplicate Cycle.
- Added controlled OpenAlex, Crossref, configured RSS/Atom/sitemap, explicit user-URL, and optional
  Brave discovery. Brave is disabled without a local key and hard-limited to 950 monthly requests.
  Public acquisition validates DNS before every hop, revalidates redirects, blocks private/reserved
  addresses, bounds size and MIME, rejects unsafe XML declarations, and stops on login, paywall, or
  CAPTCHA pages. Robots, host pacing, and Retry-After are enforced.
- Added the independent `uuma.orbit_runner`, source ingestion/candidate extraction/KAG projection
  loop, original-route Hermes notification dispatch, rotating local log, and reversible hidden
  per-user Scheduled Task. Deployment backs up `wisdom.db`; uninstall removes only the task and
  preserves all canonical and research history.
- Deployed with `UUMA_QUESTION_ORBIT_ENABLED=true`. Backup:
  `%LOCALAPPDATA%\UuMA\backups\wisdom-before-orbit-runner-20260921-102844553.db`. The Scheduled Task
  is running, its Python worker is resident, the Hermes gateway restarted cleanly, and Wisdom's
  Knowledge MCP connected with 39 tools.
- Live `wisdom.db` contains the three additive runtime tables, has a valid event chain, zero existing
  Orbit backlog, and projection watermark 109 with zero lag. No synthetic production Orbit was
  inserted; the first real eligible Wisdom question will provide the unattended-cycle acceptance.
- Full UuMA regression: 155 passed with 5 subtests and one existing third-party Pydantic warning.
  Full `src`/`tests` Ruff, PowerShell syntax, session gate, and diff checks passed.

Status: production enabled and idle-health verified; first organic unattended Orbit remains to be
observed, and the mission gate remains pending user/Orchestrator review

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

## 2026-09-25 Wisdom document contamination correction

- Investigated the reported topic `topic_c59bee6f14ed419abb16da707e8ffe66` in the live canonical
  `wisdom.db`. Its root question was a pasted `{"detail":"Wisdom topic not found"}` API error.
  Preflight had accepted it as a new topic, created five framework questions and a DEEP Orbit, and
  published a Sylvester answer with zero source or evidence citations.
- Stopped the invalid Orbit, archived the topic, and appended document version 2 with an explicit
  correction. Version 1 and the event chain remain available for audit. The fixed link returns 200;
  its current page contains the correction and `#overview` anchor, with no Sylvester text.
- New machine-error validation rejects a pure API error object before graph, topic or Orbit work.
  Uncited KAG answers are withheld as insufficient evidence, including from a background document
  and its notification summary. A table-of-contents click returns the page to document view.
- Restarted the read-only Wisdom view and Hermes gateway. Local HTTP verification confirms the
  current correction and anchor. Full test suite: 262 passed, 5 subtests passed; Ruff passed.
  A fresh user-originated Telegram turn was not sent, so that delivery path remains unobserved.
