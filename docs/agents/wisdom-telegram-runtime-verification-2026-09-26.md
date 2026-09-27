# Wisdom-Oldman Telegram runtime verification — 2026-09-26

## Observed failure

The 09:01–09:14 Telegram conversation about scallion aeroponics produced direct model
answers with zero model tool turns. The 09:04 answer specified a 3–7 MPa impingement nozzle;
the 09:06 answer specified a 60–100 PSI (0.41–0.69 MPa) pump. Neither answer supplied
traceable agronomy evidence or a new topic-document version. The durable scallion Orbit was
still QUEUED and had no cycle. The deployed Hermes guard was enabled, but its read-only
`intent=auto` preflight set `domain_checked`, which allowed a model-only technical reply.
The user's `ok` was absent from the guard's tracked topic-consent vocabulary.

## Changes and evidence

- Clear research requests now invoke `knowledge_question_preflight(intent=research)` before
  the model reply. An `auto` intake that still needs intent resolution cannot authorize a
  research answer. The output guard uses the preflight's grounded answer, document link, and
  actual Orbit state instead of allowing unsourced model text to replace it.
- Tracked proposals accept a later `ok` as consent for precisely the proposed question.
  A bare `ok` with no tracked proposal cannot create a topic.
- A QUEUED Orbit now requests a detached background runner after durable publication. The
  installed scheduled task has a logon trigger for recovery; the runner exits after an idle
  timeout. A wake request is reported as requested, not as proof of active research.
- Status questions now read the durable global Orbit list across chat sessions. A live local
  Hermes query first reproduced the false "no active topic" answer, then after the fix
  reported the active scallion Orbit and its document link.
- Discovery drops obvious off-topic search hits before ingestion. Canonical citations must
  match the question and its named subject before they can ground an answer. Chinese web
  search was added, and provider requests now count toward the Orbit search budget.
- Downloaded pages are checked again against their actual title before canonical persistence;
  a misleading search title or URL cannot by itself admit a page. Direct crop-and-method hits
  are searched before more general technique sources. A read-only live search found university
  aeroponics sources and a crop-specific result; it did not mutate the knowledge database.
- First answers can read the existing graph without waiting for every projection event;
  a stale projection caps a strong/sufficient answer at provisional. The background runner
  still performs explicit projection sync before final publication.
- Runner process management now recognizes both Windows backslash and forward-slash profile
  arguments, so pause/stop actually terminates a detached runner.
- Hermes now forwards its actual Telegram chat and thread route to the pre-LLM hook. The
  existing Orbit's route was repaired from the matching local Hermes session record without
  creating a new topic or resetting its budget. A missing Telegram chat ID no longer produces
  a send target or a newly queued digest.
- A version-2 publication incorrectly labelled uncited aeroponics material as answer sources.
  The publisher now separates answer citations from research-in-progress material, and version
  3 records the correction reason. Version 4 preserved this distinction. The old versions
  remain inspectable in the append-only history.
- The latest KAG bridge health probe passed, but an actual SIMPLE retrieval timed out after
  90 seconds. The runner now retries a degraded graph answer with a five-minute delay and
  marks the cycle blocked only after three attempts. It never publishes a text-only fallback
  as a graph-grounded answer.
- The second live graph attempt also timed out. The background runner now permits up to 300
  seconds for SIMPLE KAG retrieval, which includes model summarization; direct question
  handling retains the shorter default. The runner was restarted while the cycle was in RETRY,
  preserving that cycle and its scheduled third attempt. Attempt 3 was claimed automatically;
  success of the longer call is pending.
- The read-only topic page now shows the live Orbit status separately from the versioned
  publication state. The installed view service was restarted, and the existing topic page
  returned HTTP 200 with the live ACTIVE banner after the restart.
- The existing scallion Orbit was paused after off-topic source records appeared. Its history
  was retained. After the relevance fix, it was resumed and a new cycle was claimed. That cycle
  skipped the prior unrelated hits and ingested a relevant aeroponics equipment study. Further
  cycles added research-in-progress material, but no crop-specific answer has passed the
  citation check. The same Orbit was resumed after the transient graph retry fix.

## Historical checkpoint before the 2026-09-27 repair

- **Passed:** 293 tests and five subtests, repository lint and diff check. The local topic page
  returned HTTP 200 with its overview anchor, pending-source heading and correction summary.
  Hermes route forwarding passed an executable smoke check; its added standalone test was not
  run because the Hermes environment lacks pytest.
