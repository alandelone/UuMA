# Project Context and Invariants

UuMA is a local-first control plane for a Hermes multi-agent system. The original Hermes profile is
the Orchestrator; Brainstormer, Scholar, Wisdom-Oldman, and Forge Lab Bot are bounded specialists.
CopyCat is an external MCP service and only the Orchestrator may discover or execute reviewed
actions. It may be leveraged for procurement search expansion and overcoming stealth web crawling,
but is strictly restricted from making payments.

The append-only UuMA event log is the control-plane source of truth. Hermes Kanban is a durable
scheduler and execution projection; current graph, task, and run tables must be rebuildable.

Control state belongs in `uuma.db`. Knowledge sources, evidence, candidate claims, conflicts,
questions, gaps, proposals, and hash-chained history belong in the separate `wisdom.db`. Hermes
`state.db` is outside UuMA ownership. OpenSPG/KAG is a rebuildable projection, not canonical state.
