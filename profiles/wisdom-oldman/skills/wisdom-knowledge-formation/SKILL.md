---
name: wisdom-knowledge-formation
description: Convert evidence into atomic, context-qualified claims; relate evidence; distinguish duplicates, compatibility, context dependence, conflicts, and supersession; then propose reviewable knowledge patches. Use after evidence collection or when maintaining existing knowledge.
---

# Wisdom Knowledge Formation

Form knowledge conservatively and make every canonical change reviewable.

1. Express one falsifiable idea per claim. Put entity, measurement, method, date, operating point,
   scope, units, and boundary conditions into the statement or qualifiers.
2. Add it with `knowledge_propose_claim`; a new claim must remain `CANDIDATE`.
3. Link each relevant excerpt using `knowledge_link_evidence` as `SUPPORTS`, `CONTRADICTS`, or
   `QUALIFIES`, with a concrete rationale.
4. Propose reusable entities and qualified relations with `knowledge_propose_entity` and
   `knowledge_propose_relation`. Use `knowledge_link_chunk` to preserve the graph/chunk mutual index.
   New graph objects remain candidates until reviewed.
5. Propose a versioned domain schema with `knowledge_propose_schema_module` only when the universal
   ontology cannot express a stable domain distinction or logical rule.
6. Compare against existing claims only after aligning entity, time, units, method, conditions, and
   scope. Classify the relationship as duplicate, compatible, complementary, context-dependent,
   conflict, or superseded.
7. Use `knowledge_record_conflict` only for a genuine unresolved incompatibility. If missing
   conditions prevent comparison, create a `MISSING_CONTEXT` gap instead.
8. Propose acceptance, correction, gap resolution, conflict resolution, or supersession with
   `knowledge_propose_patch`. Inspect it with `knowledge_get_diff`.

Never apply, reject, or reverse your own patch. The Orchestrator/user review boundary owns canonical
merge decisions. Never overwrite a claim to hide its prior version; use a patch and supersession or
reversal.
