# Graph Engineering Decision Record

Source discussion: `chatgpt-conversation://6a8ee5a4-04f4-83ec-bdba-5c7dea541aec`  
Status: consolidated from the user summary and UuMA planning decisions

Graph engineering in UuMA means representing capability, work, and execution as explicit nodes,
edges, constraints, and revisioned events. It is not a claim that every problem requires Neo4j or a
separate graph database. V1 uses SQLite projection tables because the operational graph is modest,
local, transaction-oriented, and must be easy to rebuild.

The graph enables:

- capability-based Agent routing;
- dependency-aware readiness;
- explicit project/task/run relationships;
- structural change proposals and user approval;
- long-task progress, retry, cancellation, and review state;
- provenance from decisions and outputs back to Runs and sources;
- drift detection between UuMA state and Hermes Kanban.

The event stream is authoritative. Nodes and edges are current-state views. Updates use optimistic
revision checks. User-visible task splits, merges, or hierarchy changes wait for approval; temporary
steps internal to an accepted task do not. Corrections never rewrite event history.

Routing first checks hard graph constraints, then asks the Orchestrator to resolve semantic ambiguity.
This keeps the graph useful without pretending that a static taxonomy can understand every request.

Open future work includes graph query APIs, richer dependency conditions, historical graph views,
quality/evaluation edges, and optional migration to a dedicated graph backend if scale or traversal
requirements justify it.
