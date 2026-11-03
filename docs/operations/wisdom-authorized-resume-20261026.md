# User-authorized Wisdom research continuation — 2026-10-26

The user explicitly requested resuming failed, stopped and unexecuted research.
The inventory contained five existing Orbits: one real green-onion aeroponics
research investigation, two duplicate RFC deployment acceptance records, and two
withdrawn investigations generated from invalid inputs (a progress question and a
404 error body). Optional clarification was requested about the withdrawn records
and duplicate acceptance records. The valid research could proceed independently.

## Resumed investigation

- Orbit: `orbit_9ac4d099873b82f8f5a730cf07792419`.
- Existing subject: green-onion aeroponic cultivation components and division.
- Server owner: `~/.local/share/uuma/production/wisdom-oldman/wisdom.db`.
- Called the existing server-profile `knowledge_orbit_resume` semantic MCP tool.
  The short-lived client's automatic detached wake was suppressed; the installed
  `uuma-wisdom-orbit.service` performed the single explicit worker wake instead.
  Production profile and environment files were not edited.
- Confirmed original frontier and cumulative time/source/token/search/cycle counters
  were identical immediately before and after the queue transition. No reset,
  duplicate topic, claim approval, schema change or source deployment occurred.
- Service PID213482 became active. At 2026-10-26 10:02:29 Asia/Kuala_Lumpur the
  investigation was ACTIVE, cycle `cycle_3544ff408e8748529f5ce9384590d4de` was RUNNING
  with owner `alandelone-server-001:213482` and a valid lease. The frontier contained
  six FILLED, one IN_PROGRESS and three OPEN items. This proves execution started;
  it does not prove the research is complete or that the next provider call succeeds.

The two withdrawn invalid investigations remain STOPPED. Both duplicate RFC
acceptance records retain their prior states pending a more specific user selection;
the real research was not delayed by that optional decision.

## Receipts and constraints

A consistent SQLite backup, original records, semantic-tool result, counter/frontier
preservation assertions and service wake receipt are private on the server under
`~/.local/share/uuma/wisdom-authorized-resume-20261026/`. Sanitized inspection and
verification copies are under `.uuma-local/wisdom-critic/` on the workstation.
The event-sourced transition retains prior failures. Do not restore the pre-resume
database over new research writes; use semantic pause/stop if later requested.

No shared gateway restart, software deployment, test run, Git commit/push or mission
gate approval. The user authorized continuing the existing research and its configured
research workflow; no unrelated standalone message or historical-notification replay
was submitted. The prior failed-notification warning remains an independent issue
and does not itself mean the newly resumed worker is stopped.

## Later status check at 14:57 Asia/Kuala_Lumpur

After the user reported that the UI still showed FAILED, a new authoritative read
found the main investigation PAUSED since 10:07:07, with six FILLED and four OPEN
frontier items. Its last cycle completed without an exception; the recorded summary
reported eleven search attempts, zero successes and eight without direct matches.
The worker had exited after becoming idle. The earlier RUNNING lease observation
was valid at the time and must not be presented as continuous execution afterward.

The user's actual Chrome tab still selected the September RFC acceptance failure
(`wisdom_orbit_orbit_7c0097134a7345314d2a6abf11b82cce`). The workspace underneath
already showed the main research PAUSED. Selecting the green-onion topic changed
the page to `wisdom_topic_topic_07a8574b5d504d34a5483407c2a88400`; its inspector
confirmed investigation PAUSED and separately displayed the October notification
delivery failure. No research was requeued and no service or source was changed
during this explanation. Browser evidence is saved privately as
`.uuma-local/wisdom-critic/current-topic-paused-20261026.png`.
