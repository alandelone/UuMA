# Observatory source and verification context

- Explicit source paths are authoritative, even if absent. Never replace them with a newer unrelated file.
- Honor remote-owner markers after migrations. Read the canonical owner; do not initialize or recreate a workstation domain database or fall back to an obsolete local copy.
- Observatory reads must use short mode=ro/query_only transactions and must not construct domain services that initialize, repair, migrate or resume work.
- Preserve all original topic/Orbit/frontier identities, terminal states and older history. ACTIVE topics and queued frontiers are not worker-liveness evidence.
- A RUNNING cycle requires the matching ACTIVE Orbit and a nonexpired lease. Keep unfinished stopped/failed/budget-exhausted records distinct from FILLED history.
- Test remote reader scripts as standalone scripts against tmp_path databases, matching production's explicit UTF-8 stdin/stdout contract on Windows as well as Linux.
- Preserve failed diagnostics; repair missing execution context before repeating a test, without weakening source, history, owner or read-only assertions.
