# Technical Design

## Context tiers

- **Hot:** `AGENTS.md` and `mission_status.json` are always read. They contain navigation, state,
  commands, and absolute prohibitions only.
- **Warm:** the current `stage-gates/` contract and `active-session/HANDOFF.md` are read on startup;
  `progress.md` is appended during work.
- **Cold:** `docs/`, `rules/`, `repomemory/`, and `test-fixtures/` are loaded only through a link from
  the active task, failure, or module.

## State ownership

`mission_status.json` alone records the active stage, skill, current gate, blocker, and update time.
Narrative files may explain state but must not claim a competing status. Gate transition is
monotonic and requires Orchestrator/user review.

## Recovery flow

Repeated failure routes to `repomemory/findings.md`. The diagnosis updates either the narrowest
mechanical rule or the execution contract. Only then does execution restart. Workspace restoration
requires a named committed baseline and preserved unrelated changes.

## Data safety

`init.sh` creates `.venv`, installs development dependencies, writes isolated `uuma.db` and
`wisdom.db` under `.uuma-local/`, and copies deterministic fixtures. It never touches Hermes
`state.db` or default production data.
