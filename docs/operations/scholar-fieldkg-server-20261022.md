# Scholar FieldKG server placement — 2026-10-22

Scholar's graph bridge now runs on **alandelone-server-001**, port8892, with
OpenSPG project **2 / ScholarFieldKG**. Scholar itself and its canonical RSTV4
catalog remain on the workstation. Wisdom retains project1 / Uuma; its complete
OpenSPG project configuration digest was checked unchanged after deployment.

The workstation's existing `http://127.0.0.1:8892` URL is an SSH local forward to
server loopback8892. The Scholar profile now explicitly records that URL; current
MCP processes already use the same default, so no shared gateway restart was needed.
The connector was added to the existing workstation startup manifest and started
hidden through its owned-process helper. Its SSH connection checks the known host,
fails on forwarding conflicts, and uses keepalives.

The complete Scholar readiness check also requires the workstation's loopback
**8887** to forward to server loopback8887. Its Worker reads the bridge's
`host_addr=http://127.0.0.1:8887`, then verifies the project, schema and an
intentionally absent graph identifier. Forwarding only8892 makes bridge health
pass while the actual specialist guard still rejects domain work. This omitted
connection was reproduced after the user's Telegram retry and then corrected.
`scholar_graph_probe_tunnel` now starts alongside the existing8892 forward in both
the persistent workstation manifest and the dedicated Scholar connector. Both
listeners bind loopback only and use known-host SSH verification. No new vendor
operation is exposed through MCP; this is transport for the existing internal check.

Server user services, both enabled for boot:

- `uuma-scholar-fieldkg.service`: original RSTV4 semantic bridge, schema/project
  isolation guard, CPU embedding readiness check, bounded model policy.
- `uuma-scholar-embedding.service`: actual BGE-M3 CPU ONNX embeddings, authenticated
  with a new server-local credential, bound only to the Docker bridge gateway8893.
  OpenSPG's project creation validates this real1024-dimensional provider. The
  FieldKG bridge also uses it, avoiding duplicate in-process model loading.

Runtime configuration and credential files are private under
`~/.local/share/uuma/production/scholar-fieldkg/`. Existing CPU model files and the
pinned KAG0.8 environment were reused. The graph uses separately qualified
ScholarFieldKG labels in the shared physical store; no SQLite database was shared
between machines or repurposed. No old graph/project was reset.

Running source is pinned at content ID
`a7da06b9710cc979fe461296a3270a8532fd55da839dbb73799a1ca4b5b1383a`,
containing184 files with a verified per-file SHA256 manifest, including the full
RSTV4 package initialization dependencies. Source files reside under
`~/.local/share/uuma/engine-sources/scholar-fieldkg/<content-id>/`.
The existing pinned UuMA source provides the CPU adapter and zero-retry policy.
Releases remain manual; service enablement does not update source automatically.

The retained local bootstrap now checks
`RSTV4/.rstv4-local/fieldkg/remote-owner.json` before making changes. It refuses to
replace this server-owned graph or kill its SSH listener. Start the existing
workstation connector instead of running the old local bootstrap.

## Operational verification

The actual `FieldKGKagClient` read back `ready: true`, namespaceScholarFieldKG,
project2, verified schema, CPU ONNX fp32 and zero retries /60-second model timeout
through workstation8892. Missing required retrieval/projection inputs returned422;
unauthenticated embedding access returned401. The local bootstrap rejected the
exact server-owner marker. Wisdom8891 remained ready on project1. New launcher
sources passed Ruff. These are deployment checks, not scientific acceptance.

No research extraction, generative model probe, projection drain, reindex or paused
research resume was invoked. OpenSPG project creation's actual CPU embedding check
was an infrastructure check. No shared Telegram receiver was restarted.

**Historical task-tracking error:** the15:15 Telegram exchange reported
`database disk image is malformed` during Direct Run registration. This graph
deployment did not repair that database. In the later22:28-22:37 exchange, the
specific observed blocker was graph preflight; the worker successfully recorded
a BLOCKED Run. Do not reuse the earlier database diagnosis as the explanation
for that newer graph failure or infer a database repair from it.

