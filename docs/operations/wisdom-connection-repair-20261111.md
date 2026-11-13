# Wisdom connection repair — ChatGPT search round trip verified

2026-11-11 UTC+8. User authorized connecting the discovery channels sequentially, then chose
Chrome profile alanworkliaolo@gmail.com and confirmed personally loading the existing extension.

## Live result: first search round trip completed

The same diagnostic request `cgpt_dcef6cd943f246d5b8a76eceb390f5ab` now has status
`COMPLETED`, one submitted receipt, a nonempty answer and three citation links. Its conversation is
https://chatgpt.com/c/6af3d980-9658-83ec-97f0-ed1a55e6b525 . The submitted timestamp is
1794365824.0088582 and completed timestamp is 1794369523.2159488. Both the authenticated human
state and scoped Wisdom request API are checked separately. No duplicate prompt was submitted.

Two observed upstream markup changes caused the failure: the editor now uses
`form[data-chatgpt-composer] [data-composer-markdown][contenteditable="true"][role="textbox"]`
instead of the legacy prompt ID; message units now use `data-chatgpt-search-unit-key` and the
assistant body uses `data-markdown-text-style="assistant-message"`. The extension now handles
both versions. It rejects ambiguous editors, checks the conversation URL and last user request
marker, and reads only the assistant body. Eight focused Node tests passed, including wrong
conversation, later unrelated prompts, missing/streaming answers and legacy markup.

Loaded extension version 0.1.6 in Profile 9 with unchanged permissions. After extension reload,
refreshing only the ChatGPT tab left the old dashboard content script disconnected; observation
timed out as EXTENSION_UNAVAILABLE. Refreshed the existing dashboard, confirmed connected, then
resumed observation only. The submitted request was never returned to the send queue. This
recovery does not establish unattended extension restart reliability.

The answer explicitly reports insufficient direct recovery-duration evidence; its suggested
7–14 day observation window is an unverified working hypothesis. These returned links and advice
are not accepted scientific knowledge, and their content has not been independently verified here.
Ordinary search transport is verified; Deep Research and the old queued requests are still open.
The earlier chronology below remains historical evidence and is superseded by this result.

## XHS recovery checkpoint

Read the same completed jobs through the deployed Wisdom MCP binding on November 11:
`7cc3b793bf4ed6a05c9d5788` and `4dfd3e7471cc4749e06af2c0` each returned five links;
`b2f37e3b9bc0af94b1547896` returned three. Current parsing preserves the requested job identity,
canonicalizes links and stores them as discovery leads in private recovery receipts. They have not
been ingested as accepted knowledge. The nasal-spray and video-background-removal cards are
irrelevant to the research question; an untitled card remains unreviewed rather than assumed relevant.

With explicit user approval, installed the existing `xhs_chrome_extension` version 0.2.0 in Profile 9.
The service was offline and still paired to the same extension identity without credentials in the
new profile. Verified its current job was completed, backed up its JSON state, then used its existing
authenticated same-extension unpair flow to rotate pairing and paired the new Profile 9. The local
popup and the server-side native MCP now both report connected. Historical jobs were preserved.

Submitted one bounded three-link connectivity search with a durable pre-submit receipt, job
`0453098b2177258888fef3f4`. It returned `needs_login`; this is not a zero-result success.
User login is pending in the extension-created Profile 9 tab. Do not create another search.
The original job may continue within its login wait window; after a terminal timeout, inspect its
state before choosing an explicit recorded retry. No note media, OCR or extraction was requested.

Production initially used the old three discovery/planner modules. Prepared a separate candidate at
`/home/alandelone/.local/share/uuma/components/wisdom-channel-recovery/967cdfcfb9c111f2483b39b5330d6ba34271ed54035be5a474b0312c56ed2e53`.
It copies the current quota overlay, changes only `orbit_mcp_discovery.py`, `orbit_discovery.py`
and `orbit_planner.py`, and retains the previous fallback paths. The candidate passed 27 focused
tests on the server; three bridge-account reassignment/queue tests are deliberately outside this
worker-only package. The first package and a follow-up login-state correction are now applied;
the final component is d388b57d2cb800f44bd244b1a39a8d9edc3ac3b62748d60a507bc42a8e0d4d47,
with 29 focused server tests passed. Only the idle Wisdom Orbit worker restarted, with 19,444
cycle records preserved and consistent backups. Its actual source environment and independent
native-provider readbacks passed. See wisdom-channel-worker-release-20261111.md for exact receipts.

Reviewed recovered titles separately: 13 raw links, 11 unique; three potential leads, four adjacent
contexts, two irrelevant results excluded and two untitled/unreviewed. Accepted scientific evidence
remains zero. This title review is a recovery artifact, not an automated relevance-filter release.
XHS login/new-search completion, automatic result ingestion into the original research, durable
polling backoff, no-novelty strategy and full UI progress work remain open. The old ChatGPT Deep
Research queue and new-profile Deep Research availability are also unresolved.

