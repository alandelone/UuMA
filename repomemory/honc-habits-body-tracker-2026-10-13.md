# Honc habit/body tracker discussion memory

Date: 2026-10-13, Asia/Kuala_Lumpur. The user explicitly requested "ok record it".

Canonical discussion record:
[honc habits, body tracker, and diary](../docs/plans/honc-habits-body-tracker-discussion-2026-10-13.zh-CN.md).
The honc role document links this record. This is a requirements record, not implementation,
deployment, migration, or mission-gate approval; frontend remains deferred.

- Retain original habits; additions and changes remain supported in the intended backend.
- Keep one honc agent, separating work execution, habits, body observations, and diary/history.
- Separate habit configuration, reminder policy/receipts, and actual check-ins. Preserve history.
- Default reminders once per occurrence; timing/count/importance configurable. No extra chasing.
- Time anchors: fixed times/windows, wake-up, bedtime only.
- Wake-up default 08:00; earlier explicit wake/day-plan start advances the same reminder occurrence.
  Already reminded means no repeat at 08:00 or on a later wake report. Reminder time is not wake time.
- Bedtime default 21:30; one diary invitation can include today's body state.
- Body records are user supplied, including positive wellbeing. Never proactively ask for changes.
- No nightly chase of unchecked habits. Diary is itself a habit.
- Original habit names and old schedules are historical inputs; only the two defaults above were
  newly confirmed. Do not silently restore old Toilet/Rest triggers or extra old reminder points.
- Configuration scope, per-habit schedules, early completion suppression, notification recovery,
  earlier bedtime behavior, simultaneous reminders, and migration details remain open.

Future work should read the full discussion record and current implementation before designing
backend changes. Yonc retains project ownership; UuMA retains runtime control; honc owns daily facts.

Later steering: stay on existing Hermes/profile/Skill/MCP architecture, with detailed scenario
manuals suited to the user's ordinary Terra-level runtime model. This is a design constraint,
not a model benchmark, model-change request, or permission expansion.

Collaboration preference: autonomously prepare engineering details; show the user only concrete
items needing review/comments. Do not infer acceptance from silence. A reviewable design packet
is now linked in the role/discussion records:
[review page](../docs/reviews/honc-architecture-2026-10-13/user-review.md),
[architecture](../docs/plans/honc-agent-tool-architecture-2026-10-13.zh-CN.md),
[tools](../docs/plans/honc-life-tool-contracts-v1.zh-CN.md),
[manual](../docs/plans/honc-life-runtime-manual-v1.zh-CN.md),
[feature contract](../docs/plans/honc-life-feature-contract-v1.json).

R1 early-completion suppression, R2 missed-window behavior (default30-minute single-point grace),
R3 grouping simultaneous reminders, R4 earlier bedtime were initially pending; user explicitly
accepted all four with "all follow your 建议" on 2026-10-13. Do not ask these again. Acceptance is
for product behavior and design preparation, not evidence that runtime settings were applied.
Existing wake08:00/bedtime21:30/once/no-body-followup remain confirmed.
No product code or live Skill edits, scheduler jobs, migration, notification, models or deployment.
Hermes local scheduler source confirms no_agent path and delivery outcome machinery; actual honc
notification/config integration remains unverified and must bind business IDs to real receipts.

Accepted defaults and boundary contracts are now in
[policy acceptance](../docs/reviews/honc-architecture-2026-10-13/policy-acceptance.json),
[reminder policy](../docs/plans/honc-reminder-policy-contract-v1.zh-CN.md),
[machine-readable defaults](../docs/plans/honc-reminder-policy-defaults-v1.json).
Design approval does not mark any new feature passes=true; actual implementation/Eval remains.

Later implementation: the backend foundation now exists in life_models, reminder_policy,
life_store, life_service and life_mcp. This supersedes the earlier no-product-code statement
for component implementation only. 126 honc regression/component tests passed with temporary
databases; versioned CRUD, records, corrections/void, trusted-adapter-only grants, message-bound
idempotency and nine optional MCP tools are implemented. Reminder policy is pure and does not send.
Current Hermes profile/Skills, user databases and old habits were not changed or migrated.
Live source authentication, durable instances/receipts, diary habit binding and model Eval remain.
Complete feature flags and 21 cross-component reminder scenarios remain unverified.
Review and exact limitations: [foundation result](../docs/reviews/honc-architecture-2026-10-13/backend-foundation-v1.zh-CN.md).

## 2026-10-14 live integration supersedes foundation-only status

User explicitly requested full setup and continued authorization; no renewed R1-R4 approval is needed.
The existing Hermes honc home now has nine Skills, honc_life source/capability hooks, 19 allowed
honc tools and five worker tools. Both MCP resource/prompt auto utilities are disabled. The old
unbound honc_check_habit route is excluded; host hooks also block skill_manage and arbitrary file,
cron or delegation writes. Preserve original model and credentials.

Eight original habits/configuration and four nonempty raw legacy logs were migrated to honc.db;
no invented personal habit/body/diary facts. Settings persisted once: wake08:00, bedtime21:30,
count1, importance ordering only, expiry, no body-change follow-up and no nightly unchecked chase.
OffJobBh stays manual, FullRest old type and exercise unit stay unknown. Old Notion read returned
401; local inheritance is complete but Notion synchronization is not claimed restored.

The unique no_agent native scheduler job3381ec71b9d2 is enabled; first automatic execution
completed11:29:20KL with statusok and empty outer output. Existing shared gateway11784 serves
honc Telegram connected. This is real scheduling proof, not a fabricated Telegram delivery test.
264 focused tests passed, including21 R1-R4 cases and real Hermes SDK2/stdio/scheduler fixtures.
Current receipts, actual model evaluation and rollback are linked from the live setup review.
Mission stays verification/pending_review; unrelated Scholar/science work must be preserved.

Final production-model isolation run dcceb24649aa4596a48683003bd7c659:8/8 correct durable
effects and replies;27 APIcalls/18 toolcalls, two worker result-contract validation errors were
self-corrected in partial-domain, no duplicate body write. Final sources frozen and same original
model/provider; no fabricated zero-token pass, no stronger fallback. Live default settings applied
and feature contracts13/13 backed by scoped evidence; real Telegram first-due receipt remains
normal-runtime evidence, not claimed observed by fixture callbacks. Final setup review is current.
