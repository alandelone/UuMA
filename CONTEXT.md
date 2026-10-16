# UuMA Domain Glossary

Terms describe the target commerce contracts unless explicitly marked existing.
The [implementation plan](docs/plans/labbot_implementation_plan.md) records implementation gaps.
Updating this glossary does not mean those capabilities already exist.

## Lab Bot — E-Commerce & Procurement

**ownership / purpose**
: User-confirmed on 2026-09-27: whole-line self / others only, with no quantity allocation
  by purpose and no purpose sub-lines. Until reviewed, ownership is unset and review_status
  tracks pending review; there is no third ownership enum. Mixed-purpose lines remain unresolved
  and cannot be partially classified as self. AI suggestions and user decisions are separate.
  Partial deliveries may be received in batches under the same whole-line ownership; that is
  delivery accounting, not purpose allocation. Only confirmed self electronics explicitly
  approved for lab use may enter receipt preview; others never creates stock.

**category**
: electronics / consumable / tool / other. Only explicitly lab-approved electronics can enter
  component matching and receipt preview in this phase. Category alone never approves receiving.

**canonical component**
: An eSchematic-managed identity resolved using manufacturer, exact MPN, package and relevant
  technical attributes. Platform product IDs and SKUs track purchase identity, not component identity.

**order line**
: A stable line_id within a platform/account/order scope. Prefer a verified platform line ID;
  product ID plus normalized SKU hash is only a fallback candidate match. Collisions preserve
  distinct observations for review. Workbook hash, row position and sorting are not identity.

**order header**
: Minimal order provenance scoped by platform, stable local account_id and order_id. Tracks
  observations and completeness; existence is not permission to skip future changes or details.
  Newly captured proxy-purchase line details stay in the local JSON/Excel archive, not lab.db.

**batch receipt**
: Durable acknowledgment of one batch_id and payload hash, tied to archived source data and
  committed business evidence. Same-key/same-payload replay returns the original receipt;
  same-key/different-payload replay is rejected.

**review revision**
: A versioned user decision separate from observed evidence and AI suggestions. Excel returns
  base_evidence_version and base_review_version with line_id; stale changes become conflicts.

**lab supply**
: A confirmed lab item in consumable / tool / other. Kept in the review archive; no stock entry
  in this phase. Broader inventory support would require a later scope decision.

**offer snapshot**
: A price observation tied to platform/account, exact SKU, quantity, conditions, source and time.
  Maps to supplier_offers; not a purchase or cart authorization.

**receiving event**
: A RECEIVE inventory event after physical acceptance and a concrete approved receipt preview.
  The planned confirmation_id provides idempotency; current inventory_receive must be extended
  before this guarantee can be claimed. Non-RECEIVE transitions can also move stock into AVAILABLE.

**platform adapter**
: A platform-specific content-script module implementing parsing, page identity and read actions.
  core.js shares extraction logic; the service worker coordinates cross-navigation recovery.
  Python services own authorization and durable persistence.

**extraction range**
: Authorized date/order/count scope and the separately recorded completed/uncompleted portions.
  A checkpoint is recoverable only after its batch has a durable receipt.

## Lab Bot — Inventory & Builds

**inventory event**
: An append-only inventory_events entry moving quantity between buckets, for example RECEIVE
  into AVAILABLE or INSTALL from RESERVED to INSTALLED. Corrections preserve earlier history.

**purchase lot**
: A purchase_lots record linking received material to component_id, supplier and offer reference.

**component ref**
: A component_refs record caching a canonical component reference for local relationships;
  it does not by itself prove that a purchase has been physically received.

## Observatory — Multi-Agent Monitoring

**observatory item**:
A normalized projection envelope of an agent's domain artifact (project, topic, run, discussion, task, or turn) for unified fleet monitoring.
_Avoid_: Task, entity, record

**activity event**:
An immutable, timestamped runtime audit or execution event with global deduplication and agent provenance.
_Avoid_: Log entry, message

**harvest cursor**:
A durable checkpoint tracking the observatory's background progress through local audit spools and source databases.
_Avoid_: Pointer, offset

**source freshness**:
The reachability, freshness timestamp, and read health of an underlying database, tracked independently of reported execution status.
_Avoid_: Online status, heartbeat

**shared inspector**:
A single-page inspection panel for drilling down into an observatory item's timeline, sessions, tools, and artifacts without navigation.
_Avoid_: Modal dialog, detail page, drawer

**generic hermes adapter**:
A fallback observatory source adapter providing baseline activity stream and session exploration for newly registered agents lacking a specialized adapter.
_Avoid_: Default poller, unspecialized agent

**request epoch**:
A monotonically increasing counter used by the shared inspector to drop stale out-of-order asynchronous responses.
_Avoid_: Request ID, timestamp filter

## Question Orbit — Autonomous Research & Discovery

**discovery attempt**:
A single execution record of a query against an authorized discovery provider within an Orbit cycle, capturing the query, provider identity, semantic outcome, and raw failure or citation details.
_Avoid_: Search log, provider call, query trace

**cycle explanation**:
A structured, human-readable and machine-verifiable report synthesized at the end of an Orbit cycle, explaining attempted paths, failure classifications, remaining untried routes, and next recommended actions.
_Avoid_: Cycle summary, status message, failure log

**discovery outcome**:
A standard six-state semantic classification (`SUCCESS`, `NO_MATCH`, `TRANSIENT_FAILURE`, `AUTH_REQUIRED`, `BUDGET_REACHED`, `SKIPPED`) assigned to each discovery attempt, distinguishing between true lack of evidence and environmental or authorization blocks.
_Avoid_: HTTP status, error code, failure flag

**untried path**:
An authorized, configured discovery capability or provider mode that was not executed during the current cycle or whose prerequisites remain available for subsequent exploration.
_Avoid_: Missed search, fallback candidate, backup engine


