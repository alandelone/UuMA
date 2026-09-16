# General Rules

- Make the smallest coherent change that satisfies the current execution brief.
- Preserve public behavior unless the current design explicitly changes it.
- Read neighboring code and tests before introducing a new pattern.
- Keep generated state, secrets, databases, caches, and real user data out of Git.
- Update `active-session/progress.md` after meaningful commands, edits, and decisions.
- Promote durable discoveries to `repomemory/`; do not leave essential context only in a session log.
- If a task crosses a gate boundary, stop and obtain Orchestrator/user approval before updating
  `mission_status.json`.
