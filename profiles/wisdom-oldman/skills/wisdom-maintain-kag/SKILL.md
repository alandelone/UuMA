---
name: wisdom-maintain-kag
description: Maintain Wisdom-Oldman's governed KAG projection, freshness, schema modules, provenance links, health, and reversibility. Use for knowledge-base health checks, stale knowledge review, projection repair, ontology maintenance, or long-term knowledge hygiene.
---

# Wisdom Maintain KAG

Keep `wisdom.db` authoritative and treat OpenSPG KAG as a disposable projection.

1. Inspect `knowledge_projection_health`. A runtime failure and a projection lag are different
   problems; report them separately.
2. Use `knowledge_projection_sync` for pending canonical events. Allow its scoped recovery only for
   the configured `uuma-wisdom-kag` runtime. Never repair lag by editing OpenSPG directly.
3. Review due/stale records by listing `freshness_policy`. Re-verify volatile claims first, preserve
   the prior evidence/version, and propose changes through patches.
4. Use exact deduplication and provenance-link repair without changing claim meaning. Claims,
   entities, relations, schema/rules, conflicts, and supersession always require the review boundary.
5. Inspect immutable history after material maintenance. Use a compensating patch reversal when an
   approved change must be undone.

Do not merge `wisdom.db` with `uuma.db` or Hermes `state.db`. Do not treat a rebuilt projection as
proof that the canonical evidence, conditions, or approval state are correct.
