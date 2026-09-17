# Findings

## 2026-09-17 - Studio focusout replaced an imminent click target

- **Symptom:** after undo restored focus to a manuscript textarea, clicking delete on a reviewer
  comment had no effect. The earlier delete from a non-editor focus state succeeded.
- **Diagnostic:** the V6 browser test twice timed out awaiting restore-comment for R1-03;
  inspection found the comment still active and the archive empty. Textarea focusout synchronously
  redrew the target table between pointer down and click.
- **Classification:** missing-context (browser focus/click ordering) and code-defect in the
  standalone Studio preview, not an incorrect deletion/recovery assertion.
- **Resolution:** do not redraw a review panel on editor blur when focus is entering that panel.
  Keep deletion assertions intact; rerun focused and full relevant UI regression tests.
- **Prevented by:** rules/ui-interaction-testing.md and V6 delete/undo/restore browser coverage.

## 2026-09-08 — Session snapshot diagnostic

Initial session tests encountered Git exit 128 in one temporary repository. Immediate rerun and
subsequent focused/full suites passed. Root cause is unconfirmed. Snapshot failure now includes
Git stderr and rejects completion rather than accepting incomplete evidence.

Record reproducible facts, not guesses. Each entry must include date, symptom, exact diagnostic,
classification (`missing-context`, `missing-dependency`, `incorrect-contract`, or `code-defect`),
resolution, and the rule/gate that now prevents recurrence.

## 2026-09-08 — No Git recovery baseline

- **Symptom:** requested workflow includes resetting the Git workspace before restarting an Agent.
- **Diagnostic:** `git log` reports that `master` has no commits; repository files are untracked.
- **Classification:** missing-dependency (a recoverable baseline commit).
- **Resolution:** do not reset or clean. Preserve the current tree and establish a reviewed baseline
  before enabling that recovery action.
- **Prevented by:** `rules/testing-contracts.md` and `AGENTS.md`.

## 2026-09-08 — Ambient development tools are unavailable

- **Symptom:** initial lint and test commands report that `ruff` and `pytest` are missing; `bash`
  invokes a broken WSL installation.
- **Diagnostic:** ambient `python` is Hermes' private virtual environment. Git Bash is available at
  `C:\Program Files\Git\bin\bash.exe`, and supported Python 3.11/3.12 launchers are installed.
- **Classification:** missing-context and missing-dependency (the project `.venv` was not initialized).
- **Resolution:** `init.sh` now selects the Python 3.12 launcher on Windows. Run it through Git Bash,
  then use the repository `.venv` for lint and tests.
- **Prevented by:** `stage-gates/03-execution-brief.md` and `AGENTS.md`.

## 2026-09-08 — Git Bash path rejected by Windows pip

- **Symptom:** editable install rejects `/c/.../UuMA[dev]` as an invalid requirement.
- **Diagnostic:** Git Bash produced a POSIX path while the selected virtual-environment interpreter
  is native Windows Python.
- **Classification:** missing-context (cross-runtime path semantics).
- **Resolution:** install from the repository working directory with `.[dev]`; convert sandbox
  environment paths with `cygpath` before native Python reads them.
- **Prevented by:** `init.sh` and this finding.

## 2026-09-08 — Ruff configured but not installed by bootstrap

- **Symptom:** the documented lint command fails after installing the declared development extras.
- **Diagnostic:** `pyproject.toml` contains `[tool.ruff]` but the `dev` extra omitted `ruff`.
- **Classification:** missing-dependency.
- **Resolution:** declare a bounded Ruff dependency in the `dev` extra so `init.sh` provides every
  documented evaluator tool.
- **Prevented by:** `stage-gates/03-execution-brief.md` and `pyproject.toml`.

## 2026-09-08 — Existing Ruff debt is outside the context mission

- **Symptom:** full static analysis exits nonzero with 81 diagnostics despite all 66 tests passing.
- **Diagnostic:** errors occur in pre-existing `src/uuma/` and `tests/`; this mission changed no
  application Python. The largest groups are import order (23), UTC modernization (17), and unused
  imports (9).
- **Classification:** code-defect baseline, not missing context and not an incorrect assertion.
- **Resolution:** record the baseline and prohibit opportunistic source rewrites. Create a dedicated
  cleanup mission if lint cleanliness becomes an acceptance criterion.
- **Prevented by:** `rules/linting-guidelines.md` and `stage-gates/03-execution-brief.md`.

## 2026-09-08 - Scholar approval and experiment controls were caller-asserted

- **Symptom:** an MCP caller could supply approval text directly, experiments used a shell command,
  and citation existence was labeled as faithfulness.
- **Diagnostic:** direct inspection and adversarial tests showed there was no trusted user-message
  grant, no approved plan boundary, and no content assessment record.
- **Classification:** incorrect-contract and code-defect.
- **Resolution:** bind single-use grants to exact Hermes user messages, execute only approved
  argument-vector plans with optional script digest pinning, and separate citation resolution from
  content-level evidence assessment and human scientific review.
- **Prevented by:** RSTV4 approval/lifecycle tests, the Scholar skill, and the Scholar MCP/toolset
  deployment boundary.

## 2026-09-08 - Specialist deployment drift and incomplete skill projection

- **Symptom:** deployed SOUL files drifted from repository definitions, Forge Lab Bot installed only
  part of its skill suite, and specialist terminal/tool execution remained enabled despite the
  documented boundary.
- **Diagnostic:** profile filesystem and Hermes inventory inspection found the drift, missing skill
  projection, and retained `terminal`/`code_execution` entries.
- **Classification:** code-defect.
- **Resolution:** deploy managed SOUL sections with backups/conflict files, install all specialist
  skill packages, remove forbidden toolsets, and remove Scholar's general Gemini worker.
- **Prevented by:** idempotent `scripts/deploy-hermes.ps1`, profile inventory verification, and the
  MCP boundary contract.

## 2026-09-08 - KAG bootstrap treated successful Docker warnings as failures

- **Symptom:** OpenSPG containers ran, but bootstrap stopped on a benign Docker seccomp warning and
  the Knowledge MCP bridge was not durably ready.
- **Diagnostic:** Docker returned exit code zero while Windows PowerShell promoted native stderr to
  a terminating error; the script also evaluated `$PSScriptRoot` too early in a parameter default.
- **Classification:** code-defect and missing-context.
- **Resolution:** use the native exit code for the quiet readiness probe, resolve the default runtime
  after parameter binding, restore/commit the OpenSPG project, and restart the bridge and gateway.
- **Prevented by:** the bootstrap implementation and live `runtime.ready=true`, `lag=0` verification.
