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

`uuma-librarian-operations` adds read-only intake/publication receipt status for the
Librarian identity. Its explicit profile and guard allowlists are required. The
`uuma_librarian_commands` plugin supplies `/library`, `/library_sources` and
`/library_issues`, with stable source links and pagination. Refresh its deployment
inventory when enrolling new sources. See `librarian-overview-20261105.md` for scope
and verification evidence.

Apply the explicit CLI, API and Telegram toolset scope in `tools.yaml`. Configuring only CLI
toolsets leaves the API platform's default toolsets in effect. Do not expose shell,
file mutation, computer control, or unrelated MCP servers through that fallback.

Install the actual `uuma_control_guard` and `uuma_audit` plugin files into this
profile's `plugins/` directory as verified immutable releases. Listing their names
in configuration alone does not install them. The guard needs the scoped MCP
allowlist and must validate current assignment authority before domain reads.
Schema definitions of an `error` field are data, while actual MCP execution errors
continue to fail closed. Verify loaded hooks and real tool executions after reload.

Collectors operate without an LLM at midnight UTC+8. Retain version history,
unavailable sources, source age, real capture times, and missed-day evidence.
On Windows, inspect the actual task user context: packaged desktop applications
can virtualize AppData paths. Validate the private SSH key ACL in the scheduled
task's context rather than relying on a desktop-process probe.

The user replaced the NAS disks and authorized publication resumption. Publication
has resumed with separate hash and recovery receipts. Check current receipts for
coverage rather than reapplying the historical November 3 pause. The second workstation is prepared for manual
installation by the user, not remotely enrolled. Independent recovery-key custody
remains a required final user action.

Telegram is enabled for `@uulibrarian_bot` using profile-local credentials and the
existing owner's allowlist. The profile shares the server Hermes gateway with the
other specialists. Retain its independent identity, scoped MCP commands and guard.
The model/provider configuration follows the verified Forge configuration at the
November 5 deployment. Connection health and actual model/tool responses require
separate verification. See the dated Telegram deployment operations record.
