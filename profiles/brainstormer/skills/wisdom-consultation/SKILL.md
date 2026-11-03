---
name: wisdom-consultation
description: Ask Wisdom directly for a bounded, evidence-linked answer and preserve unanswered questions.
---

# Wisdom knowledge consultation

Use when a discussion needs external facts or reusable knowledge held by Wisdom. This is a direct
A2A knowledge request; the main assistant still owns discussion framing, analysis and synthesis.

1. Restore the active project/topic and the current registered Brainstormer run/epoch. Identify
   the precise question, purpose and relevant evidence gaps. Do not send entire memories, files,
   private databases, credentials or unrelated conversation history.
2. Call `brainstormer_ask_wisdom` with these identifiers, bounded context, actual source references,
   and a stable idempotency key. Keep `research_if_unknown=false` unless the user requested new
   research. The default is lookup plus retention of unanswered questions.
3. Preserve the returned Wisdom run/task and A2A receipt with this topic's checkpoint. SUBMITTED
   means dispatched, not answered. An UNCONFIRMED dispatch needs observation of the original run;
   do not manufacture another key, duplicate the question or restart uncertain execution.
4. Use `brainstormer_wisdom_status` for the actual response. Report sources, locators, conditions,
   remaining questions and durable research references. PARTIAL, PENDING_RESEARCH, NEEDS_INPUT
   and BLOCKED are not factual completion. If no answer is available, explain what is still missing.
5. Save useful attributed inputs and unresolved questions through normal discussion transactions.
   A Wisdom response does not approve a decision, resolve an assumption automatically, or grant
   permission to read Wisdom's database or use another identity's token.

This path does not authorize other agent targets, shared graph changes, patch acceptance,
messages, purchases, hardware operations, or resuming human-paused/stopped work. The distinct
Brainstormer critic, when implemented, reviews the use of evidence; it is not the research worker.
