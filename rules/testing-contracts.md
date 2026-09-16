# Testing and Recovery Contract

## Deterministic tests

- Tests must use `tmp_path`, in-memory substitutes, or versioned files under `test-fixtures/`.
- Never point tests at `%LOCALAPPDATA%\UuMA`, Hermes `state.db`, live credentials, or network services.
- Assertions should express an approved contract, including provenance, permissions, and event order.

## Failure triage

When an Agent repeats a failed approach, stop code edits and read `repomemory/findings.md`. Classify
the failure as one of:

1. **Missing context/dependency:** record the requirement and exact diagnostic in `findings.md`, then
   add the durable instruction to the narrowest relevant file under `rules/`.
2. **Incorrect assertion/contract:** compare the assertion with approved requirements and design.
   Correct `stage-gates/03-execution-brief.md` before changing the test. Never weaken a valid safety
   or behavior assertion for a green run.

After the context fix, preserve the current diff, rerun the narrowest test, then the full suite. A
Git restart is allowed only from a named, verified commit after unrelated work is preserved. This
repository currently has no committed baseline, so `git reset --hard` and `git clean` are forbidden.
