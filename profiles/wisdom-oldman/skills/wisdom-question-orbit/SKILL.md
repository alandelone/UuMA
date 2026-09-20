---
name: wisdom-question-orbit
description: Start, inspect, pause, resume, or stop durable background investigation for worthwhile knowledge gaps after the best current answer has been returned.
---

# Wisdom Question Orbit

Use `knowledge_question_preflight` for a new user question. Treat its answer as the best-current
answer and disclose `orbit_id` when an Orbit was started or reused.

Use `knowledge_orbit_status`, `knowledge_orbit_list`, and `knowledge_orbit_frontier` to explain
progress. The frontier order is categorical and explainable: HIGH before MEDIUM before LOW, then
relevance, impact, uncertainty, novelty, lower estimated cost, creation time, and stable ID.

Use pause, resume, and stop only when the user or Orchestrator asks, or when an explicit safety
boundary requires it. Never delete Orbit history. Never increase a budget tier without explicit
user or Orchestrator authorization. New findings remain evidence and candidate knowledge; never
approve a candidate or apply a patch yourself.

Do not invoke CopyCat, XHS, GUI control, external messaging, or provider-native APIs. Those remain
Orchestrator-owned boundaries. If research needs login, CAPTCHA, payment, credentials, or a new
authority, leave the Orbit blocked and identify the decision required.
