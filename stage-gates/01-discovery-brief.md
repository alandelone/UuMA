# Discovery Brief

## Problem

Repository guidance was concentrated in a root prompt with no explicit progress source, session
handoff, recovery record, or deterministic fixture entry point. Agents could repeatedly rediscover
commands and miss prior failure context.

## Scope

Introduce progressive disclosure using a short root guide, a machine-readable mission state,
one-way stage contracts, session notes, module-specific rules, durable repository memory, and an
isolated test fixture. Do not change UuMA runtime behavior or database boundaries.

## Dependencies and constraints

- Python 3.11-3.13, setuptools, pytest, and ruff are declared in `pyproject.toml`.
- Local initialization must write only beneath `.uuma-local/` unless explicitly overridden.
- The repository currently has no Git commit, so destructive reset/clean has no recoverable baseline.

## Exit criteria

The desired hierarchy and invariants are explicit, project commands are verified from source, and
the design gate may define ownership and loading order.