- **Observed:** the existing topic ID remained stable. Document versions 2, 3 and 4 were
  published; version 3 explicitly corrected version 2. The latest document still says no
  relevant traceable answer is available. The correction digest and the graph-blocked digest
  were each sent by Hermes to the repaired Telegram route in one attempt. Command success is
  evidence of dispatch, not proof that the user read the messages. The Orbit is ACTIVE and a
  new cycle reached RETRY after the actual graph call timed out. The background runner then
  claimed attempt 2 without another user message. The Orbit remains ACTIVE. The installed page
  shows that live state without rewriting the version-4 publication.
- **Pending:** crop-specific, cited findings and a multi-chapter document; a first-useful-answer
  digest; a fresh incoming Telegram question exercising the deployed host hook and guard;
  completion of the current cycle and its graph retry path. The full scenario is not accepted.
- **Known limitation:** four older off-topic sources and an incorrect early document version
  remain in append-only history. Their errors are visible and newer publication excludes them
  from answer citations. The KAG bridge can report healthy while actual retrieval times out;
  after bounded retries the task will accurately report BLOCKED again if retrieval stays down.
  The Hermes hook route change also lives in the local Hermes checkout and needs to be retained
  when that installation is updated.

The live knowledge database and deployed Hermes configuration/plugin were backed up under
`.uuma-local/backups/wisdom-live-20260926-092523` before runner and gateway verification.

## Current verification — 2026-09-27

The KAG server's built-in answer summarization was the source of the repeated timeout: retrieval
without that summary returned graph/vector context, while full SIMPLE answering repeatedly hung.
The deployed answer path now retrieves KAG context and synthesizes a bounded answer from canonical,
located source excerpts. It preserves citation keys, conditions, and the candidate-review boundary.
A fresh-process `knowledge_answer` call returned `runtime_status=KAG`, two citations, and a Chinese
scallion answer after the Hermes gateway restart. This verifies the local MCP answer path, not a
new incoming Telegram message.

The original topic `topic_07a8574b5d504d34a5483407c2a88400` and Orbit
`orbit_9ac4d099873b82f8f5a730cf07792419` were reused throughout. No new live topic was
created. The first grounded answer, conclusion corrections, a completion notice, and a later
pause notice were recorded as `SENT` to the existing Telegram route. Dispatch was observed;
recipient reading was not. The earlier `COMPLETED` state was incorrect: source count had been
mistaken for answer coverage even though the answer said aeroponic settings were unknown. The
completion rule no longer upgrades a provisional answer based solely on two located citations.
Two specific branches for aeroponic equipment/nutrients and division-transplant recovery were
added under the same topic, and the falsely filled equipment gap was reopened through audited
events. The DEEP budget and past cycles were retained. Both gaps remain `OPEN`; after further
discovery found no additional relevant, retrievable source, the Orbit moved to `PAUSED` and sent
its pause digest. The system does not claim the parameters or recovery protocol are established.

Document version 26 has eight topic/question sections. The two focused chapters were revised to
state directly what is supported, what remains unknown, and why hydroponic or soil findings cannot
be used as aeroponic settings. Corrections have version reasons and old versions remain available.
The local topic page returned HTTP 200; overview and both focused chapter anchors were present,
the page showed unresolved questions, and a request without its read-only token was rejected.
The graph endpoint returned 32 nodes and 31 edges during the final page check. The append-only
knowledge event chain validated. The latest document had no potato source. The live database was
backed up again before reopening the focused gaps to
`AppData/Local/UuMA/wisdom-before-scallion-gap-repair-20260927T031521.db`.

Full regression: **303 tests and five subtests passed**; Ruff and `git diff --check` passed.
The gateway restarted and reported a running process. The runner was restarted after the code
change, recovered an expired in-progress cycle, and processed the focused branch without a new
user message.
Read-only inspection of the actual Telegram Desktop conversation showed the 11:40 pause digest
and 11:41 focused-chapter correction digest as received messages with the topic link. The
future no-source pause explanation was also localized into Chinese.

