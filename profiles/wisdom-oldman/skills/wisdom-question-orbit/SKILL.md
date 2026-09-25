---
name: wisdom-question-orbit
description: Start, inspect, pause, resume, or stop durable background investigation for worthwhile knowledge gaps after the best current answer has been returned.
---

# Wisdom Question Orbit

Default preflight is read-only intake. Classify the user's intent from conversation context before
creating knowledge. Status/progress requests read `current_status` or the Orbit status tools;
feedback, errors and casual conversation never create research. For a genuine research request,
call `knowledge_question_preflight` with `intent="research"`, the resolved research question, and
the intake's original notification route, task and run IDs. If `requires_topic_approval` is returned,
present the proposed title and scope and
ask permission to create it and begin research. Wait for a later explicit user confirmation before
repeating the exact question with `topic_creation_approved=true`. Never approve your own proposal;
reuse existing topics without a new creation permission. Check that sources actually support
the question before presenting the answer. Treat its answer as the best-current
answer and disclose `orbit_id` when an Orbit was started or reused. Also return the stable topic
document link. The topic and question match is durable across chat sessions; follow-up focus should
extend the returned topic instead of creating an isolated research store.

Use `knowledge_orbit_status`, `knowledge_orbit_list`, and `knowledge_orbit_frontier` to explain
progress. The frontier order is categorical and explainable: HIGH before MEDIUM before LOW, then
relevance, impact, uncertainty, novelty, lower estimated cost, creation time, and stable ID.

Use pause, resume, and stop only when the user or Orchestrator asks, or when an explicit safety
boundary requires it. Never delete Orbit history. Never increase a budget tier without explicit
user or Orchestrator authorization. New findings remain evidence and candidate knowledge; never
approve a candidate or apply a patch yourself.

The topic document is the primary human-readable output. Answer the immediate question in the chat,
then point to the relevant document section. Only promise continued work when an Orbit was actually
persisted. Concrete parameters require citations or an explicit provisional label.

Do not invoke CopyCat, XHS, GUI control, external messaging, or provider-native APIs. Those remain
Orchestrator-owned boundaries. If research needs login, CAPTCHA, payment, credentials, or a new
authority, leave the Orbit blocked and identify the decision required.
