# Scholar Catalog One-shot Run-now Mode — 20261111

**Status: published and verified on November 11 at 15:32 Malaysia time.** The user explicitly approved publication. Both Catalog Web and the dedicated Reading task are Running on the fixed selections below. Default remains the normal 00:00–08:00 Asia/Kuala_Lumpur schedule; no production RUN_NOW request was submitted during publication.

Live readback verified the page controls, exact JavaScript digest and `GET /api/catalog/understanding/reading/mode` returning NIGHT with no active batch. All 130 business-table row counts and content fingerprints match the consistent pre-publication backup. Reading retains its existing logon/daily-midnight triggers and the November 12 00:00 next start. No schema change, database restore, scientific approval or additional model request occurred.

The user requested a way to finish queued reading immediately instead of waiting for night, and explicitly chose **all eligible pending tasks** as the default scope.

## Resulting behavior

- Catalog has **立即运行全部待办** and **恢复夜间运行** controls. The same operation is available to Scholar through `set_catalog_reading_execution_mode`, with `RUN_NOW` or `NIGHT`, a durable request ID and reason.
- RUN_NOW snapshots the existing eligible global Catalog source-parsing and initial-reading jobs. A parsed source's exact initial-reading child stays in that batch. Future imports and new source versions do not silently join it. It never creates a deep-reading request or reopens a held failure.
- The existing reader, leases, source validation, provider backoff and parse/reading fairness remain in control. Separate explicit individual requests keep priority. Pause, stop and quarantine remain effective; missing or modified PDFs fail normal source validation.
- The batch returns to NIGHT automatically after completion or explicit holds. The return is recorded in the existing append-only journal, so a later retry cannot silently reactivate a drained batch.
- NIGHT returns pending batch work to the normal schedule. In-flight parsing can finish its current safe step; a new model checkpoint observes the changed mode. Saved successful inference remains reusable.
- No schema migration or new scheduler is introduced. Existing request/event tables retain the source-bound batch receipt, cancellation and automatic return. Manual-priority flags, scientific review state and retry allowances are not reassigned by a mode switch.

## Published scope and identities

Only workstation Catalog Web and the dedicated Catalog Reading task are affected. The native Catalog MCP entrypoint uses the Web/active manifest. The shared Hermes gateway and other specialist services are outside this publication.

| Component | Previous selection | Published selection | Manifest SHA-256 |
| --- | --- | --- | --- |
| Reading | `catalog-reading-repair-20261111-ebfc1965c357` | `catalog-run-now-reading-20261111-f131c31fbd13` | `8cd6eca82a8ae136984099d9f62dcc4ed58b595813966b9ea42b1833681a69de` |
| Web / native MCP | `catalog-2342b790da44` | `catalog-run-now-web-20261111-947d6ef9acc2` | `6add1a4da2a21bc1516e222eda413ba414b9be282c252b25c5fc6c7c2eacd3f7` |

The Reading candidate pins 457 source/parser/test files; Web pins 448. Each is based on its actual selected engine. The Web candidate preserves its existing worker implementation; only the separately selected Reading engine executes the new queue admission. Unrelated development changes to partial-candidate routes and portable PDF resolution were excluded from both packages. The latter exposed a pre-existing `sqlite3.Row.get` failure in a broader development-source test; the unchanged selected PDF handler and the actual fixed candidate pass the same affected source tests. No assertion was weakened or unrelated production source change bundled to mask it.

Existing schema version 21, data/resource owner, interpreter, base binary and dependency pins remain. Runtime data stays in `C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db`. Existing night/logon triggers remain unchanged by this feature. Source archive hashes and exact changed-file lists are in the [preparation receipt](../../.uuma-local/scholar-catalog-implementation-20261023/run-now-mode-20261111-v4/preparation.json).

## Validation

- 60 tests passed against the actual Reading candidate: one-shot scope/idempotency, model checkpoint/cancellation, physical source changes, automatic return, real software-parser-to-initial completion, individual priority, retained backoff, source/review behavior, existing policy/fairness, overview and MCP contracts.
- Two Web-candidate tests passed for the same protected HTTP and native-tool mode contract.
- Three frontend tests passed for both buttons, repeated uncertain submission using the identical request ID, and an old poll being unable to overwrite a newer successful change.
- Scoped lint passes. Both complete fixed candidates pass the real launcher's read-only source/runtime/owner admission. Original content and all 209 retained contracts replay exactly on the Reading candidate; purpose scope passes. No model calls or production mode requests were made.
- An existing Pydantic forward-reference warning remains in MCP test setup.

## Publication and recovery steps

Before selection, recheck both original manifest bytes and all candidate source hashes. Preserve the actual task definitions, process identities and a consistent SQLite backup. Wait for a safe idle reader boundary; an unknown live reading/source lease or foreground request blocks a restart. The previously diagnosed November 6 expired source lease may remain unchanged for normal reclaim. Stop only the two owned Catalog task/process trees, atomically switch the corresponding manifests, and restart them. Confirm their actual import roots, Web/asset/HTTP readback, one logical reader and unchanged night trigger.

Do not submit RUN_NOW on the production queue merely to demonstrate the feature. Publication leaves NIGHT as the default; a later explicit button/tool action admits the actual batch. The interface and mode behavior have been tested with isolated data and fake inference.

Rollback restores the two retained manifest selections at an idle checkpoint and restarts only these components. Never restore an old database over later work. A mode-change receipt remains in the owner history; if any real run-now batch was started after publication, first return it to NIGHT through the native control and preserve all new jobs/results before considering an engine reversal.

The repository release rule distinguishes implementation from publication: [agent-development-and-release.md, section 5B](agent-development-and-release.md) states “用户要求开发不自动等于要求上线”. The prepared package and passing validation make publication review concrete. No mission gate or project-wide completion is inferred.

The user subsequently selected **现在发布** for this exact scope. The first publication attempt stopped before changing services because its idle guard incorrectly expected a loopback-only listener. A read-only reconciliation confirmed that the unchanged baseline actually listened on `0.0.0.0:8875`, with only the exact same-process reciprocal asyncio loopback socket pair and no HTTP/external connection. The successor matched that existing listener and retained all other idle, owner, lease, source and socket checks. No network binding was changed. The original aborted receipt and the successful successor are retained separately.

- [Successful publication and live readback](../../.uuma-local/scholar-catalog-implementation-20261023/run-now-mode-20261111-v4/publication-web-binding-reconciled/receipt.json), including before/after fingerprints for all 130 business tables, old task definitions, process identities, selected engines and live mode/asset readback.
- [Original idle-check abort](../../.uuma-local/scholar-catalog-implementation-20261023/run-now-mode-20261111-v4/publication/receipt.json) and [unchanged-listener reconciliation](../../.uuma-local/scholar-catalog-implementation-20261023/run-now-mode-20261111-v4/publication/web-boundary-reconciliation.json).
- Consistent SQLite backup SHA-256: `c7b067e0df52b4523194ffa53727def846b7d27105cd7e206f89039af6527519`. Old Reading/Web selections and exported task definitions are beside the successful receipt. Do not restore this backup over subsequent user work.

User entry: refresh Catalog and use **立即运行全部待办** to start the explicit one-shot batch. **恢复夜间运行** returns pending work to normal scheduling at the next safe checkpoint. Successful publication does not mean that the queued papers have already been read.

Private validation artifacts: `.uuma-local/scholar-catalog-implementation-20261023/run-now-mode-20261111-v4/`, including `reading-tests.log`, `web-tests.log`, both admission logs and `strict-replay.json`.