Remaining acceptance limits: a fresh *incoming* Telegram question through the deployed hook
has not been observed, so cross-chat answer delivery is not marked passed. The KAG projection
outbox still has lag (149 pending/running jobs at the final read); the canonical topic graph and
read-only graph view are available, but full projection synchronization is not claimed. The
unavailable NTU thesis full text remains an evidence gap; only its official public abstract was
verified. The last research pause reflects source availability, not budget exhaustion or user
permission to invent a new topic.

## Cross-chat question retest — 2026-09-27

A user-authorized incoming Telegram message asked “青葱分株后缓苗要多久？” and requested
an existing-knowledge answer with a chapter link, explicitly forbidding a new topic.
The deployed bot instead proposed a new topic. It did not create one. Local inspection
showed that the entire message, including answer-format instructions, scored 0.1895
against the established scallion topic; the actual question alone scored 0.28 and
cleared the existing 0.26 threshold. The route had no prior topic binding, so this
was a cross-chat matching failure rather than a continuation failure.

Research-question intake now strips a trailing answer-format instruction after an
interrogative boundary before matching, recording, KAG reasoning and citation checks.
The exact Telegram wording is covered by a regression test: it reuses the prior topic
from a different chat without approval, stores only the domain question, and leaves
an unrelated question pending topic-creation approval. The gateway was restarted.
Full regression: **304 tests and five subtests passed**; Ruff passed.

A fresh local `knowledge_question_preflight(intent=research)` against the live database
returned the original topic and Orbit IDs, with no increase in topic count or budget
reset. It published document version 27 and a specific question chapter. The answer
states that the reviewed sources do not establish a duration for post-division
recovery, rather than inventing a number. The read-only local chapter page returned
HTTP 200, contained its stable `question-8add182e654a` anchor, and showed five
canonical cited sources. The Orbit remains `PAUSED` because its open evidence gaps
remain unresolved. Before this local mutation, SQLite backup
`AppData/Local/UuMA/wisdom-before-crosschat-20260927T041923Z.db` was taken.

The first local call found KAG unavailable and raised `BLOCKED` after the related
question had been persisted but before a document version was published. Managed
graph recovery returned `ready=True`, then the same preflight completed. The deployed
Hermes guard performs that recovery before its domain preflight. A second **incoming
Telegram** message after the fix is still needed to observe the final bot reply and
chapter link; local MCP success is not counted as Telegram delivery.

## Pause reason and branch coverage repair — 2026-09-27

The live scallion Orbit was `PAUSED` while its budget still had substantial room:
1,276 of 21,600 active seconds, 10 of 100 sources, 22,049 of 1,000,000 estimated model
tokens, and 61 of 250 search queries had been used. The original audited pause event
carried the reason "No additional relevant public source was found; current findings
and gaps are preserved." Its projected Orbit and research-run records nevertheless had
`stop_reason=null`. `QuestionOrbitService.transition` had incorrectly treated `PAUSED` as
a running state and cleared the reason. The transition now retains pause and stop
reasons, and an audited, idempotent repair restored this live reason from the original
event. The topic page labels it `原因：`. The repaired event chain validates.

The runner also paused the entire topic after one provisional branch yielded no new
source, even though three high-priority frontier questions remained open. Frontier
items now track audited no-source attempts. A no-source result moves the runner to an
untried open question; the topic pauses for source saturation only after every open
question has been checked. Budget exhaustion still takes precedence, and a user pause
or stop remains a separate explicit state. This change does not approve candidate
knowledge or create a topic.

An online SQLite backup was taken before the live repair at
`AppData/Local/UuMA/wisdom.db.backup-20260927-105048` (integrity check `ok`). The
database file is hard-linked to the Codex LocalCache data path used by the scheduled
runner and document view. The document view was restarted and returned HTTP 200 for
the existing topic and topic list; the specific page showed both the pause reason and
the link back to all topics. Ruff passed; the full suite passed with **316 tests and
five subtests**. The Orbit runner was restarted with the updated code. The same Orbit
was queued on the user's continuation request without resetting budget or creating a
topic, and the background runner claimed a fresh cycle. That cycle completed, added
one canonical source, increased used sources from 10 to 11, and published topic version
28 with nine sections. A subsequent cycle was claimed automatically; the Orbit was
`ACTIVE`, the document page returned HTTP 200 with its live status and back link, and
the append-only event chain remained valid. A `MATERIAL_CONCLUSION_CHANGE` digest for
this cycle was marked `SENT` in the notification outbox; recipient reading was not
observed. The live no-source rotation across all remaining branches has not yet been
observed.

