---
name: discussion-state
description: Preserve Brainstormer projects, topics, decisions, assumptions, questions, and checkpoints through validated state transactions.
---

# Discussion State

Restore existing state with `brainstormer_get_context` before substantial reasoning. Submit changes
through `brainstormer_propose_transaction`; never edit canonical JSON. Project, Topic, Decision, and
supersession operations require Orchestrator review. Assumptions, questions, and checkpoints may use
`brainstormer_commit_safe_transaction` after reviewing the returned proposal.

Preserve source references, expected revisions, rejected directions, uncertainty, and unresolved
questions. Resolve, reopen, or supersede records instead of deleting history.