## Latest XHS recovery (supersedes the earlier login-pending checkpoint)

The user logged in to Rednote in Profile 9; login was observed in the browser. The original
three-link diagnostic job `0453098b2177258888fef3f4` timed out during its first login wait.
Connector 0.2.1 now supports an authenticated, exact-job resume with query/attempt fences and
a durable idempotency key. The failed receipt is retained in recovery_history. Seven connector
unit tests and Node syntax checks passed. Only the idle local XHS bridge was restarted after
source/data backups; all historical jobs were deep-equal across that restart.

Resumed this same job once with `profile9-login-recovery-20261111-v1`, attempt 1. It completed
successfully and returned three links (two titled leads and one untitled lead). No second search
job was created. These are recovered leads, not accepted scientific evidence; automatic ingestion
into the original research has not been certified. Do not ask the user to log in again without
new evidence. Exact receipts are private under `.uuma-local/wisdom-connect-20261111`.

ChatGPT ordinary search remains verified at 623 answer characters and three citations. Deep
Research and unattended extension availability remain separate unresolved checks. See
`wisdom-external-wait-20261111.md` for the subsequent scheduler correction.

## Historical live changes at the first checkpoint

- Matched the chosen address to Chrome Profile 9 using local Chrome profile metadata.
- Created scoped bridge account `wisdom-work`, Personal workspace, bound to Profile 9. Kept
  existing main account, historical requests and other Agent routes intact.
- Opened the configured local bridge dashboard via its existing authenticated API. The original
  Profile 10 had no UuMA extension; the user's Profile 9 now has the original unpacked extension.
- Extension connection became true. Native browser verification completed READY, confirmed the
  chosen identity and reported chat/search capabilities. Deep Research is not verified.
- Set only Wisdom's future account route to wisdom-work. Submitted exactly one idempotent
  search-only connection check using the existing authorized Wisdom run and public onion question.
  Request: cgpt_dcef6cd943f246d5b8a76eceb390f5ab. Idempotency key:
  wisdom-profile9-search-20261111-v1.
- The request reached browser preflight and became PAUSED / COMPOSER_UNAVAILABLE. It has no
  submitted receipt, URL or answer. Do not call the return chain complete or submit another copy.
- Original Deep Research requests remain on main with their old IDs; no old request was cancelled,
  moved, blindly resumed or approved. Other Agents' bindings are preserved.

The first native search submission was correctly rejected by the existing binding guard because
the explicit target account differed from Wisdom's route. Applied the user-requested route through
the authenticated human route API, then reused the exact idempotency key and prompt; only the
successful admission created a request. No permission guard was bypassed.

## Development repairs prepared, not deployed

- chatgpt_bridge.py: queued status exposes the account's blocking state, with other Agent blocker
  details redacted; human-directed unsubmitted request reassignment preserves ID/payload/history
  and validates run, destination readiness and mode. This new operation has not been used live.
- chatgpt_server.py: human-authenticated/CSRF-protected endpoint for that reassignment.
- orbit_discovery.py: explicit WAITING and FAILED outcomes; failed existing-request reads preserve
  the pending ID and never fall through into another POST; human waits retain the request.
- orbit_planner.py: pending waits are distinct from productive success; preserves interrupted or
  human-blocked pending IDs and provides honest waiting text.
- orbit_mcp_discovery.py: recognizes actual in_progress/queued response shape, checks the exact
  pending job ID, deduplicates completed links and preserves offline/error distinctions.
- New test_wisdom_connection_recovery.py covers provider failures, exact asynchronous responses,
  queue visibility, request migration restrictions and Agent privacy.

Focused verification: 71 passed across the new tests and existing bridge, migrated-credential,
planner and XHS suites; scoped Ruff and diff whitespace check passed. Existing third-party
Starlette warning remains. First run retained 69 pass / 2 fail: corrected waiting next_step being
overwritten and gave the second queued fixture its own logical thread, preserving production
thread-exclusivity and original assertions. No full-suite or production deployment claim.

No server worker/gateway restart, schema change, knowledge approval, new XHS search, media
extraction, commit or push. Backups and operation receipts are private under
.uuma-local/wisdom-connect-20261111.

## Earlier blocker and remaining work

The earlier next step was to observe a normal, logged-in ChatGPT new conversation with a visible editable composer in
the chosen Profile 9. Computer Use ended because it could not confidently determine the current
browser URL; no further Computer Use input was issued after that gate. Ask the user to leave that
normal chat page visible, then resume only the same demonstrably unsent test request when a safe
observation is available. Obtain actual answer/citation receipts before calling the connection
working. Diagnose selectors against observed UI; do not weaken identity checks or guess success.

After the first return chain works, continue the server XHS adapter rollout and exact old-job result
recovery, then durable polling backoff, other-frontier progress, per-requirement novelty and UI
counts. These later portions remain incomplete. Prepare component-specific release previews
before publication; preserve the mission verification/pending_review boundary.
