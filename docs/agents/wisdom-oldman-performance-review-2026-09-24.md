# Wisdom-Oldman behavior review — 2026-09-24

## Outcome

The latest Telegram interaction does not satisfy the documented answer-now / continue-researching experience. This is an observational review, not a deployment or repair. Existing unrelated workspace changes were preserved; the mission remains verification / pending_review.

## Requirements baseline

`docs/agents/wisdom-oldman.md` sections 2, 6, 9 and 14 require a best current answer, visible uncertainty and gaps, traceable evidence, and research that may continue after answering. Section 12 defines a human-readable knowledge map, but sections 15–17 explicitly defer its UI. The original shared conversation was not reconciled into this review: the requirements record itself says its source was unreadable at consolidation time.

The Question Orbit deployment plan specifies an initial answer plus orbit_id, durable investigation, and meaningful notifications. Its later bounded QUICK default is ten minutes / ten sources / 50k model tokens, stopping at the first exhausted limit. This is not unlimited autonomous research. A stable clickable digest page is not an implemented acceptance requirement in the inspected first-phase plan.

## Observed Telegram behavior

Read the profile-local Hermes state.db using SQLite read-only mode, without modifying it or joining it to another database. Session `20260924_125457_8fbf66b3` contains the September 24 interactions at 12:56 and 12:59 Asia/Kuala_Lumpur:

- User: 针对 青葱 的 气雾栽培细节&核心构建要素 ，分株法，
- Follow-up: make it more detail
- Both responses supplied detailed cultivation instructions but no citations, provisional status, meaningful knowledge gaps, orbit_id, continuation notice, or result link.
- Specific numerical claims included spray intervals, pressure, pruning lengths, and a growth improvement above 30%. This review establishes that those claims were unsupported in the responses, not that each numerical claim is false.
- Gateway logs report zero model tool turns for both responses. Hook-based lookups can occur outside model tool turns, so this alone does not prove that every preflight was skipped.

The configured production wisdom.db contains only two September 21 acceptance Orbits and their old notifications; no Orbit exists for this cultivation topic. Thus there is no recorded durable continuation for the reviewed request in the configured knowledge store.

## Concrete gaps

1. **Investigation detection misses the actual request.** `src/uuma/question_orbit.py:44` uses a fixed substring list and minimum length. Directly invoking `is_investigative` on both actual messages returned False. This independently prevents automatic Orbit creation even if preflight runs. It is weaker than the plan's structured classification and does not resolve a follow-up against its topic.
2. **Notifications are not digests.** `src/uuma/orbit_runner.py:192` serializes event payload JSON into the user message. `src/uuma/question_orbit.py:945` creates FIRST_USEFUL_ANSWER from source presence on the first cycle, with source IDs and satisfaction but without the answer text or source URLs. The September 21 sent notification confirms that payload shape in production.
3. **No delivered reading surface.** The knowledge-map UI remains explicitly deferred. The observed responses and notification contract supply no persistent human-readable digest URL.
4. **Configured policy is not demonstrated enforcement.** The deployed SOUL includes the expected preflight/Orbit instruction and configuration enables the guard and Orbit feature. Nevertheless, the observed reply omitted the required evidence/gap behavior. Root guard execution remains unproven. Gateway logs contain guard capability-denial entries; these are an investigation lead, not sufficient proof of the cause.

At review time an Orbit runner process pair was present. A scheduled-task Ready snapshot and an older launcher exit must not be interpreted as proof that the runner is absent. No live research, Telegram message, service restart, or configuration change was performed for this review.

## Recommended acceptance criteria for repair

Use the exact topic and follow-up above as a regression scenario. The first reply should provide a bounded provisional answer, identify unsupported parameters, and disclose actual persisted continuation. The follow-up must attach to the existing topic. Subsequent meaningful updates should summarize findings, evidence links, changed conclusions, unresolved questions, and completion/budget/block status. A stable accessible topic/digest page should be explicitly designed and implemented if required; source citations alone are not that page. Verify the full real Telegram path and guard execution, not only isolated runner acceptance. Preserve candidate-only knowledge and reviewer-controlled budget escalation.