After adding8887, the unchanged `ensure_knowledge_graph('scholar', recover=False)`
passed all four requests: bridge health, project lookup, schema lookup and an
absent-identifier storage read returning an empty list. The real Worker MCP,
launched with the current Scholar profile's exact command and environment, also
returned `ready: true`, `graph: ScholarFieldKG`, `recovered: false` with recovery
requested. The exact installed guard's receipt parser accepted that response.
This repair changes transport only; no runtime code, model request, Telegram
message, process restart or existing Run/research state was changed.
Additional receipts: `.uuma-local/scholar-graph-preflight-repair-20261022/`.

Private evidence: `.uuma-local/scholar-fieldkg-cutover-20261022/` locally and the
same basename under server `~/.local/share/uuma/`, particularly source-receipt,
activation-receipt and final-verification JSON files. Source packaging, schema-cache,
legacy mock-vectorizer and PowerShell policy failures are retained in the session
journal and deployment context; no assertions were weakened. The mission gate
remains verification / pending_review.

## Rollback boundary

If rollback is needed, stop only the two new Scholar services and its owned SSH
forward, restore the exact saved Scholar/startup configuration bytes, and reconcile
any subsequent graph writes before changing ownership. Retain project2 and its
source manifests as evidence; do not delete graph data, modify Wisdom project1,
restore a damaged control DB, or resume paused research as part of rollback.


## Workstation connector supervision (2026-10-26)

A later complete preflight found an exited8892 SSH forward while both server services remained active. Restarting only the existing scholar_fieldkg_tunnel restored the original project/schema/storage preflight;8887 was retained. A login-only launcher does not continuously recover disconnected forwards.

The scoped checker scripts/check-scholar-graph-connector.py admits only the existing two exact loopback SSH commands, server owner marker, unchanged configuration and unchanged launcher hashes. It refuses foreign listeners without stopping them and never initializes a database, runs a model, restarts a server or touches a Bot receiver. Watch mode checks every60seconds and holds one existing-style process lock for its own supervisor root, distinct from the connector startup lock. Both expected recovery and rejection paths have9focused software tests; actual hidden watch execution passed two cycles and rejected a duplicate owner. No healthy live tunnel was forced down for testing.

Windows Task Scheduler registration was attempted with a concrete source-pinned preview and failed with Access denied. It is not installed and must not be reported as complete. The interim active entry is the current user Startup file UuMA Scholar Graph Connector.vbs, which starts a hidden pythonw guardian from a content-addressed directory under .uuma-local/scholar-graph-connector-runtime. The guardian preserves existing SSH ownership, checks both endpoints every60seconds and can restore disconnected forwards through the existing scoped launcher. It has no scheduled-service restart guarantee if the guardian itself exits; login startup and a tested live guardian are distinct from Task Scheduler supervision.

Private evidence is scholar-catalog-implementation-20261023/graph-connector-supervision-v1 (denied task preview/logs) and graph-connector-supervision-v2 (actual Startup path/hash, PID/birth/argv, two cycles, duplicate rejection and rollback). Before stopping the guardian, verify that receipt identity; remove only its own Startup entry if requested. Preserve existing SSH forwards. A future launcher/configuration change requires a new pinned supervision preview.

## Current readback — 2026-10-28

At 12:59 UTC / 20:59 Malaysia time, the unchanged full
`ensure_knowledge_graph('scholar', recover=False)` check returned
`ready: true`, `graph: ScholarFieldKG`, `recovered: false`. This checks the bridge,
project, schema and an actual storage read, rather than bridge health alone.
The existing remote owner remains alandelone-server-001, project 2, while the
canonical Catalog remains workstation-owned.

Both loopback ports 8892 and 8887 have live SSH listeners with the expected
forward destinations and server alias. A read-only server service query returned
active for both FieldKG and embedding services. The current Windows
`UuMA Scholar Graph Connector` scheduled task exists and is Running; this later
observation supersedes the October 26 statement that no such task was installed.
No tunnel, server service, receiver, model job or Catalog record was restarted or
changed for this check. Receipt: private implementation `graph-readiness-v148.json`.
