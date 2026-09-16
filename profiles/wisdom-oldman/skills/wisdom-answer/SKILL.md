---
name: wisdom-answer
description: Retrieve evidence-linked durable knowledge and explain the best current answer with citations, conditions, conflicts, uncertainty, satisfaction, and worthwhile remaining gaps. Use when Wisdom-Oldman answers from or explains the knowledge system.
---

# Wisdom Answer

Answer from the whole relevant knowledge system, not from a single matching claim.

1. Call `knowledge_answer` with `AUTO` unless the user explicitly requests `SIMPLE` or `DEEP`.
   Treat its `runtime_status`, reasoning trace, citations, and projection watermark as part of the
   answer contract.
2. Inspect important cited canonical objects with `knowledge_get`. Use `knowledge_search` only as a
   canonical text fallback or to widen an incomplete result.
3. Prefer accepted claims. Candidate claims may support a clearly labeled provisional answer when
   their evidence is directly inspectable.
4. Synthesize the best current answer in the user's language and at the requested depth.
5. Attach source title/locator and evidence location to important statements. State conditions and
   scope next to the claim they qualify.
6. Keep known conflicts visible. Explain whether apparent disagreement is contextual or unresolved.
7. Distinguish evidence, synthesis, assumption, and unknown. Describe knowledge satisfaction as
   worthwhile coverage remaining, not as a generic confidence percentage.
8. End with only the remaining gaps that would materially improve this answer or future reuse.

Do not imply completeness merely because search returned results. Do not delay a useful provisional
answer until the research lifecycle is complete. When `runtime_status` is `DEGRADED_KAG`, say that
graph, vector, and logic-form reasoning were unavailable; never present the fallback as full KAG.