## Focused continuation — 2026-09-27

The live no-source rotation was subsequently observed: cycles 20, 21 and 22 checked
the aeroponic equipment, division-transplant recovery, and post-division recovery-time
questions respectively. All three retained an open evidence gap and recorded one
no-source attempt. Only then did the original Orbit pause with a Chinese reason saying
all unresolved questions had been checked. It had used 1,756 of 21,600 active seconds,
11 of 100 sources, 38,985 of 1,000,000 estimated tokens and 84 of 250 search queries.
The topic remained the same ID; version 31 had nine sections; the event chain validated.

Inspection of the division-recovery chapter found adjacent hydroponic and general
growth findings presented inside the answer even though they do not directly establish
recovery duration, survival rate or disease handling. Discovery now adds targeted
English queries for recovery and aeroponic equipment, rejects general hydroponic hits
for recovery-specific questions, and compact synthesis excludes points that do not
address a question's requested facet. A no-source cycle without existing citations
now records an insufficient answer and rotates to the next frontier instead of marking
the whole Orbit blocked. The user-facing insufficient-evidence text is Chinese.

The live database was backed up again to
`AppData/Local/UuMA/wisdom.db.backup-20260927-112854` with SQLite integrity `ok`.
The runner was restarted and the same paused Orbit was queued under its existing DEEP
budget. A fresh cycle was claimed and was `ACTIVE` at the last observation. Focused
Wisdom tests passed (59 tests), targeted Ruff and diff checks passed. A full repository
run reached 336 passed and five subtests but failed in unrelated concurrent Lab Bot
work: `test_governed_receive_idempotency` raised `sqlite3.OperationalError: database
is locked`. Full Ruff also found an import-order error in the concurrently edited
`src/uuma/mcp_worker.py`; that file was not changed for this Wisdom continuation.
The outcome of the newly queued research and any resulting Telegram delivery remain
to be observed before marking this continuation fully delivered.

## Document access and relevance correction - 2026-09-27

The focused continuation reached source saturation after all three remaining open
questions were checked. The same Orbit is `PAUSED` with an explicit Chinese reason;
it did not exhaust its DEEP budget or create a new topic. The document had reached
version 33 with nine sections. A `PAUSED` notification with its document URL was
marked `SENT` by the durable outbox. Recipient reading was not observed.

The scheduled document view was found serving a different physical `wisdom.db` under
the same logical LocalAppData path, due to Windows packaged-app file redirection.
The actual view had zero topics while the Orbit runner was configured to use the Codex
LocalCache directory. The view installer now defaults to the Orbit runner's
scheduled data directory and passes it through the silent VBS launcher to the
PowerShell launcher. A default reinstall confirmed the task uses the same explicit
LocalCache directory as the Orbit runner. The
previous statement that the scheduled view shared the live hard-linked database was
incorrect; this live HTTP check exposed the split. A one-time migration backed up
the unredirected view token and aligned it with the existing topic-link token. The
unauthenticated health endpoint's temporary diagnostic fields were removed.

After reinstalling the scheduled view, the existing read-only token returned HTTP
200 for the all-topics index and all three previously reported topic URLs, including
`topic_07a8574b5d504d34a5483407c2a88400`. That page contains its overview
anchor, the back link to all topics, the `PAUSED` reason, and nine sections. The
scheduled task action now carries the explicit data directory, so a future logon
launch selects the same database and token.

Review of the live document found that the division-transplant chapter still carried
unrelated hydroponic nutrient, lighting and trough-position findings from older
versions. An online backup was created at
`AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/UuMA/wisdom.db.backup-20260927-200421`
and passed SQLite integrity check. Audited versions 34 and 35 then corrected the
transplant and recovery-time chapters using only the located UCANR division guidance
and NTU fogoponic abstract, with explicit limits on what they establish. The old
versions remain available, both new change summaries state the correction reasons,
and the knowledge event chain validates. The Orbit remains `PAUSED` with unresolved
direct-evidence gaps. One deduplicated `CONCLUSION_CORRECTION` digest with the
corrected chapter link was dispatched through Hermes and marked `SENT` on its first
attempt with no error. Recipient reading was not observed.

Focused Wisdom tests: **66 passed**. Full repository regression: **343 tests and
five subtests passed**. Full Ruff check passed. These checks do not establish that
the Telegram recipient opened the corrected digest or chapter.
