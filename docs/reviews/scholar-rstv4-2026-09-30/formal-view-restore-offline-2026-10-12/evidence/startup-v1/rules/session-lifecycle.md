# Executable session lifecycle

Use the repository virtual environment. Commands below are relative to the repository root.

1. Start: `.venv/Scripts/python.exe -m uuma.session start`.
   If an unfinished session exists, use `resume`, read the handoff and progress, and continue it.
2. Execute shell work through `.venv/Scripts/python.exe -m uuma.session run -- COMMAND ARGS`.
   Start and exit events are persisted even for failing commands. Arguments and output are not
   persisted because they can contain secrets. Use handoff prose for sanitized test evidence.
3. Before ending, run `handoff --summary "..." --dead-ends "..." --next-step "..."`.
   All three fields require nonempty text; write explicit "None observed" where appropriate.
4. Run `close`. Missing handoff, later commands, changed files, deleted handoff, or a modified
   handoff returns exit code 2. Update the handoff and retry. `check` tests the same gate without closing.

The journal is an append-only application table `repo_session_events` in `.uuma-local/uuma.db`.
It stores UTC timestamps, outcomes, file hashes, and handoff versions; progress.md is a regenerated
readable projection. Existing manual progress above the automatic marker is preserved.
It does not store file contents or command output and is not a cryptographically secured audit log.
Git-listed tracked and nonignored untracked files are hashed; ignored files are outside observation.
Direct editor changes are detected at close, but their individual editing operations are not captured.

Run one session writer at a time. This entry point cannot prevent terminating a desktop process or
commands executed outside it. A crash leaves an unfinished session for `resume`; it cannot invent
the Agent's reasoning or next steps. There is no claim of a globally installed desktop stop hook.
Use `check` before workflow publication/completion steps; bypassing this CLI bypasses its gate.

Lifecycle checks read the latest journal event; progress iterates events individually. Keep the
full append-only history and the complete handoff snapshot/digest checks. Do not load all historical
handoff bodies merely to check whether a session is open, especially during low-memory execution.


## Windows handoff text and preserved prior context

When including the preceding handoff in a new CLI summary, read it with
`Path.read_text(encoding="utf-8")` so the input and verification use the same universal-newline
representation. Keep an exact raw-byte backup before generating. Do not decode `read_bytes()`
and then write that CRLF string through the CLI: Windows text writing adds another carriage
return, and reading for comparison normalizes it differently. Avoid building replacement Python
source with escaped newline strings. Supply the long summary in process to the unchanged CLI
entry point when it exceeds the Windows command-line length limit. Compare the entire previous
logical text with the generated handoff; do not weaken the full-content preservation assertion.
