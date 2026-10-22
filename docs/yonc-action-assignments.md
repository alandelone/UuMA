# Yonc Action assignment backend

User decision, 2026-10-20: allocate one existing, already decomposed leaf Action to one
executor. Reusing another author's documents records sources, not additional executors.
An Agent delivers work for user review. **All project acceptance is by the user.** There
is no automatic acceptance, predefined grading requirement, or UI/frontend change in this batch.
Manual human execution/late entry is deferred.

## Ownership and state

The Project Graph owns four additive tables: `action_assignments`, `action_deliveries`,
`action_reviews`, and `assignment_events`. UuMA continues to own Tasks and Runs in `uuma.db`.
Sources and artifacts stay in their original domain systems; the graph stores references.

The assignment lifecycle is:

```
PROPOSED --user approves allocation--> QUEUED
  --Orchestrator binds a real UuMA Task--> ASSIGNED
  --Orchestrator binds its current Run--> RUNNING
  --result delivered--> AWAITING_USER_REVIEW
  --user requests changes--> CHANGES_REQUESTED --resubmission--> AWAITING_USER_REVIEW
  --user accepts exact delivery--> ACCEPTED (Graph Action becomes DONE)
```

The last two transitions are alternatives. Only a user review of the current delivery and
result digest can accept work. Allocation approval does not accept a later result. User
reopening preserves earlier deliveries and reviews and creates a new dispatch round.
Cancellation preserves history. A bound assignment stays `CANCEL_REQUESTED`, reserving its
Action, until Orchestrator synchronization confirms the UuMA Task/Run is terminal. An unstarted
Task is durably cancelled before a late Run can register; a running worker receives the existing
UuMA cancellation request and remains reserved until its actual stop receipt. The user request
alone is not proof an external worker has stopped.

Each delivery records the single actual executor, UuMA Task/Run, result digest, reported
completion time, separately observed receipt time, method, summary, output references,
and input/source references. User review has its own reviewer and timestamp. Immutable
delivery/review/event tables reject SQL UPDATE/DELETE. This is application audit history,
not proof that a remote artifact's content cannot change; artifacts may supply a version/SHA.

## Backend API and credentials

New writes use three **different**, server-configured bearer credentials:

- `YONC_AGENT_COMMIT_TOKEN`: existing Yonc identity, allowed to propose allocations only.
- `YONC_ORCHESTRATOR_TOKEN`: receipt relay and UuMA binding. Never accepts project results.
- `YONC_USER_REVIEW_TOKEN`: trusted human client, kept outside Agent profiles and model context.
  Only this identity approves allocations, accepts/returns deliveries, cancels, or reopens.

Missing credentials fail closed; duplicate configured credentials are rejected. No request
body `actor`, `user_approved`, or self-reported acceptance can substitute for user authority.
Token setup and running-service/profile rollout are separate operational steps; the original
implementation did not provision credentials or restart services. The existing general local graph API is
not converted into a fully authenticated multi-user service by this scoped addition.

Every write requires `operation_id` and `expected_graph_version`; updates also require the
current `expected_revision`. Identical requests replay their original receipt, whereas a
different payload with the same operation ID conflicts. SQLite writer transactions and a
partial unique index enforce one open assignment per Action. Relevant existing transition,
legacy, undo and import paths cannot bypass managed assignment review. A changed Action
definition invalidates dispatch/acceptance; required `depends_on` nodes must be Done before
dispatch. UI/node transitions for unmanaged work retain their existing behavior.

| API | Responsibility |
| --- | --- |
| `POST /api/v2/nodes/{node}/assignments` | Persist a proposal with one `executor_id` and `task_contract` |
| `POST /api/v2/assignments/{id}/approve` | User accepts the allocation, making it available for handoff |
| `POST /api/v2/assignments/{id}/binding` | Orchestrator links the actual UuMA Task/current Run |
| `POST /api/v2/assignments/{id}/deliveries` | Orchestrator relays current executor/result evidence |
| `POST /api/v2/assignments/{id}/reviews` | User `accept` or `request_changes`, bound to delivery/result digest |
| `POST /api/v2/assignments/{id}/cancel` or `/reopen` | Explicit, versioned user decision with a note |
| `GET /api/v2/assignments?node_id=...&state=...` | Bounded allocation listing |
| `GET /api/v2/assignments/{id}` | Full delivery, review and operation history |
| `GET /api/v2/nodes/{node}/completion` | Existing Action's executor/results/acceptance history |

`task_contract` contains objective, required capabilities/tools, input references, risk, and
execution class. It has no automatic acceptance criteria. New request schemas forbid unknown
fields. All review decisions require a user note; this records a decision, not a grading rubric.

## Orchestrator handoff

