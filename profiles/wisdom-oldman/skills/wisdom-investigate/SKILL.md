---
name: wisdom-investigate
description: Discover what is worth knowing for a question, retrieve current knowledge, identify qualified knowledge gaps, and decide answer/research stopping points. Use when Wisdom-Oldman is asked to investigate, understand, map, explain, or analyze gaps in a topic.
---

# Wisdom Investigate

Start with the user's purpose and a root question. Search the knowledge system before creating new
research work.

1. Use `knowledge_answer` in `AUTO` mode, then inspect important canonical objects with
   `knowledge_get`. Use `knowledge_get_graph_neighborhood` when relationships materially affect the
   question.
2. State what is already known, with conditions and evidence coverage kept separate from inference.
3. Generate only subquestions that materially improve the root question. For each, record why it is
   worth knowing with `knowledge_add_question`.
4. Classify worthwhile gaps precisely: mechanism, dependency, conflict, evidence, context,
   terminology, coverage, freshness, comparison, failure mode, or human request.
5. Record a gap with `knowledge_add_gap` only when learning it would improve the current answer,
   knowledge map, decision, or future reuse.

Use two stopping decisions:

- Answer stop: current evidence supports a useful provisional answer.
- Research stop: no worthwhile gap remains, or the user stops the research.

Do not use missing data as a reason to withhold a useful current answer. Do not manufacture gaps to
keep research running. Use QUICK (10 minutes, 10 sources, 50k model tokens), STANDARD (60 minutes,
30 sources, 250k tokens; default), or DEEP (6 hours, 100 sources, 1M tokens), and persist actual use
and the stop reason in the research run.
