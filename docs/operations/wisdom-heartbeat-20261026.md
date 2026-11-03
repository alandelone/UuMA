# Native Wisdom three-hour self-check — 2026-10-26

The user explicitly requested a heartbeat inside Wisdom that periodically checks
whether unfinished research has a reason and opportunity to continue. This is
installed in the server Wisdom Hermes profile's native cron store, not as a Codex
chat automation or a new operating-system scheduler. Existing cron discovery was
performed first; the Wisdom profile had no prior jobs.

## Installed task

- Name: `Wisdom research self-check (every 3 hours)`.
- Native job ID: `cef6302a8e23`.
- Profile: `~/.local/share/uuma/pilot/home/profiles/wisdom-oldman`.
- Interval: 180 minutes, recurring with no repetition limit.
- Initial next run: 2026-10-26 **18:39:14 Asia/Kuala_Lumpur**.
- Enabled, state scheduled; no immediate run was requested or performed.
- Initially inherited the profile's agent model/provider. After the first trigger
  revealed an obsolete provider name, the job alone was pinned to `custom`, model
  `complex`, base URL `http://192.168.55.2:8080/v1`. Its existing tool/profile context
  and the independent `complex` coverage critic in the research worker are unchanged.
- Uses the existing research owner's Telegram route for meaningful results and
  native failure delivery. Route identifiers are retained privately, not in this guide.
- Operational instructions: `profiles/wisdom-oldman/WISDOM_HEARTBEAT.md` locally,
  and `WISDOM_HEARTBEAT.md` in the deployed Wisdom profile.

The task was created through Hermes's existing
`create_job_with_scheduler_registration` API and read back from its canonical store.
The profile ticker heartbeat and last-success marker were fresh (about 25 seconds
old) at installation. This proves the task is scheduled under a live scheduler; it
does not prove the first agent run, a future model call or notification delivery.

## Decision contract

Check canonical research status, open frontier, latest cycle explanation, human
pause/stop provenance, actual running lease, relevant dependencies, current quotas
and original pending provider jobs. The initial scope is the existing green-onion
Orbit `orbit_9ac4d099873b82f8f5a730cf07792419`. Do not resume unrelated historical
acceptance jobs or withdrawn error topics.

Classify RUNNING/NO_ACTION, RESUME, WAIT, NEEDS_USER or COMPLETE. Resume requires an
actual continuation opportunity and a concrete next step. A no-source pause is not
permission to repeat the same exhausted search every three hours. Human pauses and
stops take precedence; uncertain provenance waits for clarification. Preserve usage,
progress, references, source-review boundaries, the frontier and pending request IDs.
Only the existing research pipeline/critic can establish evidence sufficiency.

Each run records a small decision state in the profile's memory directory, with
the previous state retained and a last-notified incident signature. Ordinary checks
and unchanged waits return exactly `[SILENT]`, the native scheduler's supported
delivery-suppression marker. Meaningful recovery/completion, a new failure or an
actionable user decision may use the existing owner route. Do not duplicate native
delivery with an additional direct message or replay old failed notifications.

These are instructions for the scheduled agent, not a new deterministic enforcement
layer over its tools. Existing semantic permissions and quota guards remain in force.
The task is not a guarantee that research makes progress at every wakeup.

## First trigger and provider correction

The user sent a continuation after the first due time. At 19:24 Asia/Kuala_Lumpur,
canonical readback showed a trigger at **18:39:55**, last status `blocked_config`:
the inherited `antigravity-oauth` provider was unknown to the installed native cron
runtime. The agent did not execute a self-check; the scheduler remained healthy.
The next interval was already scheduled for **21:39:55**. This observed failure
supersedes the earlier installation-only readiness statement.

The existing job was updated through `update_job` with the user's previously
provided compatible `complex` endpoint. Runtime provider resolution and the native
full job configuration preflight both passed. Job ID, schedule and owner route were
preserved. The previous blocked result remains in history until a later actual run
records its outcome. No immediate model or research execution was induced during
this repair. Do not describe the preflight as a successful agent execution.

Exact pre-fix job contents and the provider correction receipt are retained privately
in the server audit directory as `job-before-provider-fix-private.json` and
`provider-fix-receipt.json`. The shared profile's model config was not changed and
no gateway restart was required. Native cadence/last-run readback and provider
preflight are distinct evidence from the next actual self-check result.

## Publication and rollback

No shared gateway restart, profile config change, server service restart, domain
database write, research requeue, model invocation or test run occurred at setup.
Only the Wisdom operational manual and its native cron job were added. Existing
research remains PAUSED until a later authorized agent decision changes it.

Private preview, source digest, original job-store backup when present and native
job readback are under server `~/.local/share/uuma/wisdom-heartbeat-20261026/` and
local `.uuma-local/wisdom-critic/heartbeat-install-receipt.json`. The deployed guide
SHA256 is `a0d629fdc012dd8d80801ed547b4cc23a7782e9e555b551e3b2a420ebfd519a5`.
Pause the exact native job through the existing cron API to disable future checks;
do not restore an old cron store over subsequent jobs or modify the knowledge DB.
Mission remains verification/pending_review. No Git commit/push or gate approval.
