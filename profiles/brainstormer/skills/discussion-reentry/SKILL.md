---
name: discussion-reentry
description: Find and restore the smallest relevant prior Brainstormer topic before resuming a discussion.
---

# Discussion Re-entry

Use `brainstormer_search_topics` when project or topic identity is uncertain. On a confident match,
load `brainstormer_get_context` and resume from the latest checkpoint plus active objects. State when
a source is unavailable. Ask the user only when different plausible topics would materially change
the answer or durable state.
