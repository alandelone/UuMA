# Session progress memory repair

Changed only the progress projection in src/uuma/session.py, its tempfile import, and two focused tests in tests/test_session.py. Exact original raw bytes are retained here. No shared handoff, session close, gate, journal append, lifecycle check or full snapshot validation was changed.

The prior progress function already iterated rows. Its SQLite JSON functions nevertheless parsed each full payload, while the Python code retained the old projection, a list of new lines and concatenated output. These are allocation amplification paths consistent with MemoryError under pressure; they do not prove a memory leak or establish the exact system cause. The original completed business command was not replayed.

The new projection reads id/time/kind/payload in ascending ID order and decodes one payload at a time in Python. It removes only top-level content/snapshot and preserves the old files_observed behavior, including scalar/null cases. It streams the complete manual prefix in 64 KiB chunks and all events to a sibling temporary file, then replaces the projection atomically. Errors propagate; the old projection stays intact and temporary output is removed. No history is pruned, truncated or skipped.

## Verification

Each command ran once through the official session run wrapper and returned zero, including its final progress generation:

- Focused lifecycle suite: **9 passed in 3.12s**. New tests compare the exact previous projection contract on isolated data with a large payload, nested content, scalar/null snapshots and a marker crossing the chunk boundary. SQLite JSON functions are denied during the new projection. A controlled mid-projection MemoryError preserves the original file and every journal row. Existing lifecycle and handoff guard tests remain intact.
- Ruff on both changed files: **PASS**.
- Actual journal projection: **28,410 rows**, each projected field checked against a frozen read-only source transaction. Every original id/time/kind/payload field digest stayed identical. Python tracemalloc peak during projection was **7,028,358 bytes**; output was **3,471,527 bytes**. See readonly-journal-receipt.json. This is not a whole-process native-memory measurement or a comparative benchmark.

The real-journal verifier bypassed only Session's writing constructor by explicitly assigning its read-only connection and an owned output root. It did not bypass any managed command wrapper or lifecycle gate. Normal wrapper events are appended outside the child reader's frozen snapshot, so this evidence claims no child source mutation, not an unchanged global active journal. No command failed before or after its inner execution during this repair validation.

No Scholar full suite, model, browser, service or old business action was repeated. No handoff body was printed. Parent owns the shared handoff and close.

Source hashes are recorded in source-after.json and manifest.json.
