# Architecture Decisions

## ADR-001: Progressive-disclosure repository context

- **Status:** accepted for implementation; completion awaits verification review.
- **Decision:** separate hot root state, warm stage/session contracts, and cold domain rules/memory.
- **Reason:** stable minimal context improves cache reuse and prevents unrelated guidance from
  competing for attention.
- **Consequence:** `mission_status.json` owns progress; narrative documents link to it rather than
  maintaining parallel status.

## ADR-002: Isolated initialization

- **Status:** accepted for implementation.
- **Decision:** `init.sh` defaults runtime state to `.uuma-local/` and stages versioned fake data.
- **Reason:** initialization and tests must never depend on or mutate user production state.
