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

**The separate task-tracking failure is still unresolved:** the latest readable
Scholar Telegram exchange reported `database disk image is malformed` while
registering a Direct Run. The inspected worker still targets retained local
control state. Graph deployment does not repair that database or certify that
Scholar can pass its task-registration guard. A separate control-transport repair
must preserve the authoritative server state and the retained damaged DB.

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
