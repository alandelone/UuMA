# Repository Guidelines

## Role and startup

Contribute carefully to UuMA, the local-first control plane for Hermes agents. Start by reading this
file, `mission_status.json`, its current gate, and `active-session/HANDOFF.md`. Load `docs/`, `rules/`,
and `repomemory/` only when needed. Follow `rules/session-lifecycle.md`: start/resume the session,
wrap commands with `python -m uuma.session run --`, then generate handoff and pass `close` before
the final response. Missing or stale handoff blocks this managed session's completion.

`mission_status.json` is the only source of truth for stage, active skill, gate status, and blocker.
Stages move in one direction: discovery -> design -> execution -> verification -> complete. Only the
Orchestrator or user review boundary may approve a gate transition.

## Project structure

- `src/uuma/` contains Python runtime code; `tests/` contains pytest contracts.
- `profiles/`, `integrations/`, `deploy/`, and `scripts/` contain agent and deployment tooling.
- `docs/` and `rules/` hold on-demand architecture, contracts, and mechanical constraints.
- `stage-gates/` owns pipeline contracts; `active-session/` owns current logs and handoff.
- `repomemory/` preserves decisions and findings; `test-fixtures/` holds fake inputs only.

## Build, test, and development commands

- `./init.sh`: create `.venv`, install dev dependencies, initialize isolated databases and fixtures
  under `.uuma-local/`; add `--serve` to start the API. On Windows, run it with Git Bash.
- `.venv/Scripts/python.exe -m pytest`: run all tests; append a test path for a focused suite.
- `.venv/Scripts/python.exe -m ruff check src tests`: lint with the 100-character limit.
- `.\scripts\start-uuma.ps1`: start the Windows HTTP control/audit endpoint.

## Style, tests, and changes

Use Python 3.11-3.13, four spaces, type hints, `snake_case` functions/modules, and `PascalCase`
classes. Name tests `test_<behavior>`. Knowledge-contract changes require focused provenance,
permission, event-chain, patch, and reversal tests. With no commit history yet, use concise
Conventional Commit subjects. Pull requests state scope, tests, schema impact, and evidence.

## Absolute prohibitions

- Keep control state in `uuma.db`, Wisdom-Oldman knowledge in `wisdom.db`, and never repurpose Hermes
  `state.db` or join these schemas.
- Keep knowledge record types distinct; preserve locations, conditions, and append-only history via
  supersession or compensating reversal.
- New claims remain candidates. Wisdom-Oldman may propose changes; only Orchestrator/user review may
  apply, reject, or reverse them.
- Keep Knowledge MCP operations semantic and backend-neutral; never expose raw vendor or SQLite APIs.
- Never weaken an assertion merely to make a failure pass. On repeated failure, follow
  `rules/testing-contracts.md`, update the missing context or execution contract, and restart from
  the current gate.
- Never destructively reset or clean a workspace without a verified committed baseline and explicit
  user authorization. Preserve and report unrelated user changes.