`prepare_yonc_assignment` reads the accepted proposal, checks its capabilities and dependencies,
and creates/routes/assigns one UuMA Task using a database/assignment/round idempotency key.
It returns `execution_started=false`. A successful call satisfies the existing delegation
preflight for that Task; execution still uses the normal Hermes route. It never launches a
worker or silently chooses a different executor. A split or changed contract needs a new
reviewable proposal rather than a worker substitution.

`sync_yonc_assignment` binds the current Run and relays its persisted result to the graph.
These UuMA tasks set `acceptance_authority=USER`: another Agent cannot verify them complete.
After an actual Graph user acceptance, synchronization records that exact user decision in
UuMA as well. Other UuMA tasks retain their existing independent-verification policy.

Cross-system writes are not atomic. If UuMA assignment succeeds and Graph binding fails,
the Task remains durable and a retry reuses it; no execution is claimed. If Graph user
acceptance succeeds but UuMA synchronization fails, the Graph decision remains authoritative
and can be reconciled. Superseded results, changed versions, denied capabilities and uncertain
responses are visible conflicts, not permission to replay work or accept a different result.

## Storage and verification

The Yonc migration `20261020_0004` adds the four tables without changing existing project
rows. The local startup upgrader also discovers them through registered SQLAlchemy metadata.
The existing Graph API/schema label remains 1.2; the additive assignment contract is version 1.
Migration downgrade refuses to delete audit history. Use an explicitly selected backup for
any operational rollback; no live databases are migrated by development tests.

Contract tests use disposable Graph/UuMA databases and disable frontend builders. They cover
one executor, explicit user-only acceptance in both systems, provenance/time distinction,
stale results, idempotency, concurrent proposals, legacy/honc bypass, immutable history,
schema preservation, and cross-system handoff/reconciliation without network/model calls.

Verification on 2026-10-20: the full UuMA suite plus the four relevant Graph backend suites
passed **710 tests and 5 subtests**, with one existing pre-v1.1 backup test skipped because
that backup is absent. The new Alembic migration was exercised on an isolated existing Graph
database and preserved its project rows. Ruff and whitespace checks passed. The machine's
test environment needed its missing SQLAlchemy/Alembic, SoupSieve and declared pypdf
dependencies installed; no assertion was weakened to accommodate those missing dependencies.
The legacy configuration test now seeds a fake configuration, and the daemon test imports
its global instance only after selecting temporary storage. An initial broad collection hit
an unrelated default-database read error; no database repair was attempted. The successful
full run used temporary data directories throughout. JUnit evidence is saved locally at
`.uuma-local/yonc-assignment-regression-20261020.xml`.

No frontend/static asset, live Graph database, service restart, real Agent dispatch, or model
inference was part of the original implementation/verification.

## Runtime rollout, 2026-10-20

The user subsequently authorized deployment. The running Graph service at
`http://127.0.0.1:8766` loads `C:/Users/Alandelone/CodeSpace_Local/yonc-graph`, a separate
checkout from `yonc_agent`. Only the assignment changes were applied there; its existing
speech endpoint, view ordering, frontend sources and built assets were preserved.

Native Windows service-context SQLite backups were verified before migration. The assignment
migration now follows the already-deployed `20261006_0004` execution migration; that existing
migration was also brought into the source checkout. A production-snapshot rehearsal and the
live additive upgrade to `20261020_0004` preserved every pre-existing Graph table's records.
The graph retains 691 nodes, graph version 65 and its original database identity. The UuMA
control database retains its 424 events, existing Tasks/Runs and a valid event hash chain.

Three distinct credentials are configured. The Graph launcher reads protected files under
`%LOCALAPPDATA%/UuMA/credentials/yonc-assignments/`; existing planner credentials are reused
when present. Orchestrator receives only its relay credential, and Yonc receives only its
planner credential. `user-review-token` remains outside Agent profiles/configuration and
is reserved for a trusted human client. Credential values are never tool arguments or reports.
The launcher restores its caller's environment after spawning the server.

The default Orchestrator and Yonc guards, managed role instructions and Yonc skills/reference
documents were refreshed. Hermes restarted gracefully and serves the same seven profiles.
Fresh stdio MCP sessions using the actual installed configuration discover both Control
handoff tools and all three Yonc assignment tools. Read calls succeed; missing-assignment
probes confirm Graph connectivity without creating work. Agent review attempts return 403,
unauthenticated writes return 401, and the user credential reaches normal record validation.

Deployment checks passed 38 merged Graph contracts and 60 control/bridge/guard contracts;
the same absent historical-backup case remains skipped. Launcher parsing and focused lint
passed. No real project task, delivery, acceptance or model request was created. Backups,
row fingerprints, test reports and sanitized deployment evidence are preserved under
`.uuma-local/yonc-assignment-deploy-20261020/`. There is still no new acceptance UI.

Windows packaged desktop tools can see a different AppData database file from the native
service despite identical path text. The desktop view reported corruption, whereas the
actual service-context database passed integrity and event-chain checks. No database repair,
replacement, reset or historical-data recovery was performed. Future operational checks and
backups must use the service's native context.
