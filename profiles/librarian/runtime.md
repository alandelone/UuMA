# Librarian runtime contract

Librarian runs on `alandelone-server-001`. Its profile is under the shared Hermes
home at `~/.local/share/uuma/pilot/home/profiles/librarian`. Workstation definitions
are development sources, not proof of production installation.

The worker entry point is `src/uuma/librarian_worker.py`, deployed as a separately
hashed script with the production UuMA interpreter and source dependencies. The
minimal Librarian semantic environment does not contain `uuma.mcp_worker` and must
not be used to launch the generic worker module.

Keep the MCP server key `uuma-worker` for governed assignment checks. Include only
`register_direct_run`, `get_assignment`, `report_progress`, `block_run`, and
`submit_result`. The server requires `UUMA_AGENT_ID=librarian`, its own scoped
`UUMA_IDENTITY_TOKEN_FILE`, and `UUMA_CONTROL_URL`; it never creates a local control
database. Direct work is restricted to read-only retrieval. Acceptance stays with
Orchestrator/user review.

The independent `uuma-librarian-read` MCP exposes seven semantic read tools. Recovery
intake remains separate from the semantic catalog; receipt of encrypted recovery
objects does not grant agents access to their plaintext or index all source records.

Collectors operate without an LLM at midnight UTC+8. Retain version history,
unavailable sources, source age, real capture times, and missed-day evidence.
On Windows, inspect the actual task user context: packaged desktop applications
can virtualize AppData paths. Validate the private SSH key ACL in the scheduled
task's context rather than relying on a desktop-process probe.

On November 3, the NAS hardware issue was explicitly deferred by the user. Keep
its existing publication pause; do not interpret that deferral as a repair or a
successful recovery publication. The second workstation is prepared for manual
installation by the user, not remotely enrolled. Independent recovery-key custody
remains a required final user action.
