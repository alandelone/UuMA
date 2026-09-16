# Linting Guidelines

- Run `python -m ruff check src tests` after Python edits.
- Target Python 3.11 syntax and a maximum line length of 100, matching `pyproject.toml`.
- Fix the cause of a diagnostic; suppressions require a short reason and narrow scope.
- Do not mix broad formatting churn with a functional change.
- Treat import, typing, and unreachable-code diagnostics as potential contract defects, not cosmetics.
- Until the recorded 81-error legacy baseline has its own cleanup mission, context-only changes must
  not trigger broad source rewrites. Record the full-suite result and require changed Python files to
  introduce no additional diagnostics.
