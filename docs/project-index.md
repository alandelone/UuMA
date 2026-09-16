# Project Index

Use this page to locate context without loading the whole repository.

| Area | Purpose | Read when |
| --- | --- | --- |
| `src/uuma/service.py`, `event_store.py`, `projections.py` | Control-plane state and event projection | Changing task/run lifecycle |
| `src/uuma/knowledge_*.py`, `kag_*.py` | Wisdom knowledge lifecycle and rebuildable KAG projection | Changing evidence, claims, patches, or retrieval |
| `src/uuma/mcp_*.py` | Semantic MCP boundaries | Adding or changing agent-facing tools |
| `src/uuma/policy.py`, `router.py`, `auth.py` | Permissions and routing | Changing authority or agent selection |
| `profiles/`, `integrations/hermes/` | Agent policy and Hermes adapters | Deploying or changing profile behavior |
| `deploy/`, `scripts/` | Local services and deployment | Operating UuMA or Hermes |
| `tests/` | Executable contracts | Verifying any behavior change |

Architecture: `docs/architecture/system-architecture.md`. Multi-Agent Logic Graphs:
`docs/logic-graphs.md`. Graph and KAG details:
`docs/architecture/graph-engineering.md` and `docs/architecture/wisdom-kag.md`. MCP contracts:
`docs/contracts/mcp-boundaries.md`.

For the active mission, follow `mission_status.json`; then open only its named gate and the rules
linked by that gate.
