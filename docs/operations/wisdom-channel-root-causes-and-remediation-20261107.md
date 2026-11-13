# Wisdom discovery channels: verified causes and proposed remediation

Date: 2026-11-07 UTC+8. Scope: four user annotations on the onion research audit.
This turn inspects existing receipts and proposes a concrete repair. No production queue,
account, research state, service, source release or canonical knowledge was modified.

## 1. ChatGPT value and queue cause — confirmed

Authenticated GET of existing request cgpt_fa7bd6257ad74add81bc633f305ae55f returned
QUEUED, result=null, url=null, zero answer characters and zero citations. Created and updated
timestamps are identical. The authoritative workstation bridge owner, verified from the actual
PID's UUMA_CHATGPT_DATABASE_PATH, also records submitted=null and only one QUEUED event.
This is not a completed report lost during ingestion: this request has not been submitted by
the bridge to the browser.

Account main is enabled and READY and supports deep_research. The bridge heartbeat is healthy.
One older request, cgpt_85da342de4794c8f84856ed2ab77c2d5, is PAUSED with
EXTENSION_UNAVAILABLE, submitted=null, url=null and result=null. BridgeStore.claim excludes
an account whenever any request has PREFLIGHT, SENDING, RUNNING, PAUSED, NEEDS_REVIEW or
AWAITING_INPUT. This accounts for the blocked new request. No cancellation/resume was issued.

Production owner is .uuma-local/workstation-node-production-20261022/state/chatgpt.db.
The old AppData desktop database was not the active owner; an attempted read of that old path
reported a malformed image. It was not repaired, initialized or used to establish current state.

## 2. XHS values and asynchronous defect — confirmed

Existing xhs_search_status reads, without new searches:

| Job | Actual returned state | Values |
| --- | --- | --- |
| 048cc5409cd5106f8bd1e0eb | extension_offline error | 0 |
| 7cc3b793bf4ed6a05c9d5788 | success/completed | 5 links |
| 4dfd3e7471cc4749e06af2c0 | success/completed | 5 links |
| b2f37e3b9bc0af94b1547896, earlier independent check | success/completed | 3 links |

The actual connector is currently paired but offline. Cached completed job values remain
readable. The two sets of five links are not ten independently relevant scientific sources:
Chinese search returned some aeroponic leads plus unrelated greenhouse content, and English
search included nasal spray, video editing and agricultural drone nozzles. Descriptions were
empty. No post bodies, media, comments or OCR were fetched in this audit.

Local offline replay of the exact historical successful test's submission:
status=in_progress, stage=queued, job_id present. XhsMCPDiscoveryProvider.parse_result yields
in_progress=False, zero artifacts, although the same job later returned three links. The parser
recognizes queued/pending/running/etc. but omits in_progress and ignores stage for pending-state
classification. The planner then discards its pending ID because response.in_progress is false.
This proves the current local parser defect; preserve production version/hash verification before
publishing a fix. The historical different-job response is a distinct matching/concurrency issue.

Therefore the earlier zero-result usage ledger cannot establish that XHS returned no raw value.
It records zero admitted artifacts at the observed submission stage, not a final upstream result.

## 3. Proposed implementation sequence

1. Add observability without changing admission: expose actual provider status, age, result-present,
   queue-blocker ID/status/reason, submitted flag, last progress, next check and waiting reason.
   Status-query success must be WAITING rather than productive research SUCCESS. Maintain separate
   raw-result, admitted, ingested, evidence-supported and requirement-covered counts.
2. Restore the existing bridge chain with scoped semantic actions: verify Chrome extension/account
   availability and originating run; inspect the older paused blocker before action. Since it has
   no submission receipt, choose an explicit audited resume or cancellation of that exact obsolete
   request. Never bulk-clear account state or replay uncertain SENDING/NEEDS_REVIEW requests.
   Preserve and reuse the queued current ID; do not submit another equivalent request.
3. Fix asynchronous discovery parsing and transitions: accept provider in_progress plus queued/running
   stages; retain exact provider/job/query and durable polling deadlines; retrieve the same job's
   completed result once; deduplicate by note ID/canonical locator. Treat offline/login, pending,
   failed, empty and irrelevant as different outcomes. If polling fails ambiguously, preserve the
   pending ID and do not fall through to a duplicate submission.
4. Add no-progress handling: proposed checks at 30s, 60s, 120s, then at most every five minutes.
   After five minutes queued without progress, inspect/report the actual queue blocker. Persist
   WAITING_EXTERNAL/REQUIRES_ATTENTION and a wake deadline rather than recording a complete research
   cycle for each poll. A stalled route may release other authorized research routes to run while
   retaining the existing pending request. Time alone must never cancel or duplicate active Deep
   Research, override a human pause, raise a budget, or approve knowledge.
5. Repair research strategy: maintain requirement-level gaps for recovery duration, spray on/off
   cycle, nozzle/droplet/pressure, nutrient EC/pH/formulation and environmental/stage conditions.
   Distinguish direct Allium fistulosum aeroponic evidence, adjacent hydroponic/other-species evidence,
   and experimental hypotheses. Numeric settings from adjacent contexts cannot silently fill direct
   requirements. A clearly documented evidence gap is a valid interim output, not a fabricated answer.
6. Normalize overlapping questions by parent topic/requirements without deleting histories. Deduplicate
   provider+query+source digest across cycles; reformulate from the critic's missing requirement rather
   than cycling the same root prompt. Prefer short Chinese XHS keywords; use scientific English for
   academic databases and search full-text methods/supplements. Preserve original references and
   exact page/table positions. Community links remain leads until relevant content can be inspected.
7. Proposed no-novelty rule: after three cycles without a new relevant source/evidence/requirement
   change, change query/source class or enter an explained wait/review state. Do not treat this as
   permission to end all research, delete a gap, clear old counters or silently increase limits.

## 4. Acceptance criteria

- A pending XHS response with status=in_progress preserves the same ID and later consumes its
  completed values; offline and wrong-job results cannot become NO_MATCH or unrelated evidence.
- The two known completed five-link XHS receipts are recoverable without new keyword searches;
  irrelevant nasal-spray/video-editing cards are excluded with a recorded reason.
- Existing ChatGPT queued status exposes its actual paused blocker and does not claim generation.
  A later successful request must retain submitted receipt, canonical conversation URL, nonempty
  answer and located citations; API GET success alone does not satisfy this criterion.
- An unchanged provider response is not counted as new evidence or a new research success.
- Ambiguous polling errors and process restarts do not create another provider request.
- Similar queries and already-used documents do not repeatedly consume complete research cycles.
- Soil/pot recovery estimates cannot close an aeroponics requirement without an explicit valid
  applicability argument; unavailable direct evidence is reported honestly with a separate next step.
- Tests use fake providers/copies; production publication follows the component release runbook
  with verified hashes, affected consumers and rollback. No broad gateway restart by default.

Read-only evidence: private channel-values-20261107.txt and xhs-existing-receipts-20261107.txt
under .uuma-local/wisdom-critic; replay helper .tmp/wisdom_xhs_pending_replay_20261107.py.
