---
name: wisdom-evidence-research
description: Acquire verifiable information for a qualified knowledge gap and preserve exact source provenance, evidence location, context, conditions, and freshness. Use when Wisdom-Oldman needs web, paper, datasheet, standard, manual, dataset, or other source research.
---

# Wisdom Evidence Research

Research against a specific question or worthwhile gap, not a broad topic dump.

1. Choose source authority for the claim: papers for scholarly mechanisms, manufacturer documents
   for exact specifications, and standards/manuals/primary records when appropriate.
2. Search using the subject, synonyms, conditions, dates, units, failure modes, and citation trails.
   Select from currently configured and permitted sources. Use `chatgpt-consultation` when ChatGPT
   can help develop leads (`chat`), find sources (`search`), or investigate a valuable gap across
   sources (`deep_research`). Give it the specific gap, conditions and prior attempts. Collect the
   actual request result and preserve its provenance; a capability or empty adapter response is
   not evidence of completed research. The DEEP budget tier is independent of the selected mode.
3. Snapshot selected files with `knowledge_ingest_file` and public pages with
   `knowledge_ingest_web`. When another authorized connector acquired the content, pass the
   inspected text to `knowledge_ingest_text`. These operations preserve raw digest, document
   version, chunk boundaries, and source locator.
4. Register a source directly with `knowledge_add_source` only when no content snapshot is
   available. Preserve its stable locator, title, publisher, authored/retrieved time, type, and
   content digest when available.
5. Extract the smallest evidence passage that supports evaluation. Store it with
   `knowledge_add_evidence`, including page/section/table location and surrounding conditions.
6. Link the evidence to the exact source chunk with `knowledge_link_chunk` when a chunk contains it.
7. Run `knowledge_extract_candidates` when the ingested document should contribute reusable graph
   structure. Its output remains candidate claims/entities/relations and still requires formation
   review; extraction is not acceptance.
8. Keep direct evidence distinct from summaries and inferences. Never turn a search-result snippet
   into evidence when the underlying source can be inspected.

One good source may support a provisional candidate. Important or surprising claims merit stronger
corroboration. Preserve disagreement; do not select a convenient source and hide the rest.

When nothing new is found, distinguish an actual empty result from a request still waiting, a
failure, an unavailable tool or a quota limit. Revise the search, use another relevant permitted
route, ask ChatGPT to develop better leads, or advance another worthwhile branch. Avoid repeating
the same ineffective query. Retain unresolved gaps and actual attempt results; do not pause the
topic just because each question has had an unsuccessful search. Explain any concrete blocker and
the next action without claiming an unrecorded retry will happen.
