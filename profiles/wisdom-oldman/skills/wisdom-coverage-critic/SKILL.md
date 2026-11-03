---
name: wisdom-coverage-critic
description: Interpret the independent coverage critic and research-first Orbit escalation.
---

# Independent coverage review

Use the durable Question Orbit runner for continued research. It delegates coverage
review to a separate API model after each completed evidence batch. The researcher
does not certify completeness from citation counts or its own general confidence.

The source order is ChatGPT consultation in `deep_research` mode first, academic
sources second, general web search third, and configured supplemental sources fourth.
An insufficient critique advances to the next source tier. Await an asynchronous
request before escalating; keep its request ID and owning provider across restarts.

The critic receives the current question, user purpose/scope, current answer,
canonical source excerpts and locations, unresolved gaps and remaining budget. It
returns `SUFFICIENT` or `CONTINUE`, a rationale, per-requirement evidence coverage,
and useful follow-up questions. Inspect the persisted cycle's `critic` receipts.
The default delegate is model `complex` at the operator-configured gateway. Its
model, prompt, input/output hashes and token use are recorded separately.

Continue to deliver useful provisional answers. A timeout, malformed verdict,
invented evidence reference, unresolved material conflict or exhausted budget is
never a sufficiency decision. Budgets and user stop/pause instructions still govern
execution. The critic has no tools and cannot approve or apply a knowledge patch.

The `xhs` MCP is a supplemental community-source capability. Use `xhs_search_links`
and `xhs_search_status` for asynchronous link discovery. Search-card snippets are
leads, not evidence. `xhs_link_to_text` / `xhs_text_status` provide a separate staged
content pipeline when extraction is authorized; do not trigger media/comment
extraction merely because a keyword search returned a link. Attribute community
claims and preserve conflicts with academic evidence. If Chrome pairing or login
is unavailable, record that blocker rather than using a stale completed job.
