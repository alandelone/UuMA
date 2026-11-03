# Wisdom research critic deployment — 2026-10-22

The user approved Deep Research → academic → general web → supplemental discovery
and requested an independent critic using `complex` at the supplied model gateway.
The implementation is active on alandelone-server-001.

Component: `e98cbd7794c5dd4b5e045bbe699e13b256dbd8a71307dbb4558e9edf5352d206`.
The source lives under the server's `components/wisdom-research/` directory. It is
a copy of the existing Wisdom source plus seven selected changed/new modules; 136
other source files were checked byte-for-byte. One baseline variance was reviewed:
production had moved the identical `control_client` import within orbit_runner;
all other bytes matched HEAD and the target retains the import once in sorted order.
This component ID is not a Git commit or a claim that the working tree was pushed.
The source-file baseline was verified against commit
`67516d29e8a94ab002a9e00fa6a4737ee45d0ccd`; the selected uncommitted changes are
identified by the component's exact file hashes. No commit or push was performed.

Wisdom's Knowledge MCP environment and its Orbit service point to the component.
The configured critic is an isolated, tool-free delegate using model `complex`;
the real gateway reports `gemini-4-argon`. The live worker startup confirms the
critic configuration. The profile includes the new coverage-critic skill and source
order. [Contract and configuration](../architecture/wisdom-research-critic.md).

Validation:

- 85 focused tests passed, including source order, critic evidence validation,
  malformed/truncated results, budget/time failures, authenticated MCP access,
  per-question tier persistence and async request continuation after runner restart.
- Ruff passed for all changed runtime modules and focused test files. The test run
  retained one existing Starlette TestClient deprecation warning.
- Real API checks returned CONTINUE for a missing mandatory parameter and SUFFICIENT
  for fully covered software-fixture requirements. A real server-side critic call
  also passed. These fixtures made no production knowledge claims or writes.
- The first live test scoped the question as a closed-source document audit, where
  reporting an absent interval was reasonably considered complete. That failed
  test/response was preserved. The user-purpose contract was clarified for required
  numerical settings, rather than weakening the missing-parameter assertion.
- Before loading profile changes, the gateway reported zero active Agents/work.
  After reloading, all five specialist Telegram receivers were connected. The live
  Wisdom Knowledge MCP process loaded the new source path.
- All five existing FAILED, STOPPED and BUDGET_EXHAUSTED Orbits retained their status.
  No task was resumed, no canonical claim was approved, and no graph rebuild was run.

The shared gateway reload used repeated zero-active checks; it did not separately
pause admission. All existing receivers reconnected and no active work was observed.
The development/publishing runbook added during this work requires an explicit
admission gate for future shared-gateway maintenance; retain that requirement.

## Search MCP inventory

The actual server Wisdom profile contains working MCP bindings for:

| Binding | Confirmed tools/capability |
| --- | --- |
| `xhs` | Keyword links/status, browser status, link-to-text/status, staged post processing |
| `chatgpt-bridge` | `chatgpt_request`, `chatgpt_continue`, `chatgpt_status`, `chatgpt_result` |
| `wisdom-knowledge` | `knowledge_search`, `knowledge_answer`, durable Orbit controls |
| `notion_kb` | `search_pages`, `get_sync_status` |

The XHS relay failure was caused by inherited UuMA dependency paths loading a
Pydantic binary incompatible with the external Conda runtime. The external child
now clears PYTHONPATH/PYTHONHOME/VIRTUAL_ENV. Only the verified idle workstation MCP
node was restarted for that repair. A server-to-workstation tool listing then passed.

XHS initially reported paired=true and browser status=offline. After the operator
opened the original Chrome profile, the same server Wisdom MCP binding reported
connected. A new bounded keyword search for `青葱 气雾培` completed successfully with
three note links (job `b2f37e3b9bc0af94b1547896`); its request and result query match.
The receipt is under the server's `wisdom-xhs-followup-20261022/` directory and the
sanitized local follow-up receipt. Only keyword links/status were called; note body,
media and comment extraction were not triggered. The search/status provider is
registered in Orbit's fourth tier. Search-card snippets remain leads;
automatic media/comment extraction was not enabled. Signed browsing tokens are not
stored as canonical locators. Notion is an Agent MCP capability, not an added automatic
Orbit provider in this change.

Private receipts, exact pre-change configuration backups, failed attempts, live
critic responses and final runtime verification are retained under
`.uuma-local/wisdom-critic/` and the server component's `operator-backup/` directory.
Mission remains verification/pending_review; this deployment does not approve that gate.

Rollback restores the backed-up profile/env references after waiting for active
cycles. It does not restore an old database over new business writes. The original
fixed source remains intact, and all non-target source files in the component match it.
