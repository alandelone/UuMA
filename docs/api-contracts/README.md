# API Contract Index

Canonical agent-facing boundaries live in `docs/contracts/mcp-boundaries.md`. Runtime schemas are
defined by Pydantic models in `src/uuma/models.py` and `src/uuma/knowledge_models.py`; tests are the
executable contract. Keep this index as a pointer rather than duplicating schemas that can drift.

When a contract changes, update the canonical document, focused tests, and the active verification
report. Record compatibility or migration decisions in `repomemory/decision.md`.
