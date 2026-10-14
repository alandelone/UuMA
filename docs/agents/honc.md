# Honc

Status: daily execution, tracing, rounds, habits, and graph writeback implemented  
Agent type: customized persistent Hermes profile  
Primary role: daily execution, focus rounds, habit tracking, and verified task completion  
Parent: Hermes Orchestrator for Agent execution and coordination  
Authoritative sources: Yonc Graph for project structure and `done_when` criteria; `honc.db` for execution events  

## 1. Mission

Honc is the user's daily execution and tracing specialist. It guards the user's active execution front:
what was actually accomplished today, what outcomes were produced, whether criteria were satisfied,
what is the next action, and ensuring these facts are faithfully synchronized back to Yonc Graph.

```text
Read Next Action from Graph / User input
    -> 🛸 Prepare Round (Outcome + Tiny Step)
    -> 🍅 Execute Focus Round
    -> Record Execution Fact & Duration
    -> Assess Done Criteria against done_when
    -> Apply Action Decision to Graph (done / reopen)
    -> Verify Receipt & Update Daily State
```

## 2. Boundaries and Colleague Separation

- **Yonc**: Manages project trees, decompositions, milestones, and priorities.
- **Yonc Graph**: The single source of truth for task structure, states, and `done_when` standards.
- **Honc**: Manages round lifecycles, execution facts, actual duration, habits, completion assessment, and Graph writeback.
- **UuMA**: Agent registration, direct runs, and control audit plane.

Honc never alters project hierarchies, never modifies milestones or parent nodes, and never changes project priorities.
Honc only automatically submits completions for leaf `ACTION` nodes when all 6 preconditions are met.

## 3. Toolsets and MCP Integration

Honc operates with:
- `uuma-worker`: Restricted worker lifecycle tools (`register_direct_run`, `get_assignment`, `report_progress`, `block_run`, `submit_result`).
- `honc-execution`: FastMCP server exposing 19 allowed semantic tools: nine work execution/graph tools and ten life-record tools. The legacy unbound habit route is excluded.

## 4. Habit, body tracker, and diary discussion (2026-10-13)

The user asked to record an expansion toward a unified daily companion: retain the original
habits, support configurable reminders, record user-supplied body observations, and keep diary
and historical queries. The proposed internal separation keeps work execution, habits, body
observations, and diary records distinct while allowing one daily view.

Confirmed reminder defaults are 08:00 for wake-up (advance on an earlier explicit wake/day-plan
start without a duplicate at 08:00) and 21:30 for bedtime diary/body logging, Asia/Kuala_Lumpur.
Reminders default to one per occurrence; no additional unanswered-message chasing, no nighttime
chase of unchecked habits, and no proactive follow-up about body changes. Contextual anchors are
limited to wake-up and bedtime alongside fixed times/windows.

These are recorded requirements and architecture directions, not a claim of new implementation
or deployment. Backend expansion remains future work and frontend is deferred. Full decisions,
inherited habit mapping, and open implementation questions are in
[the habit/body tracker discussion record](../plans/honc-habits-body-tracker-discussion-2026-10-13.zh-CN.md).

Architecture design materials now include a
[Hermes-based design](../plans/honc-agent-tool-architecture-2026-10-13.zh-CN.md),
proposed tool contracts, scenario manuals, and an unverified feature acceptance list.
The user prefers autonomous engineering preparation and consolidated review of concrete product
choices. On 2026-10-13 the user accepted all four R1-R4 recommendations in
the [review record](../reviews/honc-architecture-2026-10-13/user-review.md): completion suppression,
window expiry with default 30-minute point grace, grouping simultaneous reminders, and advancing
explicit early bedtime with a shared nightly quota. They no longer need repeated confirmation.
This is product-policy acceptance; implementation, runtime application, deployment, and technical
verification have not occurred through these documents, and no mission gate was changed.

## 5. Backend foundation implementation (2026-10-13)

An isolated life-record backend now adds strict models, versioned habit configuration, settings,
habit/body/diary records, corrections and void history, source-bound atomic operation receipts,
and an optional registration function for nine semantic tools on the existing honc MCP server.
The reminder component implements pure policy evaluation, grouping and anchor advancement.
Existing honc regression and new component tests total 126 passing cases; these use fake inputs
and temporary databases. Current live profile tools and Skills remain as listed in section 3.

This is component implementation, not live deployment or complete feature acceptance. Real Hermes
source authentication, old-habit migration, durable occurrence/delivery handling, diary-habit
binding and model Eval remain. No true notification was sent and no existing user data migrated.
See the [reviewable foundation result](../reviews/honc-architecture-2026-10-13/backend-foundation-v1.zh-CN.md)
and [developer integration manual](../plans/honc-life-backend-foundation-v1.zh-CN.md).

## 6. Live life extension (2026-10-14)

The existing honc profile now includes versioned habit settings, separate habit/body/diary records,
source-bound receipts, corrections and historical queries. Its nine detailed Skills use the existing
Hermes loop, host hooks and MCP servers. The original eight habit definitions and four nonempty
legacy activity logs were inherited without inferring personal completion or symptom facts.

The existing shared gateway serves honc with Telegram connected. The unique profile-local
`honc-life-semantic-tick-v1` no-agent job is enabled and its first automatic tick completed with
`last_status=ok`. It compiles semantic occurrences and uses the native durable delivery queue;
the outer scheduler tick stays silent. Default wake 08:00 and bedtime 21:30 share occurrence quotas
with explicit earlier anchors. A missed window expires, and body changes are never proactively
questioned. Frontend remains deferred.

Current focused integration regression: 264 tests passed, including all 21 approved R1-R4 cases,
actual installed Hermes plugin/stdio/scheduler integration with a fixture delivery callback,
and strict manual example schema validation. Fixture callback delivery is not proof of a real
Telegram receipt. Live state and actual production-model evaluation are recorded separately in
[the setup review](../reviews/honc-architecture-2026-10-13/live-setup-review.zh-CN.md) and its linked
JSON receipts. Earlier foundation sections describe their historical state and are not current
deployment status. The mission verification gate remains pending review.
